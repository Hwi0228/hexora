import json

from flask import abort

from constants import SOURCE_TYPES
from database import get_db
from question_constants import COURSE_OPTIONS, DIFFICULTIES, QUESTION_TYPES, QUESTION_CONTENT_FIELDS
from question_ids import format_question_number


def _question_row(question_id):
    row = get_db().execute(
        """
        SELECT questions.*, users.display_name AS author_name
        FROM questions
        LEFT JOIN users ON users.uuid = questions.user_uuid
        WHERE questions.id = ?
        """,
        (question_id,),
    ).fetchone()
    if row is None:
        abort(404)
    return row


def _question_form_values(question):
    values = dict(question)
    raw_choices = values.get("choices") or "[]"
    if isinstance(raw_choices, str):
        try:
            raw_choices = json.loads(raw_choices)
        except json.JSONDecodeError:
            raw_choices = []
    values["choices"] = "\n".join(raw_choices)
    base_link = get_db().execute(
        "SELECT related_question_id FROM question_links WHERE question_id = ? "
        "AND relation_type = 'variant' AND related_question_id IS NOT NULL "
        "ORDER BY id LIMIT 1", (question["id"],),
    ).fetchone()
    values["base_question_number"] = (
        format_question_number(base_link["related_question_id"]) if base_link else ""
    )
    if values.get("difficulty") not in DIFFICULTIES:
        values["difficulty"] = "중"
    if values.get("question_type") not in QUESTION_TYPES:
        values["question_type"] = "단답형"
    if values.get("curriculum") not in COURSE_OPTIONS:
        values["curriculum"] = "2015 개정 교육과정"
    if values.get("source_type") not in SOURCE_TYPES:
        values["source_type"] = "기타"
    return values


def _update_question_content(connection, question_id, values):
    """Persist the canonical editable question fields in their shared order."""
    serialized = {
        field: (
            json.dumps(values.get(field) or [], ensure_ascii=False)
            if field == "choices"
            else values.get(field)
        )
        for field in QUESTION_CONTENT_FIELDS
    }
    assignments = ", ".join(f"{field} = ?" for field in QUESTION_CONTENT_FIELDS)
    parameters = [serialized[field] for field in QUESTION_CONTENT_FIELDS]
    parameters.append(question_id)
    connection.execute(
        f"UPDATE questions SET {assignments} WHERE id = ?",
        parameters,
    )

