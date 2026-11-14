"""SQLite table definitions and schema metadata."""

USER_COLUMNS = {"uuid", "email", "display_name", "password_hash", "role", "created_at"}

FOLDER_COLUMNS = {"uuid", "user_uuid", "name", "parent_uuid", "created_at"}

QUESTION_COLUMNS = {
    "id",
    "user_uuid",
    "folder_uuid",
    "subject",
    "grade",
    "unit",
    "passage",
    "prompt",
    "examples",
    "choices",
    "answer",
    "source",
    "year",
    "page",
    "created_at",
}

USERS_SCHEMA = """
CREATE TABLE users (
    uuid TEXT PRIMARY KEY,
    email TEXT NOT NULL UNIQUE COLLATE NOCASE,
    display_name TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    role TEXT NOT NULL CHECK (role IN ('admin', 'user')),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

FOLDERS_SCHEMA = """
CREATE TABLE folders (
    uuid TEXT PRIMARY KEY,
    user_uuid TEXT REFERENCES users(uuid) ON DELETE CASCADE,
    name TEXT NOT NULL,
    parent_uuid TEXT REFERENCES folders(uuid) ON DELETE RESTRICT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""

QUESTIONS_SCHEMA = """
CREATE TABLE questions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_uuid TEXT REFERENCES users(uuid) ON DELETE CASCADE,
    folder_uuid TEXT REFERENCES folders(uuid) ON DELETE SET NULL,
    subject TEXT NOT NULL,
    grade TEXT NOT NULL,
    unit TEXT NOT NULL,
    passage TEXT NOT NULL DEFAULT '',
    prompt TEXT NOT NULL,
    examples TEXT NOT NULL DEFAULT '',
    choices TEXT NOT NULL DEFAULT '[]',
    answer TEXT NOT NULL,
    explanation TEXT NOT NULL DEFAULT '',
    source TEXT NOT NULL,
    year INTEGER,
    page INTEGER,
    difficulty TEXT NOT NULL DEFAULT '중',
    question_type TEXT NOT NULL DEFAULT '단답형',
    points INTEGER NOT NULL DEFAULT 4,
    course TEXT NOT NULL DEFAULT '',
    curriculum TEXT NOT NULL DEFAULT '2015 개정 교육과정',
    achievement_standard TEXT NOT NULL DEFAULT '',
    source_type TEXT NOT NULL DEFAULT '기타',
    exam TEXT NOT NULL DEFAULT '',
    original_question_number TEXT NOT NULL DEFAULT '',
    source_url TEXT NOT NULL DEFAULT '',
    license TEXT NOT NULL DEFAULT '',
    title TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


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


RIGHTS_REPORTS_SCHEMA = """
CREATE TABLE IF NOT EXISTS rights_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    requested_action TEXT NOT NULL,
    requester_role TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    target_url TEXT NOT NULL,
    details TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT '접수',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
)
"""


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
