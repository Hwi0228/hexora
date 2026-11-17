import base64
import hashlib
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from app import app


class OAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp.name) / "oauth.sqlite3"),
            SECRET_KEY="oauth-test-secret",
        )
        self.env = patch.dict(os.environ, {"HEXORA_MCP_API_TOKEN": "internal-test-token"})
        self.env.start()
        self.client = app.test_client()
        self.client.get("/signup")
        with self.client.session_transaction() as session:
            csrf = session["csrf_token"]
        response = self.client.post("/signup", data={
            "_csrf_token": csrf,
            "email": "oauth-test@example.com",
            "display_name": "OAuth Test",
            "password": "long-test-password",
            "password_confirm": "long-test-password",
            "terms_agreed": "1",
            "privacy_agreed": "1",
        })
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.user_uuid = session["user_uuid"]
            session["csrf_token"] = "oauth-test-csrf"
            self.csrf = session["csrf_token"]

    def tearDown(self):
        self.env.stop()
        app.config["DATABASE"] = self.original_database
        self.temp.cleanup()

    def test_metadata_and_dynamic_client_registration(self):
        metadata = self.client.get("/.well-known/oauth-authorization-server")
        self.assertEqual(metadata.status_code, 200)
        self.assertIn("authorization_code", metadata.json["grant_types_supported"])
        registered = self.client.post("/oauth/register", json={
            "client_name": "Test MCP Client",
            "redirect_uris": ["https://client.example/callback"],
            "token_endpoint_auth_method": "none",
        })
        self.assertEqual(registered.status_code, 201)
        self.assertTrue(registered.json["client_id"])

    def test_authorization_code_pkce_exchange_and_introspection(self):
        registered = self.client.post("/oauth/register", json={
            "client_name": "Test MCP Client",
            "redirect_uris": ["https://client.example/callback"],
            "token_endpoint_auth_method": "none",
        })
        client_id = registered.json["client_id"]
        verifier = "a" * 43
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode()).digest()
        ).decode().rstrip("=")
        query = {
            "client_id": client_id,
            "redirect_uri": "https://client.example/callback",
            "response_type": "code",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "questions:read questions:write",
            "state": "test-state",
        }
        page = self.client.get("/oauth/authorize", query_string=query)
        self.assertEqual(page.status_code, 200)
        self.assertIn('action="/oauth/authorize"', page.get_data(as_text=True))
        self.assertIn('type=submit name=decision value=allow', page.get_data(as_text=True))
        with self.client.session_transaction() as session:
            request_id = next(iter(session["oauth_pending_authorizations"]))
        form = {
            "request_id": request_id,
            "decision": "allow",
            "_csrf_token": self.csrf,
        }
        approved = self.client.post("/oauth/authorize", data=form)
        self.assertEqual(approved.status_code, 302)
        returned = parse_qs(urlparse(approved.location).query)
        self.assertEqual(returned["state"][0], "test-state")

        replayed = self.client.post("/oauth/authorize", data=form)
        self.assertEqual(replayed.status_code, 302)
        replay_returned = parse_qs(urlparse(replayed.location).query)
        self.assertEqual(replay_returned["state"][0], "test-state")
        self.assertNotEqual(replay_returned["code"][0], returned["code"][0])

        exchanged = self.client.post("/oauth/token", data={
            "grant_type": "authorization_code",
            "client_id": client_id,
            "redirect_uri": "https://client.example/callback",
            "code": replay_returned["code"][0],
            "code_verifier": verifier,
        })
        self.assertEqual(exchanged.status_code, 200)
        access_token = exchanged.json["access_token"]
        inspected = self.client.post(
            "/oauth/introspect",
            headers={"Authorization": "Bearer internal-test-token"},
            data={"token": access_token},
        )
        self.assertEqual(inspected.status_code, 200)
        self.assertTrue(inspected.json["active"])
        self.assertEqual(inspected.json["sub"], self.user_uuid)


if __name__ == "__main__":
    unittest.main()
