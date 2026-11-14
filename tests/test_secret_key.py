import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app import _is_production_environment, _secret_key, _validate_secret_key


class SecretKeyConfigurationTests(unittest.TestCase):
    def test_production_environment_is_detected_from_hexora_env(self):
        with patch.dict("os.environ", {"HEXORA_ENV": "production"}, clear=True):
            self.assertTrue(_is_production_environment())

    def test_render_deployment_is_detected_without_flask_env(self):
        with patch.dict("os.environ", {"RENDER": "true"}, clear=True):
            self.assertTrue(_is_production_environment())

    def test_development_environment_is_not_production(self):
        with patch.dict("os.environ", {"HEXORA_ENV": "development"}, clear=True):
            self.assertFalse(_is_production_environment())

    def test_missing_key_fails_in_production_without_generating_a_file(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(config={"SECRET_KEY": None}, instance_path=directory)
            with patch.dict("os.environ", {"HEXORA_ENV": "production"}, clear=True):
                with self.assertRaisesRegex(RuntimeError, "required in production"):
                    _secret_key(app)
            self.assertFalse((Path(directory) / ".secret_key").exists())

    def test_development_generates_and_reuses_a_persistent_key(self):
        with tempfile.TemporaryDirectory() as directory:
            app = SimpleNamespace(config={"SECRET_KEY": None}, instance_path=directory)
            with patch.dict("os.environ", {"HEXORA_ENV": "development"}, clear=True):
                first = _secret_key(app)
                second = _secret_key(app)
            self.assertEqual(first, second)
            self.assertEqual(len(first), 64)
            self.assertTrue((Path(directory) / ".secret_key").is_file())

    def test_short_key_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "at least 32 characters"):
            _validate_secret_key("short")

    def test_low_diversity_key_is_rejected(self):
        with self.assertRaisesRegex(RuntimeError, "character-diversity"):
            _validate_secret_key("a" * 64)

    def test_cryptographically_random_style_key_is_accepted(self):
        self.assertEqual(
            _validate_secret_key("aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL"),
            "aB3dE5gH7jK9mN2pQ4sT6vW8xY1zC0fL",
        )


if __name__ == "__main__":
    unittest.main()
