import json

from database import get_db
from question_constants import QUESTION_CONTENT_FIELDS


def _question_snapshot(question):
    snapshot = {field: question[field] for field in QUESTION_CONTENT_FIELDS}
    raw_choices = snapshot.get("choices") or "[]"
    if isinstance(raw_choices, str):
        try:
            snapshot["choices"] = json.loads(raw_choices)
        except json.JSONDecodeError:
            snapshot["choices"] = []
    return snapshot


def _insert_question_revision(connection, question_id, revision_number, editor_uuid, summary, snapshot):
    connection.execute(
        """
        INSERT INTO question_revisions (
            question_id, revision_number, editor_uuid, summary, snapshot_json
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            question_id, revision_number, editor_uuid, summary,
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
        ),
    )


def _ensure_initial_question_revision(connection, question):
    snapshot = _question_snapshot(question)
    connection.execute(
        """
        INSERT INTO question_revisions (
            question_id, revision_number, editor_uuid, summary,
            snapshot_json, created_at
        )
        VALUES (?, 1, ?, ?, ?, ?)
        ON CONFLICT (question_id, revision_number) DO NOTHING
        """,
        (
            question["id"],
            question["user_uuid"],
            "최초 등록 버전 · 이력 추적 시작",
            json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")),
            question["created_at"],
        ),
    )
