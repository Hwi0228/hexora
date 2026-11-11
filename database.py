"""Database connection lifecycle and backend selection."""

import sqlite3
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
    POSTGRES_SCHEMA_STATEMENTS,
    PostgresConnection,
    PostgresCursor,
    _translate_qmark_placeholders,
    initialize_postgres_database,
)


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
                initialize_postgres_database(connection)
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
                initialize_database(connection)
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
