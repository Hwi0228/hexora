import sqlite3
import unittest

from schema_migrations import SchemaMigration, apply_schema_migrations
from sqlite_backend import initialize_database


class _Cursor:
    def __init__(self, rows=()):
        self.rows = rows

    def fetchall(self):
        return self.rows


class _FakePostgresConnection:
    def __init__(self):
        self.versions = set()
        self.statements = []
        self.commits = 0
        self.rollbacks = 0

    def execute(self, statement, parameters=()):
        normalized = " ".join(statement.split())
        self.statements.append((normalized, parameters))
        if normalized.startswith("SELECT version FROM schema_migrations"):
            return _Cursor([{"version": value} for value in sorted(self.versions)])
        if normalized.startswith("INSERT INTO schema_migrations"):
            self.versions.add(int(parameters[0]))
        return _Cursor()

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


class SchemaMigrationTests(unittest.TestCase):
    def test_existing_sqlite_schema_is_adopted_as_baseline_without_data_loss(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        try:
            initialize_database(connection)
            connection.execute(
                "INSERT INTO users (uuid, email, display_name, password_hash, role) "
                "VALUES ('u1', 'member@example.com', 'Member', 'hash', 'user')"
            )
            connection.commit()

            apply_schema_migrations(connection, "sqlite")
            apply_schema_migrations(connection, "sqlite")

            versions = connection.execute(
                "SELECT version, name FROM schema_migrations"
            ).fetchall()
            user_count = connection.execute("SELECT COUNT(*) FROM users").fetchone()[0]
            self.assertEqual([(row["version"], row["name"]) for row in versions],
                             [(1, "baseline_existing_schema")])
            self.assertEqual(user_count, 1)
        finally:
            connection.close()

    def test_migrations_run_in_order_and_are_idempotent(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        migrations = (
            SchemaMigration(1, "baseline"),
            SchemaMigration(
                2,
                "add_migration_probe",
                sqlite_statements=(
                    "CREATE TABLE migration_probe (id INTEGER PRIMARY KEY, value TEXT)",
                ),
                postgresql_statements=(
                    "CREATE TABLE migration_probe (id BIGINT PRIMARY KEY, value TEXT)",
                ),
            ),
        )
        try:
            apply_schema_migrations(connection, "sqlite", migrations)
            apply_schema_migrations(connection, "sqlite", migrations)
            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]
            self.assertEqual(versions, [1, 2])
            self.assertIsNotNone(
                connection.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='migration_probe'"
                ).fetchone()
            )
        finally:
            connection.close()

    def test_failed_migration_rolls_back_its_version_record(self):
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        migrations = (
            SchemaMigration(1, "baseline"),
            SchemaMigration(
                2,
                "failing_migration",
                sqlite_statements=("CREATE TABLE broken (",),
                postgresql_statements=("CREATE TABLE broken (",),
            ),
        )
        try:
            with self.assertRaises(sqlite3.OperationalError):
                apply_schema_migrations(connection, "sqlite", migrations)
            versions = [
                row["version"]
                for row in connection.execute(
                    "SELECT version FROM schema_migrations ORDER BY version"
                ).fetchall()
            ]
            self.assertEqual(versions, [1])
        finally:
            connection.close()

    def test_postgresql_uses_its_backend_specific_ddl(self):
        connection = _FakePostgresConnection()
        migrations = (
            SchemaMigration(
                1,
                "backend_specific",
                sqlite_statements=("SQLITE_DDL",),
                postgresql_statements=("POSTGRESQL_DDL",),
            ),
        )
        apply_schema_migrations(connection, "postgresql", migrations)
        statements = [statement for statement, _ in connection.statements]
        self.assertIn("POSTGRESQL_DDL", statements)
        self.assertNotIn("SQLITE_DDL", statements)
        self.assertEqual(connection.versions, {1})


if __name__ == "__main__":
    unittest.main()
