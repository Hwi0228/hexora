import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app import app


class GPTActionsOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp.name) / "gpt-actions.sqlite3"),
            SECRET_KEY="gpt-actions-test-secret",
        )
        self.redirect_uri = "https://chatgpt.com/aip/test-gpt/oauth/callback"
        self.environment = patch.dict(os.environ, {
            "HEXORA_ACTIONS_CLIENT_ID": "test-actions-client",
            "HEXORA_ACTIONS_CLIENT_SECRET": "test-actions-client-secret",
            "HEXORA_ACTIONS_REDIRECT_URIS": self.redirect_uri,
        })
        self.environment.start()
        self.client = app.test_client()
        self.client.get("/signup")
        with self.client.session_transaction() as session:
            csrf = session["csrf_token"]
        signup = self.client.post("/signup", data={
            "_csrf_token": csrf,
            "email": "gpt-actions@example.com",
            "display_name": "GPT Actions Test",
            "password": "long-test-password",
            "password_confirm": "long-test-password",
            "terms_agreed": "1",
            "privacy_agreed": "1",
        })
        self.assertEqual(signup.status_code, 302)
        self.client.get("/actions/oauth/authorize", query_string={
            "client_id": "test-actions-client",
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "questions:read questions:write",
            "state": "test-state",
        })
        with self.client.session_transaction() as session:
            self.user_uuid = session["user_uuid"]
            self.csrf = session["csrf_token"]

    def tearDown(self):
        self.environment.stop()
        app.config["DATABASE"] = self.original_database
        self.temp.cleanup()

    def authorize_and_exchange(self, scope="questions:read questions:write"):
        params = {
            "client_id": "test-actions-client",
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": scope,
            "state": "test-state",
        }
        page = self.client.get("/actions/oauth/authorize", query_string=params)
        self.assertEqual(page.status_code, 200)
        approved = self.client.post("/actions/oauth/authorize", data={
            **params,
            "decision": "allow",
            "_csrf_token": self.csrf,
        })
        self.assertEqual(approved.status_code, 302)
        callback = parse_qs(urlparse(approved.location).query)
        self.assertEqual(callback["state"][0], "test-state")
        exchanged = self.client.post("/actions/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": "test-actions-client",
            "client_secret": "test-actions-client-secret",
            "redirect_uri": self.redirect_uri,
            "code": callback["code"][0],
        })
        self.assertEqual(exchanged.status_code, 200)
        return exchanged.json["access_token"]

    def question(self):
        return {
            "subject": "수학",
            "grade": "고2",
            "course": "수학Ⅱ",
            "curriculum": "2015 개정 교육과정",
            "prompt": "<p>도함수를 구하여라. $x^2$</p>",
            "answer": "$2x$",
            "source_type": "직접 제작",
            "license": "ORIGINAL",
            "choices": ["첫 번째", "두 번째"],
            "passage": "<p>함수 $f(x)=x^2$</p>",
            "examples": "<p>보기</p>",
        }

    def test_oauth_authorization_and_direct_api_access(self):
        token = self.authorize_and_exchange()
        unauthorized = self.client.get("/api/v1/questions")
        self.assertEqual(unauthorized.status_code, 401)

        search = self.client.get(
            "/api/v1/questions",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json["count"], 0)

        created = self.client.post(
            "/api/v1/questions",
            json={"question": self.question()},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json["code"], "000001")

        detail = self.client.get(
            "/api/v1/questions/000001",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["question"]["answer"], "$2x$")

    def test_read_only_scope_cannot_register_questions(self):
        token = self.authorize_and_exchange("questions:read")
        response = self.client.post(
            "/api/v1/questions",
            json={"question": self.question()},
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(response.status_code, 403)

    def test_oauth_rejects_unregistered_redirect_and_wrong_client_secret(self):
        bad_redirect = self.client.get("/actions/oauth/authorize", query_string={
            "client_id": "test-actions-client",
            "redirect_uri": "https://attacker.example/callback",
            "response_type": "code",
            "scope": "questions:read",
            "state": "state",
        })
        self.assertEqual(bad_redirect.status_code, 400)
        bad_client = self.client.post("/actions/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": "test-actions-client",
            "client_secret": "wrong-secret",
            "code": "invalid",
            "redirect_uri": self.redirect_uri,
        })
        self.assertEqual(bad_client.status_code, 401)


if __name__ == "__main__":
    unittest.main()
