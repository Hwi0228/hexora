import json
import sqlite3
import tempfile
import unittest
import uuid
from pathlib import Path

from app import app


class AdminDatabaseResetTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        self.original_testing = app.config.get("TESTING", False)
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "reset.sqlite3"),
            SECRET_KEY="database-reset-test-secret",
        )
        self.admin = app.test_client()
        self.register(self.admin, "reset-admin@example.com", "초기화 관리자")
        self.admin_uuid = self.user_uuid("reset-admin@example.com")

        self.member = app.test_client()
        self.register(self.member, "reset-member@example.com", "일반 사용자")
        self.member_uuid = self.user_uuid("reset-member@example.com")

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        app.config["TESTING"] = self.original_testing
        self.temp_directory.cleanup()

    def register(self, client, email, name):
        client.get("/signup")
        with client.session_transaction() as session:
            token = session["csrf_token"]
        response = client.post(
            "/signup",
            data={
                "_csrf_token": token,
                "email": email,
                "display_name": name,
                "password": "long-test-password",
                "password_confirm": "long-test-password",
                "terms_agreed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

    def user_uuid(self, email):
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            return connection.execute(
                "SELECT uuid FROM users WHERE email = ?", (email,)
            ).fetchone()[0]

    def csrf_post(self, client, path, data):
        client.get(path)
        with client.session_transaction() as session:
            token = session["csrf_token"]
        payload = dict(data)
        payload["_csrf_token"] = token
        return client.post(path, data=payload)

    def seed_service_data(self):
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            connection.execute("PRAGMA foreign_keys = ON")
            root_folder = str(uuid.uuid4())
            child_folder = str(uuid.uuid4())
            connection.execute(
                "INSERT INTO folders (uuid, user_uuid, name) VALUES (?, ?, ?)",
                (root_folder, self.admin_uuid, "관리자 폴더"),
            )
            connection.execute(
                "INSERT INTO folders (uuid, user_uuid, name, parent_uuid) VALUES (?, ?, ?, ?)",
                (child_folder, self.admin_uuid, "하위 폴더", root_folder),
            )
            connection.execute(
                "INSERT INTO folders (uuid, user_uuid, name) VALUES (?, ?, ?)",
                (str(uuid.uuid4()), self.member_uuid, "일반 사용자 폴더"),
            )
            cursor = connection.execute(
                """
                INSERT INTO questions (
                    user_uuid, folder_uuid, subject, grade, unit,
                    prompt, answer, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    self.admin_uuid, child_folder, "수학", "고2", "미분",
                    "초기화 대상 문제", "정답", "테스트 출처",
                ),
            )
            question_id = cursor.lastrowid
            connection.execute(
                """
                INSERT INTO question_revisions (
                    question_id, revision_number, editor_uuid, summary, snapshot_json
                ) VALUES (?, 1, ?, ?, ?)
                """,
                (question_id, self.admin_uuid, "최초 등록", json.dumps({"prompt": "초기화 대상 문제"})),
            )
            connection.execute(
                """
                INSERT INTO question_drafts (user_uuid, draft_key, payload_json)
                VALUES (?, ?, ?)
                """,
                (self.admin_uuid, "draft-1", "{}"),
            )
            connection.execute(
                """
                INSERT INTO question_notes (user_uuid, question_id, note)
                VALUES (?, ?, ?)
                """,
                (self.admin_uuid, question_id, "개인 메모"),
            )
            workbook = connection.execute(
                "INSERT INTO workbooks (kind, title) VALUES (?, ?)",
                ("community", "초기화 대상 문제집"),
            ).lastrowid
            entry = connection.execute(
                """
                INSERT INTO workbook_entries (workbook_id, question_id, page)
                VALUES (?, ?, ?)
                """,
                (workbook, question_id, 1),
            ).lastrowid
            connection.execute(
                """
                INSERT INTO question_links (
                    question_id, workbook_entry_id, relation_type, created_by
                ) VALUES (?, ?, ?, ?)
                """,
                (question_id, entry, "variant", self.admin_uuid),
            )
            connection.execute(
                """
                INSERT INTO rights_reports (
                    category, requested_action, requester_role, requester_name,
                    requester_email, target_url, details
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "기타 권리침해", "삭제 요청", "권리자 본인",
                    "신고자", "reporter@example.com",
                    "https://hexora.kro.kr/questions", "신고 내용",
                ),
            )

    def count(self, table):
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            return connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]

    def test_reset_page_is_admin_only(self):
        response = self.member.get("/admin/database-reset")
        self.assertEqual(response.status_code, 403)
        self.assertEqual(self.admin.get("/admin/database-reset").status_code, 200)

    def test_wrong_confirmation_does_not_delete_anything(self):
        self.seed_service_data()
        response = self.csrf_post(
            self.admin,
            "/admin/database-reset",
            {"confirmation": "초기화", "acknowledge_irreversible": "1"},
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(self.count("questions"), 1)
        self.assertEqual(self.count("users"), 2)

    def test_reset_deletes_service_data_and_members_but_preserves_admin(self):
        self.seed_service_data()
        response = self.csrf_post(
            self.admin,
            "/admin/database-reset",
            {
                "confirmation": "초기화 실행",
                "acknowledge_irreversible": "1",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("completed=1", response.headers["Location"])

        with sqlite3.connect(app.config["DATABASE"]) as connection:
            users = connection.execute(
                "SELECT uuid, role FROM users"
            ).fetchall()
        self.assertEqual(users, [(self.admin_uuid, "admin")])

        for table in (
            "questions",
            "folders",
            "question_revisions",
            "question_drafts",
            "question_notes",
            "workbooks",
            "workbook_entries",
            "question_links",
            "rights_reports",
        ):
            self.assertEqual(self.count(table), 0, table)

        page = self.admin.get("/admin/database-reset")
        self.assertEqual(page.status_code, 200)
        self.assertIn("초기화가 완료되었습니다".encode(), page.data)
        self.assertIn("초기화 관리자".encode(), page.data)


if __name__ == "__main__":
    unittest.main()
