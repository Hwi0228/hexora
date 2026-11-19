"""Validated, atomic JSON import for the shared HEXORA question bank."""
import json
from flask import g, render_template, request
from auth import login_required
from constants import LICENSE_CHOICES, SOURCE_TYPES, SUBJECTS
from database import begin_write_transaction, get_db
from question_constants import COURSE_OPTIONS, DIFFICULTIES, QUESTION_CONTENT_FIELDS, QUESTION_TYPES
from question_revisions import _insert_question_revision
from rich_text import _rich_text_has_content, sanitize_rich_html

MAX_IMPORT_BYTES = 5 * 1024 * 1024
MAX_IMPORT_QUESTIONS = 200
MAX_FIELD_LENGTHS = {
    "title": 200, "grade": 50, "course": 100, "unit": 200,
    "achievement_standard": 4000, "passage": 50000, "prompt": 50000,
    "examples": 20000, "answer": 10000, "explanation": 20000,
    "source": 300, "exam": 200, "original_question_number": 50, "source_url": 1000,
}
ALLOWED_FIELDS = set(QUESTION_CONTENT_FIELDS)


def _normalize_question(item, index):
    errors = []
    prefix = f"{index + 1}번 문항"
    if not isinstance(item, dict):
        return None, [f"{prefix}: 객체(JSON object)여야 합니다."]
    unknown = sorted(set(item) - ALLOWED_FIELDS)
    if unknown:
        errors.append(f"{prefix}: 알 수 없는 필드: {', '.join(unknown)}")
    data = {
        "title": item.get("title", ""), "subject": item.get("subject", ""),
        "grade": item.get("grade", ""), "course": item.get("course", ""),
        "curriculum": item.get("curriculum", "2015 개정 교육과정"),
        "unit": item.get("unit", ""), "achievement_standard": item.get("achievement_standard", ""),
        "difficulty": item.get("difficulty", "중"), "question_type": item.get("question_type", "단답형"),
        "points": item.get("points", 4), "passage": item.get("passage", ""),
        "prompt": item.get("prompt", ""), "examples": item.get("examples", ""),
        "choices": item.get("choices", []), "answer": item.get("answer", ""),
        "explanation": item.get("explanation", ""), "source_type": item.get("source_type", "기타"),
        "source": item.get("source", ""), "year": item.get("year"), "exam": item.get("exam", ""),
        "original_question_number": item.get("original_question_number", ""),
        "page": item.get("page"), "source_url": item.get("source_url", ""), "license": item.get("license", ""),
    }
    for field in ("subject", "curriculum", "difficulty", "question_type", "source_type", "license"):
        if not isinstance(data[field], str):
            errors.append(f"{prefix}: {field}는 문자열이어야 합니다.")
            data[field] = ""
    checks = (
        ("subject", SUBJECTS, "subject"),
        ("curriculum", COURSE_OPTIONS, "curriculum"),
        ("difficulty", DIFFICULTIES, "difficulty"),
        ("question_type", QUESTION_TYPES, "question_type"),
        ("source_type", SOURCE_TYPES, "source_type"),
        ("license", LICENSE_CHOICES, "license"),
    )
    for field, allowed, label in checks:
        if data[field] not in allowed:
            errors.append(f"{prefix}: {label} 값이 올바르지 않습니다.")
    if not isinstance(data["grade"], str) or not data["grade"].strip():
        errors.append(f"{prefix}: grade는 필수 문자열입니다.")
    for field, maximum in MAX_FIELD_LENGTHS.items():
        value = data[field]
        if not isinstance(value, str):
            errors.append(f"{prefix}: {field}는 문자열이어야 합니다.")
            data[field] = ""
            continue
        data[field] = value.strip() if field not in {"passage", "prompt", "examples", "answer", "explanation"} else value
        if len(value) > maximum:
            errors.append(f"{prefix}: {field}는 {maximum}자 이하여야 합니다.")
    for field in ("passage", "prompt", "examples", "answer", "explanation"):
        if isinstance(data[field], str):
            data[field] = sanitize_rich_html(data[field])
    if not isinstance(data["choices"], list) or len(data["choices"]) > 20:
        errors.append(f"{prefix}: choices는 최대 20개의 문자열 배열이어야 합니다.")
        data["choices"] = []
    else:
        if any(not isinstance(choice, str) or len(choice) > 2000 for choice in data["choices"]):
            errors.append(f"{prefix}: choices의 각 항목은 2,000자 이하의 문자열이어야 합니다.")
        data["choices"] = [sanitize_rich_html(choice.strip()) for choice in data["choices"] if isinstance(choice, str) and choice.strip()]
    if not _rich_text_has_content(data["prompt"]):
        errors.append(f"{prefix}: prompt에 문제 내용이 필요합니다.")
    if not _rich_text_has_content(data["answer"]):
        errors.append(f"{prefix}: answer에 정답이 필요합니다.")
    if isinstance(data["points"], bool) or not isinstance(data["points"], int) or not 1 <= data["points"] <= 100:
        errors.append(f"{prefix}: points는 1~100의 정수여야 합니다.")
    for field, maximum in (("year", 2200), ("page", 10000)):
        value = data[field]
        if value is not None and (isinstance(value, bool) or not isinstance(value, int) or not 1 <= value <= maximum):
            errors.append(f"{prefix}: {field}는 1~{maximum}의 정수 또는 null이어야 합니다.")
    return data, errors


def _parse_import_payload(raw):
    if len(raw.encode("utf-8")) > MAX_IMPORT_BYTES:
        return [], ["JSON 파일은 5 MiB 이하여야 합니다."]
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return [], ["JSON 문법을 확인해 주세요."]
    if isinstance(payload, list):
        items = payload
    elif isinstance(payload, dict) and set(payload) == {"questions"}:
        items = payload["questions"]
    else:
        return [], ['최상위 형식은 {"questions": [...]} 또는 문항 배열이어야 합니다.']
    if not isinstance(items, list) or not items:
        return [], ["등록할 문항이 없습니다."]
    if len(items) > MAX_IMPORT_QUESTIONS:
        return [], [f"한 번에 최대 {MAX_IMPORT_QUESTIONS}개 문항까지 등록할 수 있습니다."]
    normalized, errors = [], []
    for index, item in enumerate(items):
        data, item_errors = _normalize_question(item, index)
        errors.extend(item_errors)
        if data is not None:
            normalized.append(data)
    return normalized, errors


def _insert_questions(connection, questions, user_uuid):
    inserted_ids = []
    for data in questions:
        cursor = connection.execute(
            """
            INSERT INTO questions (
                user_uuid, folder_uuid, subject, grade, unit, passage, prompt,
                examples, choices, answer, explanation, source, year, page,
                difficulty, question_type, points, course, curriculum,
                achievement_standard, source_type, exam, original_question_number,
                source_url, license, title
            )
            VALUES (?, NULL, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            RETURNING id
            """,
            (
                user_uuid, data["subject"], data["grade"], data["unit"], data["passage"],
                data["prompt"], data["examples"], json.dumps(data["choices"], ensure_ascii=False),
                data["answer"], data["explanation"], data["source"], data["year"], data["page"],
                data["difficulty"], data["question_type"], data["points"], data["course"],
                data["curriculum"], data["achievement_standard"], data["source_type"],
                data["exam"], data["original_question_number"], data["source_url"],
                data["license"], data["title"],
            ),
        )
        question_id = cursor.fetchone()["id"]
        snapshot = {field: data[field] for field in QUESTION_CONTENT_FIELDS}
        _insert_question_revision(connection, question_id, 1, user_uuid, "JSON 일괄 등록", snapshot)
        inserted_ids.append(question_id)
    return inserted_ids


def register_json_import_routes(app):
    @app.route("/questions/import-json", methods=["GET", "POST"])
    @login_required
    def json_question_import():
        raw_json = request.form.get("json_data", "")
        errors, preview, imported_count = [], [], 0
        if request.method == "POST":
            if not raw_json.strip():
                errors = ["JSON 내용을 입력하거나 파일을 선택해 주세요."]
            else:
                preview, errors = _parse_import_payload(raw_json)
            if request.form.get("action") == "import" and not errors:
                connection = get_db()
                try:
                    begin_write_transaction(connection)
                    inserted_ids = _insert_questions(connection, preview, g.user["uuid"])
                    connection.commit()
                    imported_count = len(inserted_ids)
                    preview, raw_json = [], ""
                except Exception:
                    connection.rollback()
                    app.logger.exception("HEXORA JSON question import failed")
                    errors = ["등록 중 오류가 발생했습니다. 데이터는 모두 롤백되었습니다."]
                    preview = []
        return render_template(
            "question_json_import.html", nav_items=[], active_page="json_question_import",
            raw_json=raw_json, errors=errors, preview=preview,
            imported_count=imported_count, max_questions=MAX_IMPORT_QUESTIONS,
        )
