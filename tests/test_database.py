"""Tests for database connection and schema initialization lifecycle."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from flask import Flask

from database import close_db, get_db


class DatabaseInitializationTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        self.database_path = Path(self.temp_directory.name) / "hexora.sqlite3"
        self.app = Flask(__name__)
        self.app.config.update(
            DATABASE_TYPE="sqlite",
            DATABASE=str(self.database_path),
        )

    def tearDown(self):
        self.temp_directory.cleanup()

    def _open_and_close_connection(self):
        with self.app.app_context():
            connection = get_db()
            self.assertIsNotNone(connection)
            close_db()

    def test_file_database_schema_is_initialized_once_for_multiple_connections(self):
        with patch("database.initialize_database") as initialize:
            self._open_and_close_connection()
            self._open_and_close_connection()

        initialize.assert_called_once()

    def test_in_memory_database_schema_is_initialized_for_each_connection(self):
        self.app.config["DATABASE"] = ":memory:"
        with patch("database.initialize_database") as initialize:
            self._open_and_close_connection()
            self._open_and_close_connection()

        self.assertEqual(initialize.call_count, 2)


if __name__ == "__main__":
    unittest.main()
