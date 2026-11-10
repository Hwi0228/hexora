import json

from flask import g

from database import get_db
from question_constants import QUESTION_CONTENT_FIELDS


def _draft_key(question_id=None):
    return "new" if question_id is None else f"question:{int(question_id)}"


def _load_question_draft(question_id=None):
    row = get_db().execute(
        "SELECT payload_json, base_revision, updated_at FROM question_drafts "
        "WHERE user_uuid = ? AND draft_key = ?",
        (g.user["uuid"], _draft_key(question_id)),
    ).fetchone()
    if row is None:
        return None
    try:
        payload = json.loads(row["payload_json"])
    except (TypeError, json.JSONDecodeError):
        return None
    payload["choices"] = "\n".join(payload.get("choices") or [])
    payload["draft_updated_at"] = row["updated_at"]
    payload["draft_base_revision"] = row["base_revision"]
    return payload


def _save_question_draft(data, question_id=None, base_revision=None):
    payload = {field: data.get(field) for field in QUESTION_CONTENT_FIELDS}
    payload["choices"] = data.get("choices") or []
    payload["folder_uuid"] = data.get("folder_uuid")
    payload["summary"] = data.get("summary", "")
    payload["base_question_number"] = data.get("base_question_number", "")
    get_db().execute(
        """
        INSERT INTO question_drafts (
            user_uuid, draft_key, question_id, base_revision, payload_json,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        ON CONFLICT(user_uuid, draft_key) DO UPDATE SET
            question_id = excluded.question_id,
            base_revision = excluded.base_revision,
            payload_json = excluded.payload_json,
            updated_at = CURRENT_TIMESTAMP
        """,
        (
            g.user["uuid"], _draft_key(question_id), question_id, base_revision,
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        ),
    )
    get_db().commit()


def _delete_question_draft(question_id=None):
    get_db().execute(
        "DELETE FROM question_drafts WHERE user_uuid = ? AND draft_key = ?",
        (g.user["uuid"], _draft_key(question_id)),
    )
