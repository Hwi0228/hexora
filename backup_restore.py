"""Verified backup archives and explicit, guarded database restoration."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit


class BackupError(RuntimeError):
    """Raised when a database backup cannot be safely created or restored."""


FORMAT_VERSION = 1
SQLITE_PAYLOAD = "database.sqlite3"
POSTGRES_PAYLOAD = "database.dump"
MANIFEST_NAME = "manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sqlite_integrity_check(path: Path) -> None:
    try:
        with sqlite3.connect(str(path)) as connection:
            result = connection.execute("PRAGMA integrity_check").fetchone()[0]
            foreign_key_errors = connection.execute("PRAGMA foreign_key_check").fetchall()
    except sqlite3.DatabaseError as exc:
        raise BackupError("SQLite 백업 파일을 열 수 없거나 손상되었습니다.") from exc
    if result != "ok":
        raise BackupError(f"SQLite 무결성 검사에 실패했습니다: {result}")
    if foreign_key_errors:
        raise BackupError(
            f"SQLite 외래 키 참조 무결성 검사에 실패했습니다: {len(foreign_key_errors)}건"
        )


def _sqlite_summary(path: Path) -> dict:
    _sqlite_integrity_check(path)
    with sqlite3.connect(str(path)) as connection:
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        counts = {}
        for table in ("users", "questions", "question_revisions"):
            if table in tables:
                # Table names come only from this fixed allowlist.
                counts[table] = int(
                    connection.execute(f'SELECT COUNT(*) FROM "{table}"').fetchone()[0]
                )
    return {"counts": counts, "foreign_key_violations": 0}


def _postgres_summary(database_url: str) -> dict:
    try:
        import psycopg
    except ImportError as exc:
        raise BackupError("PostgreSQL 검증에는 psycopg가 필요합니다.") from exc
    try:
        with psycopg.connect(database_url) as connection:
            with connection.cursor() as cursor:
                cursor.execute(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE'"
                )
                tables = {row[0] for row in cursor.fetchall()}
                counts = {}
                for table in ("users", "questions", "question_revisions"):
                    if table in tables:
                        cursor.execute(f'SELECT COUNT(*) FROM "{table}"')
                        counts[table] = int(cursor.fetchone()[0])
                cursor.execute(
                    "SELECT COUNT(*) FROM pg_constraint "
                    "WHERE contype = 'f' AND connamespace = 'public'::regnamespace "
                    "AND NOT convalidated"
                )
                unvalidated_constraints = int(cursor.fetchone()[0])
    except Exception as exc:
        raise BackupError(f"PostgreSQL 데이터 검증에 실패했습니다: {exc}") from exc
    return {
        "counts": counts,
        "foreign_key_violations": 0,
        "unvalidated_foreign_keys": unvalidated_constraints,
    }


def _database_summary(database_type: str, target) -> dict:
    if database_type == "sqlite":
        return _sqlite_summary(Path(target))
    if database_type == "postgresql":
        return _postgres_summary(str(target))
    raise BackupError("지원하지 않는 데이터베이스 유형입니다.")


def _verify_restored_summary(database_type: str, target, expected: dict) -> dict:
    actual = _database_summary(database_type, target)
    if actual.get("counts", {}) != expected.get("counts", {}):
        raise BackupError(
            "복구 후 핵심 테이블의 레코드 수가 백업 manifest와 일치하지 않습니다."
        )
    if actual.get("foreign_key_violations", 0):
        raise BackupError("복구 후 외래 키 참조 무결성 검사에 실패했습니다.")
    if actual.get("unvalidated_foreign_keys", 0):
        raise BackupError("PostgreSQL에 검증되지 않은 외래 키 제약조건이 있습니다.")
    return actual


def _postgres_environment(database_url: str) -> dict[str, str]:
    parsed = urlsplit(database_url)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname:
        raise BackupError("유효한 PostgreSQL DATABASE_URL이 필요합니다.")

    environment = os.environ.copy()
    environment["PGHOST"] = parsed.hostname
    if parsed.port:
        environment["PGPORT"] = str(parsed.port)
    if parsed.username:
        environment["PGUSER"] = unquote(parsed.username)
    if parsed.password:
        environment["PGPASSWORD"] = unquote(parsed.password)
    database_name = unquote(parsed.path.lstrip("/"))
    if not database_name:
        raise BackupError("DATABASE_URL에 PostgreSQL 데이터베이스 이름이 없습니다.")
    environment["PGDATABASE"] = database_name

    query = parse_qs(parsed.query)
    for key in ("sslmode", "sslrootcert", "sslcert", "sslkey", "connect_timeout"):
        if query.get(key):
            environment["PG" + key.upper()] = query[key][-1]
    return environment


def _find_postgres_tool(name: str) -> str | None:
    preferred_major = os.environ.get("HEXORA_POSTGRES_CLIENT_VERSION", "").strip()
    if preferred_major:
        preferred = shutil.which(f"{name}-{preferred_major}")
        if preferred:
            return preferred
        bundled = Path(f"/usr/lib/postgresql/{preferred_major}/bin") / name
        if bundled.is_file():
            return str(bundled)
    return shutil.which(name)


def _run_postgres_tool(command: list[str], environment: dict[str, str], timeout: int):
    try:
        result = subprocess.run(
            command,
            env=environment,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as exc:
        executable = Path(command[0]).name
        raise BackupError(
            f"{executable} 실행 파일을 찾지 못했습니다. PostgreSQL client 도구를 설치해 주세요."
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise BackupError("PostgreSQL 백업/복구 작업이 제한 시간 내에 끝나지 않았습니다.") from exc
    if result.returncode:
        detail = (result.stderr or result.stdout or "알 수 없는 오류").strip()
        raise BackupError(f"PostgreSQL 도구 실행에 실패했습니다: {detail[-2000:]}")


def _validate_postgres_dump(path: Path, environment: dict[str, str]) -> None:
    executable = _find_postgres_tool("pg_restore")
    if not executable:
        raise BackupError("pg_restore를 찾지 못했습니다. PostgreSQL client 도구를 설치해 주세요.")
    _run_postgres_tool([executable, "--list", str(path)], environment, timeout=60)


def create_backup(
    database_type: str,
    source,
    *,
    output: Path | None = None,
    schema_version: int = 0,
) -> Path:
    """Create a ZIP archive containing the database payload and integrity manifest."""
    if database_type not in {"sqlite", "postgresql"}:
        raise ValueError("지원하지 않는 데이터베이스 유형입니다.")

    destination = (
        Path(output).expanduser().resolve()
        if output is not None
        else Path.cwd() / (
            "hexora-backup-"
            + datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + ".zip"
        )
    )
    destination.parent.mkdir(parents=True, exist_ok=True)
    payload_name = SQLITE_PAYLOAD if database_type == "sqlite" else POSTGRES_PAYLOAD

    with tempfile.TemporaryDirectory(prefix="hexora-backup-") as temporary:
        payload = Path(temporary) / payload_name
        if database_type == "sqlite":
            source_path = Path(source)
            if not source_path.is_file():
                raise BackupError("SQLite 데이터베이스 파일을 찾지 못했습니다.")
            try:
                with sqlite3.connect(str(source_path)) as source_connection:
                    with sqlite3.connect(str(payload)) as backup_connection:
                        source_connection.backup(backup_connection)
                        backup_connection.commit()
            except sqlite3.DatabaseError as exc:
                raise BackupError("SQLite 백업을 생성하지 못했습니다.") from exc
            _sqlite_integrity_check(payload)
        else:
            environment = _postgres_environment(str(source))
            executable = _find_postgres_tool("pg_dump")
            if not executable:
                raise BackupError("pg_dump를 찾지 못했습니다. PostgreSQL client 도구를 설치해 주세요.")
            _run_postgres_tool(
                [
                    executable,
                    "--format=custom",
                    "--no-owner",
                    "--no-acl",
                    "--file",
                    str(payload),
                ],
                environment,
                timeout=300,
            )
            _validate_postgres_dump(payload, environment)

        database_summary = (
            _sqlite_summary(payload)
            if database_type == "sqlite"
            else _postgres_summary(str(source))
        )
        manifest = {
            "format_version": FORMAT_VERSION,
            "database_type": database_type,
            "schema_version": int(schema_version),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "payload": payload_name,
            "sha256": _sha256(payload),
            "database_summary": database_summary,
        }
        temporary_archive = destination.with_name(destination.name + ".tmp")
        try:
            with zipfile.ZipFile(
                temporary_archive, "w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.write(payload, arcname=payload_name)
                archive.writestr(
                    MANIFEST_NAME,
                    json.dumps(manifest, ensure_ascii=False, indent=2),
                )
            os.replace(temporary_archive, destination)
            try:
                os.chmod(destination, 0o600)
            except OSError:
                pass
        finally:
            if temporary_archive.exists():
                temporary_archive.unlink()
    return destination


def inspect_backup(archive_path: Path) -> tuple[dict, bytes]:
    """Verify archive structure, payload checksum and SQLite integrity."""
    path = Path(archive_path)
    try:
        with zipfile.ZipFile(path, "r") as archive:
            names = archive.namelist()
            if len(names) != 2 or len(set(names)) != 2 or MANIFEST_NAME not in names:
                raise BackupError("백업 파일의 내부 구성이 올바르지 않습니다.")
            if any(name.startswith(("/", "\\")) or ".." in Path(name).parts for name in names):
                raise BackupError("백업 파일에 허용되지 않는 경로가 포함되어 있습니다.")
            if archive.testzip() is not None:
                raise BackupError("백업 ZIP 내부 파일의 CRC 검증에 실패했습니다.")
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
            if manifest.get("format_version") != FORMAT_VERSION:
                raise BackupError("지원하지 않는 백업 형식 버전입니다.")
            database_type = manifest.get("database_type")
            expected_payload = (
                SQLITE_PAYLOAD if database_type == "sqlite"
                else POSTGRES_PAYLOAD if database_type == "postgresql"
                else None
            )
            if expected_payload is None or expected_payload not in names:
                raise BackupError("백업 데이터베이스 유형 또는 데이터 파일이 올바르지 않습니다.")
            payload = archive.read(expected_payload)
    except (OSError, zipfile.BadZipFile, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BackupError("백업 파일을 읽을 수 없거나 손상되었습니다.") from exc

    actual_hash = hashlib.sha256(payload).hexdigest()
    if not isinstance(manifest.get("sha256"), str) or actual_hash != manifest["sha256"]:
        raise BackupError("백업 파일 체크섬이 일치하지 않습니다.")

    if database_type == "sqlite":
        with tempfile.TemporaryDirectory(prefix="hexora-verify-") as temporary:
            temporary_db = Path(temporary) / SQLITE_PAYLOAD
            temporary_db.write_bytes(payload)
            _sqlite_integrity_check(temporary_db)
    else:
        # PostgreSQL custom archives are structurally validated with pg_restore
        # before any target database is modified.
        with tempfile.TemporaryDirectory(prefix="hexora-verify-") as temporary:
            temporary_dump = Path(temporary) / POSTGRES_PAYLOAD
            temporary_dump.write_bytes(payload)
            environment = os.environ.copy()
            _validate_postgres_dump(temporary_dump, environment)

    return manifest, payload


def restore_backup(
    archive_path: Path,
    database_type: str,
    target,
    *,
    confirm_overwrite: bool = False,
    supported_schema_version: int = 1,
) -> dict:
    """Restore only after explicit confirmation and complete archive validation."""
    if not confirm_overwrite:
        raise BackupError(
            "복구는 대상 DB를 덮어쓸 수 있습니다. --confirm-overwrite를 명시해 주세요."
        )

    manifest, payload = inspect_backup(archive_path)
    if manifest["database_type"] != database_type:
        raise BackupError("백업 DB 종류와 현재 DATABASE_TYPE이 일치하지 않습니다.")
    if int(manifest.get("schema_version", -1)) > supported_schema_version:
        raise BackupError("백업 스키마 버전이 현재 애플리케이션이 지원하는 버전보다 높습니다.")

    if database_type == "sqlite":
        target_path = Path(target).expanduser().resolve()
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if Path(str(target_path) + "-wal").exists() or Path(str(target_path) + "-shm").exists():
            raise BackupError(
                "SQLite WAL/SHM 파일이 존재합니다. 서비스를 중지하고 연결을 닫은 뒤 복구해 주세요."
            )
        temporary_path = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix=".hexora-restore-", suffix=".sqlite3",
                dir=target_path.parent, delete=False,
            ) as stream:
                temporary_path = Path(stream.name)
                stream.write(payload)
                stream.flush()
                os.fsync(stream.fileno())
            _sqlite_integrity_check(temporary_path)
            os.replace(temporary_path, target_path)
        finally:
            if temporary_path and temporary_path.exists():
                temporary_path.unlink()
    elif database_type == "postgresql":
        environment = _postgres_environment(str(target))
        executable = shutil.which("pg_restore")
        if not executable:
            raise BackupError("pg_restore를 찾지 못했습니다. PostgreSQL client 도구를 설치해 주세요.")
        with tempfile.TemporaryDirectory(prefix="hexora-restore-") as temporary:
            dump_path = Path(temporary) / POSTGRES_PAYLOAD
            dump_path.write_bytes(payload)
            _run_postgres_tool(
                [
                    executable,
                    "--clean",
                    "--if-exists",
                    "--no-owner",
                    "--no-acl",
                    "--exit-on-error",
                    "--single-transaction",
                    "--dbname",
                    environment["PGDATABASE"],
                    str(dump_path),
                ],
                environment,
                timeout=600,
            )
    else:
        raise ValueError("지원하지 않는 데이터베이스 유형입니다.")

    _verify_restored_summary(
        database_type,
        target,
        manifest.get("database_summary", {}),
    )
    return manifest
