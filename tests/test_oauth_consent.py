import base64
import hashlib
import tempfile
import unittest
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from app import app


class OAuthConsentBindingTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        self.original_secret_key = app.config["SECRET_KEY"]
        self.original_testing = app.config["TESTING"]
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "oauth-consent.sqlite3"),
            SECRET_KEY="oauth-consent-test-secret",
        )
        self.client = app.test_client()

        self.client.get("/signup")
        with self.client.session_transaction() as session:
            csrf_token = session["csrf_token"]
        signup = self.client.post("/signup", data={
            "_csrf_token": csrf_token,
            "email": "oauth-consent@example.com",
            "display_name": "OAuth consent test",
            "password": "long-test-password",
            "password_confirm": "long-test-password",
            "terms_agreed": "1",
            "privacy_agreed": "1",
        })
        self.assertEqual(signup.status_code, 302)

        registration = self.client.post("/oauth/register", json={
            "client_name": "HEXORA MCP test",
            "redirect_uris": ["https://client.example/callback"],
            "token_endpoint_auth_method": "none",
        })
        self.assertEqual(registration.status_code, 201)
        self.client_id = registration.json["client_id"]
        self.redirect_uri = "https://client.example/callback"

    def tearDown(self):
        app.config["DATABASE"] = self.original_database
        app.config["SECRET_KEY"] = self.original_secret_key
        app.config["TESTING"] = self.original_testing
        self.temp_directory.cleanup()

    def test_post_cannot_escalate_scope_after_consent_page(self):
        verifier = "v" * 43
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("utf-8")).digest()
        ).decode("ascii").rstrip("=")

        consent = self.client.get("/oauth/authorize", query_string={
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": "state-from-client",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "questions:read",
        })
        self.assertEqual(consent.status_code, 200)

        with self.client.session_transaction() as session:
            csrf_token = session["csrf_token"]
            pending = session["oauth_pending_authorizations"]
            request_id = next(iter(pending))

        # A modified hidden field must not grant a scope the user did not see.
        approved = self.client.post("/oauth/authorize", data={
            "_csrf_token": csrf_token,
            "request_id": request_id,
            "decision": "allow",
            "scope": "questions:read questions:write",
        })
        self.assertEqual(approved.status_code, 302)
        callback = urlsplit(approved.location)
        callback_params = parse_qs(callback.query)
        self.assertEqual(callback_params["state"], ["state-from-client"])

        token_response = self.client.post("/oauth/token", json={
            "grant_type": "authorization_code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "code": callback_params["code"][0],
            "code_verifier": verifier,
        })
        self.assertEqual(token_response.status_code, 200)
        self.assertEqual(token_response.json["scope"], "questions:read")

    def test_consent_request_is_single_use(self):
        verifier = "w" * 43
        challenge = base64.urlsafe_b64encode(
            hashlib.sha256(verifier.encode("utf-8")).digest()
        ).decode("ascii").rstrip("=")
        self.client.get("/oauth/authorize", query_string={
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "state": "one-time-state",
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "scope": "questions:read",
        })
        with self.client.session_transaction() as session:
            csrf_token = session["csrf_token"]
            request_id = next(iter(session["oauth_pending_authorizations"]))

        first = self.client.post("/oauth/authorize", data={
            "_csrf_token": csrf_token,
            "request_id": request_id,
            "decision": "deny",
        })
        second = self.client.post("/oauth/authorize", data={
            "_csrf_token": csrf_token,
            "request_id": request_id,
            "decision": "allow",
        })

        self.assertEqual(first.status_code, 302)
        self.assertEqual(second.status_code, 400)


if __name__ == "__main__":
    unittest.main()
