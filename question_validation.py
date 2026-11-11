from flask import g

from constants import SUBJECTS, LICENSE_CHOICES, SOURCE_TYPES
from database import get_db
from question_constants import COURSE_OPTIONS, DIFFICULTIES, QUESTION_TYPES
from question_ids import parse_question_number
from rich_text import sanitize_rich_html, _rich_text_has_content


def _collect_question_data(form):
    data = {
        "title": form.get("title", "").strip(),
        "subject": form.get("subject", "").strip(),
        "grade": form.get("grade", "").strip(),
        "course": form.get("course", "").strip(),
        "curriculum": form.get("curriculum", "2015 개정 교육과정").strip(),
        "unit": form.get("unit", "").strip(),
        "achievement_standard": form.get("achievement_standard", "").strip(),
        "difficulty": form.get("difficulty", "중").strip(),
        "question_type": form.get("question_type", "단답형").strip(),
        "points": None,
        "passage": "",
        "prompt": sanitize_rich_html(form.get("prompt", "")),
        "examples": "",
        "choices": [
            sanitize_rich_html(value.strip())
            for value in form.get("choices", "").splitlines()
            if value.strip()
        ],
        "answer": sanitize_rich_html(form.get("answer", "")),
        "explanation": sanitize_rich_html(form.get("explanation", "")),
        "source_type": form.get("source_type", "기타").strip(),
        "source": form.get("source", "").strip(),
        "year": None,
        "exam": form.get("exam", "").strip(),
        "original_question_number": form.get("original_question_number", "").strip(),
        "page": None,
        "source_url": form.get("source_url", "").strip(),
        "license": form.get("license", "").strip(),
        "base_question_number": form.get("base_question_number", "").strip().upper(),
        "base_question_id": None,
        "summary": form.get("summary", "").strip() or "문제 내용 수정",
        "folder_uuid": form.get("folder_uuid", "").strip() or None,
    }
    errors = []
    if data["subject"] not in SUBJECTS:
        errors.append("과목을 선택해 주세요.")
    if data["curriculum"] not in COURSE_OPTIONS:
        errors.append("교육과정을 선택해 주세요.")
    if data["difficulty"] not in DIFFICULTIES:
        errors.append("난이도를 선택해 주세요.")
    if data["question_type"] not in QUESTION_TYPES:
        errors.append("문항 유형을 선택해 주세요.")
    if data["source_type"] not in SOURCE_TYPES:
        errors.append("출처 유형을 선택해 주세요.")
    if data["license"] not in LICENSE_CHOICES:
        errors.append("라이선스를 선택해 주세요.")
    if data["base_question_number"]:
        base_id = parse_question_number(data["base_question_number"])
        if base_id is None:
            errors.append("변형문제 기준 번호는 6자리 Base36 번호로 입력해 주세요.")
        elif get_db().execute("SELECT 1 FROM questions WHERE id = ?", (base_id,)).fetchone() is None:
            errors.append("해당 기준 문항을 찾을 수 없습니다.")
        else:
            data["base_question_id"] = base_id
    for field, label in (("grade", "학년"),):
        if not data[field]:
            errors.append(f"{label}을(를) 입력해 주세요.")
    if not _rich_text_has_content(data["prompt"]):
        errors.append("문제 내용을 입력해 주세요.")
    if not _rich_text_has_content(data["answer"]):
        errors.append("정답을 입력해 주세요.")

    for field, label, maximum in (
        ("title", "문항 제목", 200), ("grade", "학년", 50), ("course", "교과목", 100),
        ("unit", "단원", 200), ("achievement_standard", "성취기준", 4000),
        ("prompt", "문제 내용", 1500000), ("answer", "정답", 10000),
        ("explanation", "해설", 20000), ("source", "출처명", 300),
        ("exam", "시험 / 회차", 200), ("original_question_number", "원본 문항 번호", 50),
        ("source_url", "출처 URL", 1000), ("summary", "수정 요약", 200),
    ):
        if len(data[field]) > maximum:
            errors.append(f"{label}은 {maximum}자 이내로 입력해 주세요.")
    if len(data["choices"]) > 20:
        errors.append("선택지는 20개 이하로 입력해 주세요.")
    if any(len(choice) > 2000 for choice in data["choices"]):
        errors.append("각 선택지는 2,000자 이내로 입력해 주세요.")

    for field, label, maximum in (
        ("year", "연도", 2200), ("page", "페이지", 10000), ("points", "배점", 100)
    ):
        value = form.get(field, "").strip()
        if field == "points" and not value:
            value = "4"
        if not value:
            continue
        try:
            parsed = int(value)
            if not 1 <= parsed <= maximum:
                raise ValueError
            data[field] = parsed
        except ValueError:
            errors.append(f"{label}는 1에서 {maximum} 사이의 정수로 입력해 주세요.")

    if data["folder_uuid"] and get_db().execute(
        "SELECT 1 FROM folders WHERE uuid = ? AND user_uuid = ?",
        (data["folder_uuid"], g.user["uuid"]),
    ).fetchone() is None:
        errors.append("선택한 폴더가 없습니다.")
    return data, errors


def _form_values_from_data(data):
    values = dict(data or {})
    choices = values.get("choices") or []
    if not isinstance(choices, str):
        values["choices"] = "\n".join(choices)
    return values
