import os
import unittest
from unittest.mock import patch

from app import create_app
from database import (
    POSTGRES_SCHEMA_STATEMENTS,
    HybridRow,
    PostgresConnection,
    _translate_qmark_placeholders,
)


class _FakeCursor:
    def fetchone(self):
        return {"id": 17, "label": "row"}

    def fetchall(self):
        return [{"id": 17}, {"id": 18}]


class _FakeConnection:
    def __init__(self):
        self.calls = []

    def execute(self, statement, parameters=()):
        self.calls.append((statement, parameters))
        return _FakeCursor()


class DatabaseBackendConfigurationTests(unittest.TestCase):
    def test_sqlite_remains_the_default_backend(self):
        with patch.dict(os.environ, {"FLASK_SECRET_KEY": "test"}, clear=True):
            app = create_app()
        self.assertEqual(app.config["DATABASE_TYPE"], "sqlite")
        self.assertEqual(app.config["DATABASE"], os.path.join(app.instance_path, "probocr.sqlite3"))

    def test_postgres_backend_requires_a_database_url(self):
        with patch.dict(os.environ, {"DATABASE_TYPE": "postgresql", "FLASK_SECRET_KEY": "test"}, clear=True):
            with self.assertRaisesRegex(RuntimeError, "DATABASE_URL"):
                create_app()

    def test_postgres_backend_accepts_database_url(self):
        with patch.dict(
            os.environ,
            {
                "DATABASE_TYPE": "postgresql",
                "DATABASE_URL": "postgresql://user:password@example.test/neondb",
                "FLASK_SECRET_KEY": "test",
            },
            clear=True,
        ):
            app = create_app()
        self.assertEqual(app.config["DATABASE_TYPE"], "postgresql")
        self.assertEqual(app.config["DATABASE_URL"], "postgresql://user:password@example.test/neondb")

    def test_unknown_backend_is_rejected(self):
        with patch.dict(os.environ, {"DATABASE_TYPE": "mysql", "FLASK_SECRET_KEY": "test"}, clear=True):
            with self.assertRaisesRegex(ValueError, "DATABASE_TYPE"):
                create_app()

    def test_qmark_translation_ignores_quoted_text_and_comments(self):
        sql = "SELECT ? AS value, '?' AS literal, \"?\" AS ident -- ?\nWHERE id = ?"
        self.assertEqual(
            _translate_qmark_placeholders(sql),
            "SELECT %s AS value, '?' AS literal, \"?\" AS ident -- ?\nWHERE id = %s",
        )

    def test_postgres_connection_adapter_preserves_row_access(self):
        raw = _FakeConnection()
        connection = PostgresConnection(raw)
        cursor = connection.execute("SELECT * FROM users WHERE uuid = ?", ("user-1",))
        row = cursor.fetchone()
        self.assertEqual(raw.calls, [("SELECT * FROM users WHERE uuid = %s", ("user-1",))])
        self.assertEqual(row["id"], 17)
        self.assertEqual(row[0], 17)
        self.assertEqual(cursor.fetchall()[1]["id"], 18)

    def test_postgres_schema_includes_all_application_tables(self):
        schema = "\n".join(POSTGRES_SCHEMA_STATEMENTS)
        for table in (
            "users",
            "folders",
            "questions",
            "question_revisions",
            "question_drafts",
            "question_notes",
        ):
            self.assertIn(f"CREATE TABLE IF NOT EXISTS {table}", schema)
        self.assertNotIn("PRAGMA", schema)
        self.assertNotIn("AUTOINCREMENT", schema)


if __name__ == "__main__":
    unittest.main()


class DatabaseBackendParityIntegrationTests(unittest.TestCase):
    """Run the same CRUD, FK, and rollback contract against both backends."""

    def test_shared_data_lifecycle_on_sqlite_and_postgresql(self):
        import tempfile
        import uuid
        from pathlib import Path
        from flask import Flask
        from database import close_db, get_db

        backends = [("sqlite", None)]
        postgres_url = os.environ.get("HEXORA_TEST_POSTGRES_URL", "").strip()
        if postgres_url:
            backends.append(("postgresql", postgres_url))

        with tempfile.TemporaryDirectory() as directory:
            for backend, database_url in backends:
                with self.subTest(backend=backend):
                    environment = {
                        "DATABASE_TYPE": backend,
                        "FLASK_SECRET_KEY": "database-parity-test-secret",
                    }
                    if backend == "sqlite":
                        environment["DATABASE_PATH"] = str(Path(directory) / "parity.sqlite3")
                    else:
                        environment["DATABASE_URL"] = database_url
                    with patch.dict(os.environ, environment, clear=False):
                        app = create_app()
                    app.config.update(TESTING=True)
                    user_id = str(uuid.uuid4())
                    try:
                        with app.app_context():
                            connection = get_db()
                            connection.execute(
                                "INSERT INTO users (uuid, email, display_name, password_hash, role) "
                                "VALUES (?, ?, ?, ?, 'user')",
                                (user_id, f"parity-{user_id}@example.test", "Parity", "hash"),
                            )
                            folder_id = str(uuid.uuid4())
                            connection.execute(
                                "INSERT INTO folders (uuid, user_uuid, name) VALUES (?, ?, ?)",
                                (folder_id, user_id, "Parity folder"),
                            )
                            cursor = connection.execute(
                                """INSERT INTO questions
                                   (user_uuid, folder_uuid, subject, grade, unit, prompt, answer, source)
                                   VALUES (?, ?, '수학', '고1', '테스트', '문제', '정답', '테스트')
                                   RETURNING id""",
                                (user_id, folder_id),
                            )
                            question_id = cursor.fetchone()["id"]
                            connection.execute(
                                """INSERT INTO question_revisions
                                   (question_id, revision_number, editor_uuid, summary, snapshot_json)
                                   VALUES (?, 1, ?, '최초 등록', '{}')""",
                                (question_id, user_id),
                            )
                            connection.execute(
                                """INSERT INTO question_drafts
                                   (user_uuid, draft_key, question_id, base_revision, payload_json)
                                   VALUES (?, ?, ?, 1, '{}')""",
                                (user_id, f"question:{question_id}", question_id),
                            )
                            workbook_cursor = connection.execute(
                                "INSERT INTO workbooks (kind, title, created_by) VALUES ('community', 'Parity', ?) RETURNING id",
                                (user_id,),
                            )
                            workbook_id = workbook_cursor.fetchone()["id"]
                            connection.execute(
                                "INSERT INTO workbook_entries (workbook_id, question_id, unit) VALUES (?, ?, '테스트')",
                                (workbook_id, question_id),
                            )
                            connection.execute(
                                """INSERT INTO rights_reports
                                   (category, requested_action, requester_role, requester_name,
                                    requester_email, target_url, details)
                                   VALUES ('copyright', 'review', 'author', 'Parity', ?, '/', 'test')""",
                                (f"parity-{user_id}@example.test",),
                            )
                            connection.commit()

                            self.assertEqual(
                                connection.execute("SELECT prompt FROM questions WHERE id = ?", (question_id,)).fetchone()[0],
                                "문제",
                            )
                            self.assertEqual(
                                connection.execute("SELECT COUNT(*) FROM question_revisions WHERE question_id = ?", (question_id,)).fetchone()[0],
                                1,
                            )
                            self.assertEqual(
                                connection.execute("SELECT COUNT(*) FROM question_drafts WHERE user_uuid = ?", (user_id,)).fetchone()[0],
                                1,
                            )
                            self.assertEqual(
                                connection.execute("SELECT COUNT(*) FROM workbook_entries WHERE workbook_id = ?", (workbook_id,)).fetchone()[0],
                                1,
                            )

                            connection.execute("DELETE FROM users WHERE uuid = ?", (user_id,))
                            connection.commit()
                            for table, column, value in (
                                ("questions", "id", question_id),
                                ("folders", "uuid", folder_id),
                                ("question_revisions", "question_id", question_id),
                                ("question_drafts", "user_uuid", user_id),
                            ):
                                self.assertEqual(
                                    connection.execute(f"SELECT COUNT(*) FROM {table} WHERE {column} = ?", (value,)).fetchone()[0],
                                    0,
                                    msg=f"{backend}: cascade cleanup failed for {table}",
                                )
                            # A failed transaction must not leave a partially written row.
                            connection.execute(
                                "INSERT INTO users (uuid, email, display_name, password_hash, role) VALUES (?, ?, ?, ?, 'user')",
                                (str(uuid.uuid4()), f"rollback-{user_id}@example.test", "Rollback", "hash"),
                            )
                            connection.rollback()
                            self.assertEqual(
                                connection.execute("SELECT COUNT(*) FROM users WHERE email = ?", (f"rollback-{user_id}@example.test",)).fetchone()[0],
                                0,
                            )
                    finally:
                        with app.app_context():
                            close_db()


if __name__ == "__main__":
    unittest.main()
