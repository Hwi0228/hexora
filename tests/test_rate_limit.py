import tempfile
import unittest
from pathlib import Path

from app import app


class PublicWriteRateLimitTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original = {
            key: app.config.get(key)
            for key in (
                "DATABASE", "TESTING", "RATE_LIMIT_LOGIN_IP_MAX",
                "RATE_LIMIT_LOGIN_ACCOUNT_MAX", "RATE_LIMIT_LOGIN_WINDOW_SECONDS",
                "RATE_LIMIT_SIGNUP_IP_MAX", "RATE_LIMIT_SIGNUP_WINDOW_SECONDS",
                "RATE_LIMIT_REPORT_IP_MAX", "RATE_LIMIT_REPORT_WINDOW_SECONDS",
            )
        }
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "rate-limit.sqlite3"),
            SECRET_KEY="rate-limit-tests-secret-key",
            RATE_LIMIT_LOGIN_IP_MAX=100,
            RATE_LIMIT_LOGIN_ACCOUNT_MAX=2,
            RATE_LIMIT_LOGIN_WINDOW_SECONDS=900,
            RATE_LIMIT_SIGNUP_IP_MAX=2,
            RATE_LIMIT_SIGNUP_WINDOW_SECONDS=3600,
            RATE_LIMIT_REPORT_IP_MAX=2,
            RATE_LIMIT_REPORT_WINDOW_SECONDS=3600,
        )
        self.client = app.test_client()

    def tearDown(self):
        app.config.update(self.original)
        self.temp_directory.cleanup()

    def _csrf(self, path):
        self.client.get(path)
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def test_login_limit_combines_ip_and_normalized_account_identifier(self):
        token = self._csrf("/login")
        payload = {
            "_csrf_token": token,
            "email": "Unknown@Example.com",
            "password": "incorrect",
        }
        self.assertEqual(self.client.post("/login", data=payload).status_code, 400)
        self.assertEqual(self.client.post("/login", data=payload).status_code, 400)
        limited = self.client.post("/login", data=payload)
        self.assertEqual(limited.status_code, 429)
        self.assertTrue(limited.headers["Retry-After"].isdigit())
        self.assertEqual(limited.headers["Cache-Control"], "no-store")

    def test_signup_limit_is_applied_before_validation(self):
        token = self._csrf("/signup")
        payload = {"_csrf_token": token}
        self.assertEqual(self.client.post("/signup", data=payload).status_code, 400)
        self.assertEqual(self.client.post("/signup", data=payload).status_code, 400)
        self.assertEqual(self.client.post("/signup", data=payload).status_code, 429)

    def test_rights_report_limit_is_applied_before_validation(self):
        token = self._csrf("/report/request")
        payload = {"_csrf_token": token}
        self.assertEqual(
            self.client.post("/report/request", data=payload).status_code, 400
        )
        self.assertEqual(
            self.client.post("/report/request", data=payload).status_code, 400
        )
        self.assertEqual(
            self.client.post("/report/request", data=payload).status_code, 429
        )

    def test_forwarded_for_header_is_not_used_as_the_client_identity(self):
        from flask import request

        with app.test_request_context(
            "/login", method="POST",
            headers={"X-Forwarded-For": "203.0.113.99"},
            environ_base={"REMOTE_ADDR": "127.0.0.1"},
        ):
            self.assertEqual(request.remote_addr, "127.0.0.1")


if __name__ == "__main__":
    unittest.main()
