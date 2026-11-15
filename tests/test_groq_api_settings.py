import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cryptography.fernet import Fernet

from app import app
from database import get_db
from groq_key_routes import get_user_groq_api_key


class GroqApiSettingsTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.encryption_key = Fernet.generate_key().decode("ascii")
        self.environment = patch.dict(
            os.environ,
            {"GROQ_KEY_ENCRYPTION_KEY": self.encryption_key},
            clear=False,
        )
        self.environment.start()
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "groq-byok.sqlite3"),
            SECRET_KEY="groq-byok-test-secret",
        )
        self.client = app.test_client()
        self.client.get("/signup")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        response = self.client.post(
            "/signup",
            data={
                "_csrf_token": token,
                "email": "groq-byok@example.test",
                "display_name": "Groq BYOK Test",
                "password": "long-test-password",
                "password_confirm": "long-test-password",
            },
        )
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.user_uuid = session["user_uuid"]

    def tearDown(self):
        self.environment.stop()
        self.temp_directory.cleanup()

    def csrf_token(self):
        self.client.get("/settings/api-keys")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def test_key_is_encrypted_per_user_and_never_rendered(self):
        api_key = "gsk_test_user_specific_secret_key"
        response = self.client.post(
            "/settings/api-keys",
            data={
                "_csrf_token": self.csrf_token(),
                "action": "save",
                "groq_api_key": api_key,
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertIn("saved=1", response.headers["Location"])

        with app.app_context():
            row = get_db().execute(
                "SELECT groq_api_key_encrypted FROM user_api_credentials WHERE user_uuid = ?",
                (self.user_uuid,),
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertNotIn(api_key, row["groq_api_key_encrypted"])
            self.assertEqual(get_user_groq_api_key(self.user_uuid), api_key)

        page = self.client.get("/settings/api-keys")
        self.assertEqual(page.status_code, 200)
        self.assertNotIn(api_key.encode("utf-8"), page.data)
        self.assertIn("개인 API 키 등록됨".encode("utf-8"), page.data)

    def test_key_can_be_replaced_and_deleted(self):
        first_key = "gsk_first_user_key_secret"
        second_key = "gsk_second_user_key_secret"
        for api_key in (first_key, second_key):
            response = self.client.post(
                "/settings/api-keys",
                data={
                    "_csrf_token": self.csrf_token(),
                    "action": "save",
                    "groq_api_key": api_key,
                },
            )
            self.assertEqual(response.status_code, 302)

        with app.app_context():
            self.assertEqual(get_user_groq_api_key(self.user_uuid), second_key)

        response = self.client.post(
            "/settings/api-keys",
            data={"_csrf_token": self.csrf_token(), "action": "delete"},
        )
        self.assertEqual(response.status_code, 302)
        with app.app_context():
            self.assertIsNone(get_user_groq_api_key(self.user_uuid))


if __name__ == "__main__":
    unittest.main()
