"""Versioned, backend-aware database schema migration tracking."""

from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    sqlite_statements: tuple[str, ...] = ()
    postgresql_statements: tuple[str, ...] = ()


# Version 1 is a baseline marker: the pre-existing initializers already create
# and upgrade the current schema, so existing installations can be adopted
# without replaying destructive DDL or copying user data.
SCHEMA_MIGRATIONS = (
    SchemaMigration(version=1, name="baseline_existing_schema"),
)


def _row_version(row) -> int:
    try:
        return int(row["version"])
    except (TypeError, KeyError, IndexError):
        return int(row[0])


def _read_applied_versions(connection) -> set[int]:
    return {
        _row_version(row)
        for row in connection.execute(
            "SELECT version FROM schema_migrations ORDER BY version"
        ).fetchall()
    }


def apply_schema_migrations(
    connection,
    backend: str,
    migrations: Iterable[SchemaMigration] = SCHEMA_MIGRATIONS,
) -> None:
    """Apply pending migrations in order and record each only after commit."""
    if backend == "sqlite":
        create_tracking_table = """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    elif backend == "postgresql":
        create_tracking_table = """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
        """
    else:
        raise ValueError("backend must be 'sqlite' or 'postgresql'")

    ordered = tuple(sorted(migrations, key=lambda migration: migration.version))
    if not ordered or any(item.version < 1 for item in ordered):
        raise ValueError("At least one positive schema migration version is required.")
    if len({item.version for item in ordered}) != len(ordered):
        raise ValueError("Schema migration versions must be unique.")

    connection.execute(create_tracking_table)
    connection.commit()

    latest_supported = ordered[-1].version
    applied = _read_applied_versions(connection)
    if applied and max(applied) > latest_supported:
        raise RuntimeError(
            "Database schema version is newer than this HEXORA application supports."
        )

    for migration in ordered:
        if migration.version in applied:
            continue

        try:
            if backend == "sqlite":
                connection.execute("BEGIN IMMEDIATE")
            else:
                connection.execute("BEGIN")
                connection.execute(
                    "LOCK TABLE schema_migrations IN EXCLUSIVE MODE"
                )

            # Re-read under the write lock so concurrent app workers do not
            # apply the same migration twice.
            current_versions = _read_applied_versions(connection)
            if migration.version in current_versions:
                connection.commit()
                applied = current_versions
                continue

            statements = (
                migration.sqlite_statements
                if backend == "sqlite"
                else migration.postgresql_statements
            )
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                """
                INSERT INTO schema_migrations (version, name)
                VALUES (?, ?)
                """,
                (migration.version, migration.name),
            )
            connection.commit()
            applied.add(migration.version)
        except Exception:
            connection.rollback()
            raise
