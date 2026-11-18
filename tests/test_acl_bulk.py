import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import app


class BulkAclTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        self.original_testing = app.config.get("TESTING", False)
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "acl-bulk.sqlite3"),
            SECRET_KEY="acl-bulk-test-secret",
        )
        result = app.test_cli_runner().invoke(
            args=[
                "create-admin",
                "--email", "admin@example.com",
                "--display-name", "HEXORA 관리자",
            ],
            input="SecureAdminPassword123!\nSecureAdminPassword123!\n",
        )
        self.assertEqual(result.exit_code, 0, result.output)
        self.admin = app.test_client()
        self.login(self.admin, "admin@example.com")
        self.user = app.test_client()
        self.signup(self.user)
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            self.user_uuid = connection.execute(
                "SELECT uuid FROM users WHERE email = ?",
                ("member@example.com",),
            ).fetchone()[0]

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        app.config["TESTING"] = self.original_testing
        self.temp_directory.cleanup()

    def csrf(self, client):
        with client.session_transaction() as session:
            return session["csrf_token"]

    def login(self, client, email):
        client.get("/login")
        response = client.post(
            "/login",
            data={
                "_csrf_token": self.csrf(client),
                "email": email,
                "password": "SecureAdminPassword123!",
            },
        )
        self.assertEqual(response.status_code, 302)

    def signup(self, client):
        client.get("/signup")
        response = client.post(
            "/signup",
            data={
                "_csrf_token": self.csrf(client),
                "email": "member@example.com",
                "display_name": "일반 사용자",
                "password": "long-test-password",
                "password_confirm": "long-test-password",
                "terms_agreed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

    def grant(self, permission, effect="allow", target_type="user"):
        self.admin.get("/admin/acl")
        data = {
            "_csrf_token": self.csrf(self.admin),
            "target_type": target_type,
            "user_uuid": self.user_uuid if target_type == "user" else "",
            "target_role": "user",
            "permission_code": permission,
            "effect": effect,
        }
        response = self.admin.post("/admin/acl", data=data)
        self.assertEqual(response.status_code, 302)

    def sample_document(self):
        return {
            "version": "1.0",
            "questions": [
                {
                    "subject": "수학",
                    "grade": "고2",
                    "course": "수학Ⅱ",
                    "curriculum": "2015 개정 교육과정",
                    "unit": "적분",
                    "prompt": "다음 적분을 계산하시오. $\\int x\\,dx$",
                    "answer": "$\\frac{x^2}{2}+C$",
                    "explanation": "",
                    "choices": [],
                    "source_type": "직접 제작",
                    "license": "ORIGINAL",
                }
            ],
        }

    def test_bulk_routes_are_denied_without_explicit_permission(self):
        self.assertEqual(self.user.get("/questions/bulk").status_code, 403)
        self.assertEqual(self.user.get("/questions/export.json").status_code, 403)

    def test_role_policy_can_grant_and_user_override_can_deny(self):
        self.grant("questions.bulk_import", target_type="role")
        self.assertEqual(self.user.get("/questions/bulk").status_code, 200)
        self.grant("questions.bulk_import", effect="deny")
        self.assertEqual(self.user.get("/questions/bulk").status_code, 403)

    def test_json_import_preview_transaction_and_export(self):
        self.grant("questions.bulk_import")
        self.grant("questions.bulk_export")
        preview = self.user.post(
            "/questions/bulk",
            data={
                "_csrf_token": self.csrf(self.user),
                "file": (
                    io.BytesIO(json.dumps(self.sample_document(), ensure_ascii=False).encode("utf-8")),
                    "questions.json",
                ),
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(preview.status_code, 200)
        self.assertIn("등록 미리보기", preview.get_data(as_text=True))

        imported = self.user.post(
            "/questions/bulk",
            data={
                "_csrf_token": self.csrf(self.user),
                "mode": "import",
                "payload": json.dumps(self.sample_document(), ensure_ascii=False),
            },
        )
        self.assertEqual(imported.status_code, 200)
        self.assertIn("등록 완료: 1개", imported.get_data(as_text=True))

        exported = self.user.get("/questions/export.json")
        self.assertEqual(exported.status_code, 200)
        payload = json.loads(exported.get_data(as_text=True))
        self.assertEqual(payload["version"], "1.0")
        self.assertEqual(len(payload["questions"]), 1)
        self.assertEqual(payload["questions"][0]["subject"], "수학")

    def test_partial_import_requires_separate_permission(self):
        self.grant("questions.bulk_import")
        response = self.user.post(
            "/questions/bulk",
            data={
                "_csrf_token": self.csrf(self.user),
                "mode": "import",
                "partial": "1",
                "payload": json.dumps(self.sample_document(), ensure_ascii=False),
            },
        )
        self.assertEqual(response.status_code, 403)


if __name__ == "__main__":
    unittest.main()
