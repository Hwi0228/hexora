import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import create_app


class ObservabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.app = create_app()
        self.app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "health.sqlite3"),
            SECRET_KEY="observability-tests-secret-key",
        )
        self.client = self.app.test_client()

    def tearDown(self):
        self.temp_directory.cleanup()

    def test_liveness_does_not_open_database(self):
        with patch("database.get_db", side_effect=AssertionError("database accessed")):
            response = self.client.get("/health/live")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "alive"})
        self.assertTrue(response.headers.get("X-Request-ID"))

    def test_readiness_checks_database_and_reports_failure(self):
        response = self.client.get("/health/ready")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.get_json(), {"status": "ready"})

        with patch("database.get_db", side_effect=OSError("private database URL must not leak")):
            failed = self.client.get("/health/ready")
        self.assertEqual(failed.status_code, 503)
        self.assertEqual(failed.get_json(), {"status": "not_ready"})

    def test_json_formatter_uses_allowlisted_fields_only(self):
        from observability import JsonLogFormatter
        import logging

        record = logging.LogRecord("hexora", logging.INFO, __file__, 1, "request", (), None)
        record.request_id = "abc123"
        record.password = "must-not-be-logged"
        record.database_url = "postgres://secret"
        rendered = JsonLogFormatter().format(record)
        payload = json.loads(rendered)
        self.assertEqual(payload["request_id"], "abc123")
        self.assertNotIn("password", payload)
        self.assertNotIn("database_url", payload)


if __name__ == "__main__":
    unittest.main()
