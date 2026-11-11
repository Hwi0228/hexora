"""SQLite schema definitions and initialization.

This module owns the SQLite schema lifecycle. Connection creation and
backend selection remain in database.py.
"""

import uuid

from sqlite_schema import (
    FOLDER_COLUMNS,
    FOLDERS_SCHEMA,
    QUESTION_ADDITIONAL_COLUMNS,
    QUESTION_COLUMNS,
    QUESTION_DRAFTS_SCHEMA,
    QUESTION_LINKS_SCHEMA,
    QUESTION_NOTES_SCHEMA,
    QUESTION_REVISIONS_SCHEMA,
    QUESTIONS_SCHEMA,
    USER_COLUMNS,
    USERS_SCHEMA,
    WORKBOOK_ENTRIES_SCHEMA,
    WORKBOOK_SCHEMA,
)


def _table_columns(connection, table_name):
    return {
        row["name"]
        for row in connection.execute(f"PRAGMA table_info({table_name})")
    }

def _create_indexes(connection):
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_folders_root_name
        ON folders(user_uuid, name) WHERE parent_uuid IS NULL
        """
    )
    connection.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_folders_child_name
        ON folders(user_uuid, parent_uuid, name) WHERE parent_uuid IS NOT NULL
        """
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_questions_user_subject ON questions(user_uuid, subject)"
    )

QUESTION_REVISIONS_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_revisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    revision_number INTEGER NOT NULL,
    editor_uuid TEXT REFERENCES users(uuid) ON DELETE SET NULL,
    summary TEXT NOT NULL,
    snapshot_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(question_id, revision_number)
)
"""


def _create_question_revision_table(connection):
    connection.execute(QUESTION_REVISIONS_SCHEMA)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_revisions_question "
        "ON question_revisions(question_id, revision_number DESC)"
    )

QUESTION_DRAFTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_drafts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uuid TEXT NOT NULL REFERENCES users(uuid) ON DELETE CASCADE,
    draft_key TEXT NOT NULL,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    base_revision INTEGER,
    payload_json TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_uuid, draft_key)
)
"""

QUESTION_ADDITIONAL_COLUMNS = {
    "difficulty": "TEXT NOT NULL DEFAULT '중'",
    "question_type": "TEXT NOT NULL DEFAULT '단답형'",
    "points": "INTEGER NOT NULL DEFAULT 4",
    "course": "TEXT NOT NULL DEFAULT ''",
    "curriculum": "TEXT NOT NULL DEFAULT '2015 개정 교육과정'",
    "achievement_standard": "TEXT NOT NULL DEFAULT ''",
    "source_type": "TEXT NOT NULL DEFAULT '기타'",
    "exam": "TEXT NOT NULL DEFAULT ''",
    "original_question_number": "TEXT NOT NULL DEFAULT ''",
    "source_url": "TEXT NOT NULL DEFAULT ''",
    "license": "TEXT NOT NULL DEFAULT ''",
    "title": "TEXT NOT NULL DEFAULT ''",
    "deleted_at": "TEXT",
}


def _ensure_question_additional_columns(connection):
    columns = _table_columns(connection, "questions")
    for name, definition in QUESTION_ADDITIONAL_COLUMNS.items():
        if name not in columns:
            connection.execute(
                f"ALTER TABLE questions ADD COLUMN {name} {definition}"
            )


def _create_question_drafts_table(connection):
    connection.execute(QUESTION_DRAFTS_SCHEMA)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_drafts_owner "
        "ON question_drafts(user_uuid, updated_at DESC)"
    )

QUESTION_NOTES_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uuid TEXT NOT NULL REFERENCES users(uuid) ON DELETE CASCADE,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    note TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(user_uuid, question_id)
)
"""


def _create_question_notes_table(connection):
    connection.execute(QUESTION_NOTES_SCHEMA)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_notes_user "
        "ON question_notes(user_uuid, question_id)"
    )


WORKBOOK_SCHEMA = """
CREATE TABLE IF NOT EXISTS workbooks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    kind TEXT NOT NULL CHECK (kind IN ('commercial', 'community')),
    title TEXT NOT NULL,
    publisher TEXT NOT NULL DEFAULT '',
    authors TEXT NOT NULL DEFAULT '',
    isbn TEXT NOT NULL DEFAULT '',
    edition TEXT NOT NULL DEFAULT '',
    publication_year INTEGER,
    subject TEXT NOT NULL DEFAULT '',
    grade TEXT NOT NULL DEFAULT '',
    curriculum TEXT NOT NULL DEFAULT '',
    description TEXT NOT NULL DEFAULT '',
    created_by TEXT REFERENCES users(uuid) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

WORKBOOK_ENTRIES_SCHEMA = """
CREATE TABLE IF NOT EXISTS workbook_entries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    workbook_id INTEGER NOT NULL REFERENCES workbooks(id) ON DELETE CASCADE,
    question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    unit TEXT NOT NULL DEFAULT '',
    page INTEGER,
    question_number TEXT NOT NULL DEFAULT '',
    created_by TEXT REFERENCES users(uuid) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK (question_id IS NOT NULL OR page IS NOT NULL OR question_number <> '')
)
"""

QUESTION_LINKS_SCHEMA = """
CREATE TABLE IF NOT EXISTS question_links (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    question_id INTEGER NOT NULL REFERENCES questions(id) ON DELETE CASCADE,
    related_question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
    workbook_entry_id INTEGER REFERENCES workbook_entries(id) ON DELETE CASCADE,
    relation_type TEXT NOT NULL CHECK (relation_type IN ('variant', 'similar')),
    created_by TEXT REFERENCES users(uuid) ON DELETE SET NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CHECK ((related_question_id IS NULL) <> (workbook_entry_id IS NULL)),
    CHECK (related_question_id IS NULL OR related_question_id <> question_id)
)
"""


def _create_workbook_tables(connection):
    connection.execute(WORKBOOK_SCHEMA)
    connection.execute(WORKBOOK_ENTRIES_SCHEMA)
    connection.execute(QUESTION_LINKS_SCHEMA)
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workbooks_kind_title ON workbooks(kind, title)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_workbook_entries_workbook ON workbook_entries(workbook_id, id)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_workbook_entries_question "
        "ON workbook_entries(workbook_id, question_id) WHERE question_id IS NOT NULL"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_links_question ON question_links(question_id, relation_type)"
    )
    connection.execute(
        "CREATE INDEX IF NOT EXISTS idx_question_links_related ON question_links(related_question_id, relation_type)"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_question_links_question_target "
        "ON question_links(question_id, related_question_id, relation_type) "
        "WHERE related_question_id IS NOT NULL"
    )
    connection.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_question_links_workbook_target "
        "ON question_links(question_id, workbook_entry_id, relation_type) "
        "WHERE workbook_entry_id IS NOT NULL"
    )


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
