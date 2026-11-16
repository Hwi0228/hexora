import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app


class McpApiTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.original_database = app.config["DATABASE"]
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "mcp-api.sqlite3"),
            SECRET_KEY="mcp-api-test-secret",
        )
        self.client = app.test_client()
        self.environment = patch.dict(os.environ, {
            "HEXORA_MCP_API_TOKEN": "test-api-token",
            "HEXORA_MCP_SERVICE_USER_UUID": "",
        })
        self.environment.start()

        self.client.get("/signup")
        with self.client.session_transaction() as session:
            csrf_token = session["csrf_token"]
        response = self.client.post("/signup", data={
            "_csrf_token": csrf_token,
            "email": "mcp-owner@example.com",
            "display_name": "MCP 서비스 테스트",
            "password": "long-test-password",
            "password_confirm": "long-test-password",
            "terms_agreed": "1",
            "privacy_agreed": "1",
        })
        self.assertEqual(response.status_code, 302)
        with self.client.session_transaction() as session:
            self.service_user_uuid = session["user_uuid"]
        os.environ["HEXORA_MCP_SERVICE_USER_UUID"] = self.service_user_uuid
        self.headers = {"Authorization": "Bearer test-api-token"}

    def tearDown(self):
        self.environment.stop()
        app.config["DATABASE"] = self.original_database
        self.temp_directory.cleanup()

    def question(self, **overrides):
        payload = {
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
        payload.update(overrides)
        return payload

    def query_one(self, sql, params=()):
        with sqlite3.connect(app.config["DATABASE"]) as connection:
            return connection.execute(sql, params).fetchone()[0]

    def test_mcp_routes_require_bearer_token_without_redirecting_to_login(self):
        response = self.client.get("/api/integrations/mcp/health")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(
            self.client.get(
                "/api/integrations/mcp/health", headers=self.headers
            ).status_code,
            200,
        )

    def test_question_can_be_validated_and_created_with_revision(self):
        payload = self.question()
        validated = self.client.post(
            "/api/integrations/mcp/questions/validate",
            json=payload,
            headers=self.headers,
        )
        self.assertEqual(validated.status_code, 200)
        self.assertTrue(validated.json["valid"])

        created = self.client.post(
            "/api/integrations/mcp/questions",
            json={"question": payload},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)
        self.assertEqual(created.json["code"], "000001")
        self.assertEqual(self.query_one("SELECT COUNT(*) FROM question_revisions"), 1)
        self.assertEqual(self.query_one("SELECT passage FROM questions"), "<p>함수 $f(x)=x^2$</p>")
        self.assertEqual(self.query_one("SELECT examples FROM questions"), "<p>보기</p>")

    def test_created_question_is_searchable_and_retrievable_by_base36_code(self):
        payload = self.question()
        created = self.client.post(
            "/api/integrations/mcp/questions",
            json={"question": payload},
            headers=self.headers,
        )
        self.assertEqual(created.status_code, 201)

        search = self.client.get(
            "/api/integrations/mcp/questions?query=도함수&course=수학Ⅱ",
            headers=self.headers,
        )
        self.assertEqual(search.status_code, 200)
        self.assertEqual(search.json["count"], 1)
        self.assertEqual(search.json["questions"][0]["code"], "000001")

        detail = self.client.get(
            "/api/integrations/mcp/questions/000001",
            headers=self.headers,
        )
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["question"]["answer"], "$2x$")

    def test_standards_endpoint_filters_by_course(self):
        response = self.client.get(
            "/api/integrations/mcp/standards?curriculum=2015%20개정%20교육과정&course=수학Ⅱ",
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertGreater(response.json["count"], 0)
        self.assertEqual(response.json["standards"][0]["course"], "수학Ⅱ")

    def test_invalid_payload_is_rejected(self):
        response = self.client.post(
            "/api/integrations/mcp/questions",
            json={"question": {"subject": "수학"}},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json["created"])


if __name__ == "__main__":
    unittest.main()
