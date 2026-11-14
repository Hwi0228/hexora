"""Validation helpers for imported HWP question payloads."""

import json
from pathlib import Path

from constants import LICENSE_CHOICES, SOURCE_TYPES, SUBJECTS
from parse_hwp import strip_choice_label
from rich_text import sanitize_rich_html


MAX_SECTION_XML_SIZE = 16 * 1024 * 1024
MAX_IMPORTED_QUESTIONS = 500


def _validated_import(form):
    errors = []
    try:
        payload = json.loads(form.get("questions_json", ""))
    except (TypeError, ValueError):
        return None, None, errors, "파싱 결과가 올바르지 않습니다. 파일을 다시 업로드해 주세요."
    questions = payload.get("questions") if isinstance(payload, dict) else payload

    if not isinstance(questions, list) or not 1 <= len(questions) <= MAX_IMPORTED_QUESTIONS:
        return None, None, errors, "등록할 문항이 없거나 허용 개수(500개)를 초과했습니다."

    subject = form.get("subject", "").strip()
    grade = form.get("grade", "").strip()
    unit = form.get("unit", "").strip()
    source = form.get("source", "").strip()
    license_value = form.get("license", "").strip()
    source_type = form.get("source_type", "기타").strip() or "기타"
    year_value = form.get("year", "").strip()

    if subject not in SUBJECTS:
        errors.append("과목을 선택해 주세요.")
    if license_value not in LICENSE_CHOICES:
        errors.append("문항 공개에 사용할 라이선스를 선택해 주세요.")
    if source_type not in SOURCE_TYPES:
        errors.append("출처 유형이 올바르지 않습니다.")
    for value, label in ((grade, "학년"), (unit, "단원"), (source, "출처")):
        if not value:
            errors.append(f"{label}을(를) 입력해 주세요.")
    for value, label, maximum in (
        (grade, "학년", 50),
        (unit, "단원", 200),
        (source, "출처", 300),
    ):
        if len(value) > maximum:
            errors.append(f"{label}은 {maximum}자 이내로 입력해 주세요.")

    year = None
    if year_value:
        try:
            year = int(year_value)
            if not 1 <= year <= 2200:
                raise ValueError
        except ValueError:
            errors.append("연도는 1에서 2200 사이의 정수로 입력해 주세요.")

    selected_values = form.getlist("selected_questions")
    selected_indices = []
    for value in selected_values:
        try:
            index = int(value)
        except (TypeError, ValueError):
            errors.append("선택한 문항이 올바르지 않습니다.")
            break
        if not 0 <= index < len(questions):
            errors.append("선택한 문항이 올바르지 않습니다.")
            break
        if index not in selected_indices:
            selected_indices.append(index)
    if not selected_indices:
        errors.append("DB에 등록할 문항을 하나 이상 선택해 주세요.")

    normalized_questions = []
    for question in questions:
        if not isinstance(question, dict):
            errors.append("파싱 결과의 문항 형식이 올바르지 않습니다.")
            break
        prompt = question.get("question")
        answer = question.get("answer")
        explanation = question.get("explanation", "")
        choices = question.get("choices", [])
        if (
            not isinstance(prompt, str)
            or not prompt.strip()
            or len(prompt) > 10000
            or not isinstance(answer, str)
            or len(answer) > 2000
            or not isinstance(explanation, str)
            or len(explanation) > 10000
            or not isinstance(choices, list)
            or len(choices) > 20
            or any(
                not isinstance(choice, str) or len(choice) > 2000
                for choice in choices
            )
        ):
            errors.append("문항 내용, 정답, 해설 또는 선택지의 형식이 올바르지 않습니다.")
            break
        normalized_questions.append(
            {
                "number": len(normalized_questions) + 1,
                "question": sanitize_rich_html(prompt.strip()),
                "answer": sanitize_rich_html(answer.strip()),
                "explanation": sanitize_rich_html(explanation.strip()),
                "choices": [
                    sanitize_rich_html(strip_choice_label(choice))
                    for choice in choices
                ],
            }
        )

    if errors:
        return normalized_questions or None, None, errors, None
    metadata = {
        "subject": subject,
        "grade": grade,
        "unit": unit,
        "source": source,
        "folder_uuid": None,
        "year": year,
        "license": license_value,
        "source_type": source_type,
    }
    return normalized_questions, (metadata, selected_indices), errors, None


def _get_section_xml(filename: str, content: bytes) -> bytes:
    if Path(filename).suffix.lower() != ".xml":
        raise ValueError("단독 HWPML XML 파일만 이 경로에서 처리할 수 있습니다.")
    if not content:
        raise ValueError("파싱할 XML 내용이 비어 있습니다.")
    if len(content) > MAX_SECTION_XML_SIZE:
        raise ValueError("XML 크기가 허용 한도(16MB)를 초과합니다.")
    return content
