import sqlite3
import tempfile
import unittest
from pathlib import Path

from app import app


class AdminBootstrapCommandTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        self.original_testing = app.config.get("TESTING", False)
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "admin-bootstrap.sqlite3"),
            SECRET_KEY="admin-bootstrap-test-secret",
        )

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        app.config["TESTING"] = self.original_testing
        self.temp_directory.cleanup()

    def signup(self, email):
        client = app.test_client()
        client.get("/signup")
        with client.session_transaction() as session:
            token = session["csrf_token"]
        response = client.post(
            "/signup",
            data={
                "_csrf_token": token,
                "email": email,
                "display_name": "일반 가입자",
                "password": "long-test-password",
                "password_confirm": "long-test-password",
                "terms_agreed": "1",
                "privacy_agreed": "1",
            },
        )
        self.assertEqual(response.status_code, 302)

    def roles(self):
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            return connection.execute(
                "SELECT email, role FROM users ORDER BY email"
            ).fetchall()

    def invoke_bootstrap(self, email="owner@example.com"):
        return app.test_cli_runner().invoke(
            [
                "create-admin",
                "--email", email,
                "--display-name", "HEXORA 운영자",
            ],
            input="SecureAdminPassword123!\\nSecureAdminPassword123!\\n",
        )

    def test_public_first_signup_never_receives_admin_role(self):
        self.signup("member@example.com")
        self.assertEqual(self.roles(), [("member@example.com", "user")])

    def test_cli_creates_first_admin_on_empty_database(self):
        result = self.invoke_bootstrap()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertIn("최초 관리자 계정을 생성했습니다", result.output)
        self.assertEqual(self.roles(), [("owner@example.com", "admin")])

    def test_cli_can_promote_an_existing_user_explicitly(self):
        self.signup("owner@example.com")
        result = self.invoke_bootstrap()
        self.assertEqual(result.exit_code, 0, result.output)
        self.assertEqual(self.roles(), [("owner@example.com", "admin")])

    def test_second_bootstrap_is_rejected_without_creating_another_admin(self):
        first = self.invoke_bootstrap()
        second = self.invoke_bootstrap("another@example.com")
        self.assertEqual(first.exit_code, 0, first.output)
        self.assertNotEqual(second.exit_code, 0)
        self.assertIn("이미 존재", second.output)
        self.assertEqual(self.roles(), [("owner@example.com", "admin")])


if __name__ == "__main__":
    unittest.main()
