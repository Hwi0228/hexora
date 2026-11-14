import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch
import subprocess

from backup_restore import (
    BackupError,
    create_backup,
    inspect_backup,
    restore_backup,
    _postgres_environment,
)


class DatabaseBackupRestoreTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.database = self.root / "source.sqlite3"
        with sqlite3.connect(self.database) as connection:
            connection.execute(
                "CREATE TABLE sample (id INTEGER PRIMARY KEY, value TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO sample(value) VALUES ('보존 데이터')")
            connection.execute(
                "CREATE TABLE users (id INTEGER PRIMARY KEY, email TEXT UNIQUE NOT NULL)"
            )
            connection.execute("INSERT INTO users(email) VALUES ('student@example.test')")
            connection.execute(
                "CREATE TABLE questions (id INTEGER PRIMARY KEY, title TEXT NOT NULL)"
            )
            connection.execute("INSERT INTO questions(title) VALUES ('sample question')")
            connection.execute(
                "CREATE TABLE question_revisions (id INTEGER PRIMARY KEY, question_id INTEGER NOT NULL REFERENCES questions(id))"
            )
            connection.execute("INSERT INTO question_revisions(question_id) VALUES (1)")

    def tearDown(self):
        self.temporary.cleanup()

    def test_sqlite_backup_contains_metadata_checksum_and_valid_database(self):
        output = create_backup("sqlite", self.database, output=self.root / "backup.zip", schema_version=0)
        manifest, payload = inspect_backup(output)
        self.assertEqual(manifest["database_type"], "sqlite")
        self.assertEqual(manifest["schema_version"], 1)
        self.assertEqual(len(manifest["sha256"]), 64)
        self.assertEqual(
            manifest["database_summary"]["counts"],
            {"users": 1, "questions": 1, "question_revisions": 1},
        )
        with tempfile.NamedTemporaryFile(suffix=".sqlite3") as stream:
            stream.write(payload)
            stream.flush()
            with sqlite3.connect(stream.name) as connection:
                self.assertEqual(connection.execute("SELECT value FROM sample").fetchone()[0], "보존 데이터")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM question_revisions").fetchone()[0], 1)

    def test_sqlite_restore_requires_confirmation_and_replaces_target_atomically(self):
        output = create_backup("sqlite", self.database, output=self.root / "backup.zip", schema_version=1)
        target = self.root / "target.sqlite3"
        with sqlite3.connect(target) as connection:
            connection.execute("CREATE TABLE old_data (value TEXT)")
            connection.execute("INSERT INTO old_data VALUES ('remove me')")

        with self.assertRaisesRegex(BackupError, "confirm-overwrite"):
            restore_backup(output, "sqlite", target)
        restore_backup(output, "sqlite", target, confirm_overwrite=True, supported_schema_version=0)
        with sqlite3.connect(target) as connection:
            self.assertEqual(connection.execute("SELECT value FROM sample").fetchone()[0], "보존 데이터")
            self.assertIsNone(connection.execute(
                "SELECT name FROM sqlite_master WHERE name='old_data'"
            ).fetchone())

    def test_corrupted_payload_checksum_is_rejected_before_restore(self):
        output = create_backup("sqlite", self.database, output=self.root / "backup.zip", schema_version=1)
        rewritten = self.root / "corrupt.zip"
        with zipfile.ZipFile(output) as source:
            manifest = json.loads(source.read("manifest.json"))
            payload = source.read("database.sqlite3") + b"corruption"
        with zipfile.ZipFile(rewritten, "w") as target:
            target.writestr("manifest.json", json.dumps(manifest))
            target.writestr("database.sqlite3", payload)
        with self.assertRaisesRegex(BackupError, "체크섬"):
            inspect_backup(rewritten)

    def test_restore_rejects_database_type_and_newer_schema_mismatch(self):
        output = create_backup("sqlite", self.database, output=self.root / "backup.zip", schema_version=2)
        with self.assertRaisesRegex(BackupError, "DB 종류"):
            restore_backup(output, "postgresql", "postgresql://u:p@localhost/db", confirm_overwrite=True)
        with self.assertRaisesRegex(BackupError, "스키마 버전"):
            restore_backup(output, "sqlite", self.root / "target.sqlite3", confirm_overwrite=True, supported_schema_version=1)

    def test_postgres_url_credentials_are_passed_via_environment_not_arguments(self):
        environment = _postgres_environment(
            "postgresql://hexora:secret%21@db.example:5433/mathdb?sslmode=require"
        )
        self.assertEqual(environment["PGUSER"], "hexora")
        self.assertEqual(environment["PGPASSWORD"], "secret!")
        self.assertEqual(environment["PGHOST"], "db.example")
        self.assertEqual(environment["PGPORT"], "5433")
        self.assertEqual(environment["PGDATABASE"], "mathdb")
        self.assertEqual(environment["PGSSLMODE"], "require")

    @patch("backup_restore.shutil.which", side_effect=lambda name: f"/usr/bin/{name}")
    @patch("backup_restore.subprocess.run")
    def test_postgres_backup_and_restore_use_pg_dump_and_pg_restore(self, run, which):
        def fake_run(command, **kwargs):
            if command[0].endswith("pg_dump"):
                Path(command[command.index("--file") + 1]).write_bytes(b"custom-format-dump")
            return subprocess.CompletedProcess(command, 0, "", "")

        run.side_effect = fake_run
        output = create_backup(
            "postgresql",
            "postgresql://user:password@localhost/db",
            output=self.root / "postgres.zip",
            schema_version=1,
        )
        manifest, payload = inspect_backup(output)
        self.assertEqual(manifest["database_type"], "postgresql")
        self.assertEqual(payload, b"custom-format-dump")
        self.assertEqual(manifest["database_summary"]["counts"], {})
        restore_backup(
            output,
            "postgresql",
            "postgresql://user:password@localhost/db",
            confirm_overwrite=True,
            supported_schema_version=1,
        )
        commands = [call.args[0][0] for call in run.call_args_list]
        self.assertIn("/usr/bin/pg_dump", commands)
        self.assertGreaterEqual(commands.count("/usr/bin/pg_restore"), 2)
        dump_call = next(call for call in run.call_args_list if call.args[0][0].endswith("pg_dump"))
        self.assertNotIn("password", " ".join(dump_call.args[0]))


if __name__ == "__main__":
    unittest.main()
