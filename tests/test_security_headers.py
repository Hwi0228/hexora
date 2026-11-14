import os
import unittest
from unittest.mock import patch

from app import create_app
from werkzeug.middleware.proxy_fix import ProxyFix


class ProductionSecurityDefaultsTests(unittest.TestCase):
    def test_production_enables_secure_session_cookies_and_proxy_scheme(self):
        with patch.dict(
            os.environ,
            {
                "HEXORA_ENV": "production",
                "FLASK_SECRET_KEY": "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL",
            },
            clear=True,
        ):
            app = create_app()

        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])
        self.assertTrue(app.config["SESSION_COOKIE_HTTPONLY"])
        self.assertEqual(app.config["SESSION_COOKIE_SAMESITE"], "Lax")
        self.assertIsInstance(app.wsgi_app, ProxyFix)

    def test_render_enables_secure_cookie_defaults(self):
        with patch.dict(
            os.environ,
            {
                "RENDER": "true",
                "FLASK_SECRET_KEY": "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL",
            },
            clear=True,
        ):
            app = create_app()

        self.assertTrue(app.config["SESSION_COOKIE_SECURE"])

    def test_development_http_keeps_secure_cookie_disabled_by_default(self):
        with patch.dict(
            os.environ,
            {"HEXORA_ENV": "development", "FLASK_SECRET_KEY": "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL"},
            clear=True,
        ):
            app = create_app()

        self.assertFalse(app.config["SESSION_COOKIE_SECURE"])

    def test_security_headers_are_present_and_allow_required_quill_cdn(self):
        with patch.dict(
            os.environ,
            {
                "HEXORA_ENV": "production",
                "FLASK_SECRET_KEY": "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL",
            },
            clear=True,
        ):
            app = create_app()
            response = app.test_client().get("/login")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(response.headers["X-Frame-Options"], "DENY")
        self.assertEqual(
            response.headers["Referrer-Policy"], "strict-origin-when-cross-origin"
        )
        self.assertIn("camera=()", response.headers["Permissions-Policy"])
        csp = response.headers["Content-Security-Policy"]
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertIn("https://cdn.jsdelivr.net", csp)
        self.assertEqual(
            response.headers["Strict-Transport-Security"],
            "max-age=31536000; includeSubDomains",
        )

    def test_hsts_is_not_sent_in_development(self):
        with patch.dict(
            os.environ,
            {"HEXORA_ENV": "development", "FLASK_SECRET_KEY": "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL"},
            clear=True,
        ):
            app = create_app()
            response = app.test_client().get("/login")

        self.assertNotIn("Strict-Transport-Security", response.headers)


if __name__ == "__main__":
    unittest.main()
