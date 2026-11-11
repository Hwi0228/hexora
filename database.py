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


def initialize_database(connection):
    connection.execute("PRAGMA foreign_keys = OFF")
    tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        )
    }
    user_columns = _table_columns(connection, "users") if "users" in tables else set()
    folder_columns = _table_columns(connection, "folders") if "folders" in tables else set()
    question_columns = _table_columns(connection, "questions") if "questions" in tables else set()

    if "users" not in tables:
        connection.execute(USERS_SCHEMA)

    if FOLDER_COLUMNS.issubset(folder_columns) and QUESTION_COLUMNS.issubset(question_columns):
        if "explanation" not in question_columns:
            connection.execute(
                "ALTER TABLE questions ADD COLUMN explanation TEXT NOT NULL DEFAULT ''"
            )
        _ensure_question_additional_columns(connection)
        _create_indexes(connection)
        _create_question_revision_table(connection)
        _create_question_drafts_table(connection)
        _create_question_notes_table(connection)
        _create_workbook_tables(connection)
        connection.commit()
        connection.execute("PRAGMA foreign_keys = ON")
        return

    legacy_folders = (
        [dict(row) for row in connection.execute("SELECT * FROM folders")]
        if "folders" in tables
        else []
    )
    legacy_questions = (
        [dict(row) for row in connection.execute("SELECT * FROM questions")]
        if "questions" in tables
        else []
    )

    connection.execute("BEGIN IMMEDIATE")
    try:
        if "users" in tables and not USER_COLUMNS.issubset(user_columns):
            connection.execute("DROP TABLE users")
            connection.execute(USERS_SCHEMA)

        folder_uuid_map = {}
        for folder in legacy_folders:
            old_key = folder.get("uuid", folder.get("id"))
            folder_uuid_map[str(old_key)] = folder.get("uuid") or str(uuid.uuid4())

        if "questions" in tables:
            connection.execute("DROP TABLE questions")
        if "folders" in tables:
            connection.execute("DROP TABLE folders")

        connection.execute(FOLDERS_SCHEMA)
        connection.execute(QUESTIONS_SCHEMA)

        for folder in legacy_folders:
            old_parent = folder.get("parent_uuid", folder.get("parent_id"))
            parent_uuid = (
                folder_uuid_map.get(str(old_parent))
                if old_parent is not None
                else None
            )
            connection.execute(
                """
                INSERT INTO folders (uuid, user_uuid, name, parent_uuid, created_at)
                VALUES (?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                (
                    folder_uuid_map[str(folder.get("uuid", folder.get("id")))],
                    folder.get("user_uuid"),
                    folder.get("name", ""),
                    parent_uuid,
                    folder.get("created_at"),
                ),
            )

        for question in legacy_questions:
            legacy_folder_ref = question.get(
                "folder_uuid", question.get("folder_id")
            )
            folder_uuid = (
                folder_uuid_map.get(str(legacy_folder_ref))
                if legacy_folder_ref is not None
                else None
            )
            connection.execute(
                """
                INSERT INTO questions (
                    id, user_uuid, folder_uuid, subject, grade, unit, passage,
                    prompt, examples, choices, answer, explanation, source, year,
                    page, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, COALESCE(?, CURRENT_TIMESTAMP))
                """,
                (
                    question.get("id"),
                    question.get("user_uuid"),
                    folder_uuid,
                    question.get("subject", ""),
                    question.get("grade", ""),
                    question.get("unit", question.get("topic", "")),
                    question.get("passage", ""),
                    question.get("prompt", ""),
                    question.get("examples", ""),
                    question.get("choices", "[]"),
                    question.get("answer", ""),
                    question.get("explanation", ""),
                    question.get("source", ""),
                    question.get("year"),
                    question.get("page"),
                    question.get("created_at"),
                ),
            )

        _ensure_question_additional_columns(connection)
        _create_indexes(connection)
        _create_question_revision_table(connection)
        _create_question_drafts_table(connection)
        _create_question_notes_table(connection)
        _create_workbook_tables(connection)
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.execute("PRAGMA foreign_keys = ON")

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
