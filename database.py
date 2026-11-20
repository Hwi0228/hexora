"""Database connection lifecycle and backend selection."""

import sqlite3
import threading
from pathlib import Path

from flask import current_app, g

from sqlite_backend import (
    USER_COLUMNS, FOLDER_COLUMNS, QUESTION_COLUMNS,
    USERS_SCHEMA, FOLDERS_SCHEMA, QUESTIONS_SCHEMA,
    _table_columns, _create_indexes,
    QUESTION_REVISIONS_SCHEMA, _create_question_revision_table,
    QUESTION_DRAFTS_SCHEMA, QUESTION_ADDITIONAL_COLUMNS,
    _ensure_question_additional_columns, _create_question_drafts_table,
    QUESTION_NOTES_SCHEMA, _create_question_notes_table,
    WORKBOOK_SCHEMA, WORKBOOK_ENTRIES_SCHEMA, QUESTION_LINKS_SCHEMA,
    _create_workbook_tables, initialize_database,
)
from postgres_backend import (
    HybridRow,
    PostgresConnection,
    PostgresCursor,
    _translate_qmark_placeholders,
)
from postgres_schema import POSTGRES_SCHEMA_STATEMENTS, initialize_postgres_database


# Schema initialization is process-local and keyed by the actual database.
# SQLite's in-memory databases are connection-local, so they must be initialized
# for every connection.
_SCHEMA_INITIALIZATION_LOCK = threading.Lock()
_INITIALIZED_DATABASES = set()


def _schema_initialization_key(backend, database):
    if backend == "postgresql":
        return backend, database

    if database == ":memory:":
        return None

    database_path = Path(database).resolve()
    try:
        stat = database_path.stat()
    except OSError:
        # The connection has already been opened, so this is only a defensive
        # fallback for unusual SQLite URI/path configurations.
        return backend, str(database_path)

    # Including the inode prevents a deleted and recreated SQLite file at the
    # same path from incorrectly inheriting the previous file's ready state.
    return backend, str(database_path), stat.st_dev, stat.st_ino


def _initialize_schema_once(connection, backend, database):
    key = _schema_initialization_key(backend, database)
    if key is None:
        initialize_database(connection)
        return

    if key in _INITIALIZED_DATABASES:
        return

    with _SCHEMA_INITIALIZATION_LOCK:
        if key in _INITIALIZED_DATABASES:
            return

        if backend == "postgresql":
            initialize_postgres_database(connection)
        else:
            initialize_database(connection)

        # Mark ready only after the initializer has completed successfully.
        _INITIALIZED_DATABASES.add(key)


def begin_write_transaction(connection, lock_table=None):
    """Start a write transaction using the selected backend's transaction model."""
    if getattr(connection, "backend", "sqlite") == "postgresql":
        from psycopg.pq import TransactionStatus

        if connection.raw.info.transaction_status == TransactionStatus.IDLE:
            connection.execute("BEGIN")
        if lock_table:
            if lock_table not in {"users", "questions"}:
                raise ValueError("Unsupported transaction lock table.")
            connection.execute(f"LOCK TABLE {lock_table} IN EXCLUSIVE MODE")
        return

    connection.execute("BEGIN IMMEDIATE")


def is_integrity_error(error):
    if isinstance(error, sqlite3.IntegrityError):
        return True
    try:
        import psycopg
    except ImportError:
        return False
    return isinstance(error, psycopg.IntegrityError)


def get_db():
    if "db" not in g:
        if current_app.config["DATABASE_TYPE"] == "postgresql":
            import psycopg
            from psycopg.rows import dict_row

            database_url = current_app.config["DATABASE_URL"]
            if database_url.startswith("postgres://"):
                database_url = "postgresql://" + database_url[len("postgres://"):]
            raw_connection = psycopg.connect(
                database_url,
                row_factory=dict_row,
                connect_timeout=10,
            )
            connection = PostgresConnection(raw_connection)
            try:
                _initialize_schema_once(connection, "postgresql", database_url)
            except Exception:
                connection.close()
                raise
            g.db = connection
        else:
            database = current_app.config["DATABASE"]
            Path(database).parent.mkdir(parents=True, exist_ok=True)
            connection = sqlite3.connect(database)
            connection.row_factory = sqlite3.Row
            try:
                _initialize_schema_once(connection, "sqlite", database)
                connection.execute("PRAGMA foreign_keys = ON")
            except Exception:
                connection.close()
                raise
            g.db = connection
    return g.db


def close_db(_error=None):
    connection = g.pop("db", None)
    if connection is not None:
        if _error is not None:
            connection.rollback()
        connection.close()
