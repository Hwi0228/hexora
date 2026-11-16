"""Authenticated API bridge for the HEXORA MCP service."""

import hmac
import json
import os

from flask import Blueprint, abort, g, jsonify, request
from werkzeug.datastructures import MultiDict

from database import begin_write_transaction, get_db
from question_ids import format_question_number, parse_question_number
from question_repository import _question_row
from question_revisions import _insert_question_revision, _question_snapshot
from question_validation import _collect_question_data
from rich_text import sanitize_rich_html

mcp_api = Blueprint("mcp_api", __name__, url_prefix="/api/integrations/mcp")


@mcp_api.before_request
def authorize():
    expected = os.environ.get("HEXORA_MCP_API_TOKEN", "")
    authorization = request.headers.get("Authorization", "")
    supplied = authorization[7:] if authorization.startswith("Bearer ") else ""
    if not expected or not supplied or not hmac.compare_digest(expected, supplied):
        abort(401)

    service_user_uuid = os.environ.get("HEXORA_MCP_SERVICE_USER_UUID", "")
    if not service_user_uuid:
        abort(503, description="HEXORA_MCP_SERVICE_USER_UUID is not configured")

    user = get_db().execute(
        "SELECT uuid, email, display_name, role FROM users WHERE uuid = ?",
        (service_user_uuid,),
    ).fetchone()
    if user is None:
        abort(503, description="Configured MCP service user does not exist")
    g.user = user


@mcp_api.get("/health")
def health():
    return jsonify({"ok": True, "service": "HEXORA", "integration": "mcp"})


@mcp_api.get("/questions")
def search_questions():
    query = request.args.get("query", "").strip()
    filters = {
        key: request.args.get(key, "").strip()
        for key in ("subject", "grade", "course", "achievement_standard", "difficulty")
    }
    limit = min(max(request.args.get("limit", 10, type=int), 1), 50)
    sql = """
        SELECT questions.id, questions.title, questions.subject, questions.grade,
               questions.course, questions.curriculum, questions.unit,
               questions.achievement_standard, questions.difficulty,
               questions.question_type, questions.points, questions.passage,
               questions.prompt, questions.examples, questions.choices,
               questions.answer, questions.explanation, questions.source_type,
               questions.source, questions.year, questions.exam,
               questions.original_question_number, questions.source_url,
               questions.license, questions.created_at,
               users.display_name AS author_name
        FROM questions
        LEFT JOIN users ON users.uuid = questions.user_uuid
        WHERE questions.deleted_at IS NULL
    """
    parameters = []
    for column, value in filters.items():
        if value:
            sql += f" AND questions.{column} = ?"
            parameters.append(value)
    if query:
        sql += """
            AND (
                questions.title LIKE ? OR questions.prompt LIKE ?
                OR questions.passage LIKE ? OR questions.explanation LIKE ?
                OR questions.achievement_standard LIKE ?
            )
        """
        parameters.extend([f"%{query}%"] * 5)
    sql += " ORDER BY questions.id DESC LIMIT ?"
    parameters.append(limit)

    rows = get_db().execute(sql, parameters).fetchall()
    questions = []
    for row in rows:
        item = dict(row)
        item["code"] = format_question_number(item.pop("id"))
        try:
            item["choices"] = json.loads(item.get("choices") or "[]")
        except (ValueError, TypeError):
            item["choices"] = []
        questions.append(item)
    return jsonify({"ok": True, "count": len(questions), "questions": questions})


@mcp_api.get("/questions/<code>")
def get_question(code):
    question_id = parse_question_number(code)
    if question_id is None:
        abort(404)
    row = _question_row(question_id)
    if row["deleted_at"] is not None:
        abort(404)

    item = dict(row)
    item["code"] = format_question_number(item.pop("id"))
    try:
        item["choices"] = json.loads(item.get("choices") or "[]")
    except (ValueError, TypeError):
        item["choices"] = []
    return jsonify({"ok": True, "question": item})


@mcp_api.get("/standards")
def standards():
    from question_constants import CURRICULUM_STANDARDS

    query = request.args.get("query", "").strip()
    curriculum = request.args.get("curriculum", "2015 개정 교육과정").strip()
    course = request.args.get("course", "").strip()
    limit = min(max(request.args.get("limit", 30, type=int), 1), 100)
    curriculum_data = CURRICULUM_STANDARDS.get(curriculum, {})
    found = []
    for course_name, units in curriculum_data.items():
        if course and course != course_name:
            continue
        for unit, standards_list in units.items():
            for standard in standards_list:
                if query and query not in standard and query not in unit:
                    continue
                found.append({
                    "curriculum": curriculum,
                    "course": course_name,
                    "unit": unit,
                    "achievement_standard": standard,
                })
    return jsonify({
        "ok": True,
        "count": min(len(found), limit),
        "standards": found[:limit],
        "available_curricula": list(CURRICULUM_STANDARDS),
    })


def collect(payload):
    if not isinstance(payload, dict):
        return {}, ["문항 데이터는 JSON 객체여야 합니다."]

    form = MultiDict()
    for key, value in payload.items():
        if key == "choices" and isinstance(value, list):
            form.add(key, "\n".join(str(choice) for choice in value))
        elif value is not None:
            form.add(key, str(value))

    data, errors = _collect_question_data(form)
    data["passage"] = sanitize_rich_html(str(payload.get("passage") or ""))
    data["examples"] = sanitize_rich_html(str(payload.get("examples") or ""))
    for field, label, maximum in (
        ("passage", "지문", 50000),
        ("examples", "보기", 20000),
    ):
        if len(data[field]) > maximum:
            errors.append(f"{label}은 {maximum}자 이내로 입력해 주세요.")
    return data, errors


@mcp_api.post("/questions/validate")
def validate_question():
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "valid": False, "errors": ["JSON 객체가 필요합니다."]}), 400
    _data, errors = collect(payload)
    return jsonify({"ok": True, "valid": not errors, "errors": errors})


@mcp_api.post("/questions")
def create_question():
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("question"), dict):
        return jsonify({
            "ok": False,
            "created": False,
            "errors": ["question 객체가 포함된 JSON이 필요합니다."],
        }), 400

    data, errors = collect(body["question"])
    if errors:
        return jsonify({"ok": False, "created": False, "errors": errors}), 400

    connection = get_db()
    try:
        begin_write_transaction(connection)
        cursor = connection.execute(
            """
            INSERT INTO questions (
                user_uuid, folder_uuid, subject, grade, unit, passage, prompt,
                examples, choices, answer, explanation, source, year, page,
                difficulty, question_type, points, course, curriculum,
                achievement_standard, source_type, exam, original_question_number,
                source_url, license, title
            )
            VALUES (
                ?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
                ?, ?, ?, ?, ?, ?
            )
            RETURNING id
            """,
            (
                g.user["uuid"], data["subject"], data["grade"], data["unit"],
                data["passage"], data["prompt"], data["examples"],
                json.dumps(data["choices"], ensure_ascii=False), data["answer"],
                data["explanation"], data["source"], data["year"], data["page"],
                data["difficulty"], data["question_type"], data["points"],
                data["course"], data["curriculum"], data["achievement_standard"],
                data["source_type"], data["exam"], data["original_question_number"],
                data["source_url"], data["license"], data["title"],
            ),
        )
        question_id = cursor.fetchone()["id"]

        if data["base_question_id"] is not None:
            base = connection.execute(
                "SELECT deleted_at FROM questions WHERE id = ?",
                (data["base_question_id"],),
            ).fetchone()
            if base is None or base["deleted_at"] is not None:
                connection.rollback()
                return jsonify({
                    "ok": False,
                    "created": False,
                    "errors": ["변형 기준 문항을 찾을 수 없습니다."],
                }), 400
            connection.execute(
                """
                INSERT INTO question_links (
                    question_id, related_question_id, relation_type, created_by
                )
                VALUES (?, ?, 'variant', ?)
                """,
                (question_id, data["base_question_id"], g.user["uuid"]),
            )

        row = connection.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        _insert_question_revision(
            connection,
            question_id,
            1,
            g.user["uuid"],
            data["summary"] or "ChatGPT MCP 최초 등록",
            _question_snapshot(row),
        )
        connection.commit()
    except Exception:
        connection.rollback()
        raise

    return jsonify({
        "ok": True,
        "created": True,
        "code": format_question_number(question_id),
    }), 201
