"""Direct REST API for HEXORA GPT Actions; no MCP transport is involved."""
import hashlib
import json
import time

from flask import Blueprint, abort, g, jsonify, request

from database import begin_write_transaction, get_db
from question_ids import format_question_number, parse_question_number
from question_repository import _question_row
from question_revisions import _insert_question_revision, _question_snapshot
from question_validation import _collect_question_data
from rich_text import sanitize_rich_html
from werkzeug.datastructures import MultiDict

actions_api = Blueprint("actions_api", __name__, url_prefix="/api/v1")


@actions_api.before_request
def authorize_action_request():
    authorization = request.headers.get("Authorization", "")
    token = authorization[7:].strip() if authorization.startswith("Bearer ") else ""
    if not token:
        abort(401)
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    row = get_db().execute(
        """SELECT t.user_uuid, t.scope, t.expires_at,
                  u.uuid, u.email, u.display_name, u.role
        FROM actions_oauth_tokens t
        JOIN users u ON u.uuid = t.user_uuid
        WHERE t.token_hash = ? AND t.token_type = 'access_token'""",
        (token_hash,),
    ).fetchone()
    if row is None or row["expires_at"] < int(time.time()):
        abort(401)
    g.user = row
    g.oauth_scopes = set(row["scope"].split())


def require_scope(scope):
    if scope not in g.oauth_scopes:
        abort(403)


@actions_api.get("/health")
def health():
    return jsonify({"ok": True, "service": "HEXORA", "api": "v1"})


@actions_api.get("/questions")
def search_questions():
    require_scope("questions:read")
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


@actions_api.get("/questions/<code>")
def get_question(code):
    require_scope("questions:read")
    question_id = parse_question_number(code)
    if question_id is None:
        abort(404)
    row = _question_row(question_id)
    if row is None or row["deleted_at"] is not None:
        abort(404)
    item = dict(row)
    item["code"] = format_question_number(item.pop("id"))
    try:
        item["choices"] = json.loads(item.get("choices") or "[]")
    except (ValueError, TypeError):
        item["choices"] = []
    return jsonify({"ok": True, "question": item})


@actions_api.get("/standards")
def standards():
    require_scope("questions:read")
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


def collect_question(payload):
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
    data["summary"] = str(payload.get("summary") or "GPT Actions 문항 등록")
    for field, label, maximum in (
        ("passage", "지문", 50000),
        ("examples", "보기", 20000),
        ("summary", "수정 요약", 200),
    ):
        if len(data[field]) > maximum:
            errors.append(f"{label}은 {maximum}자 이내로 입력해 주세요.")
    return data, errors


@actions_api.post("/questions/validate")
def validate_question():
    require_scope("questions:write")
    payload = request.get_json(silent=True)
    if not isinstance(payload, dict):
        return jsonify({"ok": False, "valid": False, "errors": ["JSON 객체가 필요합니다."]}), 400
    _data, errors = collect_question(payload)
    return jsonify({"ok": True, "valid": not errors, "errors": errors})


@actions_api.post("/questions")
def create_question():
    require_scope("questions:write")
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("question"), dict):
        return jsonify({
            "ok": False,
            "created": False,
            "errors": ["question 객체가 포함된 JSON이 필요합니다."],
        }), 400

    data, errors = collect_question(body["question"])
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
                """INSERT INTO question_links
                (question_id, related_question_id, relation_type, created_by)
                VALUES (?, ?, 'variant', ?)""",
                (question_id, data["base_question_id"], g.user["uuid"]),
            )

        row = connection.execute(
            "SELECT * FROM questions WHERE id = ?", (question_id,)
        ).fetchone()
        _insert_question_revision(
            connection, question_id, 1, g.user["uuid"], data["summary"],
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
