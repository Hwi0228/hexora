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
