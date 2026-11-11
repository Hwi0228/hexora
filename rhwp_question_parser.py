"""Question-row and numbered-paragraph parsing for rhwp IR documents."""

from __future__ import annotations

import html
import re
from typing import Any

from hwp_equations import CHOICE_LABELS, strip_choice_label


CHOICE_PATTERN = re.compile(rf"[{CHOICE_LABELS}]")


_HWP_CONTROL_SEQUENCE = re.compile(
    r"(?P<marker>[\x01-\x08\x0b\x0c\x0e-\x1f])[\s\S]{6}?(?P=marker)"
)


def _compact(text: str) -> str:
    # rhwp-python may retain HWP inline-control records in paragraph.text.
    # Remove paired control markers before detecting question/answer numbers.
    text = _HWP_CONTROL_SEQUENCE.sub("", text)
    text = text.replace("\x00", "")
    text = re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"(\[그림(?::[^\]]*)?\])(?=\S)", r"\1 ", text)
    return text.strip()


def _is_document_header(paragraph: str, next_paragraph: str = "") -> bool:
    if re.fullmatch(r"수학\s*[①-⑳]?", paragraph):
        return True
    if re.fullmatch(r"[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+\s*[.)]?\s*수와\s*연산", paragraph):
        return True
    if re.search(r"반\s*/\s*번호|이름", paragraph):
        return True
    if (
        next_paragraph
        and re.search(r"반\s*/\s*번호|이름", next_paragraph)
        and len(paragraph) <= 80
        and not re.search(r"[.!?。！？]", paragraph)
        and not CHOICE_PATTERN.search(paragraph)
    ):
        return True
    return False


def _canonical(text: str) -> str:
    """서식과 인라인 수식 Embed 표현 차이를 제거해 중복 문단을 비교한다."""
    # Summary paragraphs may store an existing Quill math embed as HTML while
    # the corresponding IR formula block is rendered as $...$. Convert both
    # representations to the same inline-math text before comparing prefixes.
    text = re.sub(
        r'<(?:span|div)\b[^>]*\bdata-latex=["\']([^"\']*)["\'][^>]*>.*?</(?:span|div)>',
        lambda match: "$" + html.unescape(match.group(1)) + "$",
        text,
        flags=re.DOTALL,
    )
    text = html.unescape(text)
    return re.sub(r"\s+", "", text).replace("$", "").replace(r"\(", "").replace(r"\)", "")

def _strip_canonical_prefix(text: str, prefix: str) -> str:
    if not prefix:
        return text
    consumed = 0
    index = 0
    while index < len(text) and consumed < len(prefix):
        character = text[index]
        if not character.isspace() and character != "$":
            consumed += 1
        index += 1
    while index < len(text) and (text[index].isspace() or text[index] == "$"):
        index += 1
    return text[index:]


def _split_choices(text: str) -> list[str]:
    starts = list(CHOICE_PATTERN.finditer(text))
    choices = []
    for index, start in enumerate(starts):
        end = starts[index + 1].start() if index + 1 < len(starts) else len(text)
        choice = _compact(text[start.start():end])
        choice = strip_choice_label(choice)
        if choice:
            choices.append(choice)
    return choices


def _parse_question_row(paragraphs: list[str], number: int) -> dict[str, Any] | None:
    summaries = [
        (index, paragraph)
        for index, paragraph in enumerate(paragraphs)
        if "[정답]" in paragraph and "[해설]" in paragraph
    ]
    if len(summaries) != 1:
        return None

    summary_index, summary = summaries[0]
    answer_marker = summary.find("[정답]")
    explanation_marker = summary.find("[해설]", answer_marker + len("[정답]"))
    if answer_marker < 0 or explanation_marker < 0:
        return None

    answer = _compact(summary[answer_marker + len("[정답]"):explanation_marker])
    summary_after_explanation = summary[explanation_marker + len("[해설]"):]

    answer_indices = [
        index for index, paragraph in enumerate(paragraphs)
        if index != summary_index and "[정답]" in paragraph and "[해설]" not in paragraph
    ]
    if not answer:
        if not answer_indices:
            return None
        answer = _compact(paragraphs[answer_indices[0]].split("[정답]", 1)[-1])

    marker_indices = [
        index for index, paragraph in enumerate(paragraphs)
        if index != summary_index and "[해설]" in paragraph and "[정답]" not in paragraph
    ]
    explanation_indices: set[int] = set()
    explanation_parts: list[str] = []
    explanation_prefix = ""

    if marker_indices:
        marker_index = marker_indices[0]
        marker_tail = paragraphs[marker_index].split("[해설]", 1)[-1].strip()
        if marker_tail:
            marker_tail_canonical = _canonical(marker_tail)
            if _canonical(summary_after_explanation).startswith(marker_tail_canonical):
                explanation_parts.append(marker_tail)
                explanation_prefix += marker_tail_canonical
                explanation_indices.add(marker_index)

        for index in range(marker_index + 1, len(paragraphs)):
            candidate = paragraphs[index].strip()
            if not candidate or CHOICE_PATTERN.search(candidate):
                break
            if "[정답]" in candidate or "[해설]" in candidate:
                break
            candidate_canonical = _canonical(candidate)
            if not candidate_canonical:
                continue
            prospective = explanation_prefix + candidate_canonical
            if not _canonical(summary_after_explanation).startswith(prospective):
                break
            explanation_parts.append(candidate)
            explanation_prefix = prospective
            explanation_indices.add(index)

    explanation = _compact(" ".join(explanation_parts))
    question_from_summary = _strip_canonical_prefix(
        summary_after_explanation, explanation_prefix
    )
    question_from_summary = _compact(question_from_summary)

    choices: list[str] = []
    if CHOICE_PATTERN.search(question_from_summary):
        choice_start = CHOICE_PATTERN.search(question_from_summary)
        assert choice_start is not None
        choices.extend(_split_choices(question_from_summary[choice_start.start():]))
        question_from_summary = question_from_summary[:choice_start.start()].strip()

    question_parts = [question_from_summary] if question_from_summary else []
    ignored_indices = {summary_index, *answer_indices, *marker_indices, *explanation_indices}

    for index, paragraph in enumerate(paragraphs):
        if index in ignored_indices or not paragraph:
            continue
        if "[정답]" in paragraph or "[해설]" in paragraph:
            continue
        if CHOICE_PATTERN.search(paragraph):
            choices.extend(_split_choices(paragraph))
            continue
        question_parts.append(paragraph)

    question = _compact(" ".join(question_parts))
    question = re.sub(r"\s*\[\s*\d+\s*점\s*\]\s*$", "", question).strip()
    if not question or not answer:
        return None

    deduplicated_choices: list[str] = []
    for choice in choices:
        if choice not in deduplicated_choices:
            deduplicated_choices.append(choice)

    return {
        "number": number,
        "question": question,
        "choices": deduplicated_choices,
        "answer": answer,
        "explanation": explanation,
    }


_QUESTION_START = re.compile(
    r"^\s*(?:(?:제\s*)?(\d{1,3})\s*[.)]|"
    r"(\d{1,3})\s*번(?:\s*[.)])?|Q\s*(\d{1,3})\s*[.:)])\s*(.*)$",
    re.IGNORECASE,
)


def _parse_numbered_paragraphs(paragraphs: list[str]) -> list[dict[str, Any]]:
    """문항 번호로 시작하는 일반 문단형 시험지도 파싱한다. 정답·해설은 선택 항목이다."""
    records: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    unit_index = 0
    previous_source_number: int | None = None

    def append_question_text(value: str) -> None:
        value = _compact(value)
        if value:
            current["question_parts"].append(value)

    def finish() -> None:
        if current is None:
            return
        question = _compact(" ".join(current["question_parts"]))
        question = re.sub(r"\s*\[\s*\d+\s*점\s*\]\s*$", "", question).strip()
        if not question:
            return
        choices: list[str] = []
        for choice in current["choices"]:
            choice = _compact(choice)
            if choice and choice not in choices:
                choices.append(choice)
        records.append({
            "number": len(records) + 1,
            "source_number": current["source_number"],
            "unit_index": current["unit_index"],
            "question": question,
            "choices": choices,
            "answer": _compact(current["answer"]),
            "explanation": _compact(" ".join(current["explanation_parts"])),
        })

    for paragraph_index, raw_paragraph in enumerate(paragraphs):
        paragraph = _compact(raw_paragraph)
        if not paragraph:
            continue

        start = _QUESTION_START.match(paragraph)
        if start:
            source_number = int(start.group(1) or start.group(2) or start.group(3))
            if previous_source_number is not None and source_number <= previous_source_number:
                unit_index += 1
            finish()
            current = {
                "source_number": source_number,
                "unit_index": unit_index,
                "question_parts": [],
                "choices": [],
                "answer": "",
                "explanation_parts": [],
            }
            previous_source_number = source_number
            append_question_text(start.group(4))
            continue

        if current is None:
            continue

        next_paragraph = (
            _compact(paragraphs[paragraph_index + 1])
            if paragraph_index + 1 < len(paragraphs) else ""
        )
        if _is_document_header(paragraph, next_paragraph):
            continue

        next_start = _QUESTION_START.match(next_paragraph)
        if (
            next_start
            and previous_source_number is not None
            and int(next_start.group(1) or next_start.group(2) or next_start.group(3)) <= previous_source_number
            and len(paragraph) <= 60
            and not re.search(r"[.!?。！？]", paragraph)
            and not CHOICE_PATTERN.search(paragraph)
        ):
            # 단원 제목은 직전 문항의 마지막 선택지/본문에 합치지 않는다.
            continue

        answer_match = re.search(r"\[정답\]\s*(.*?)(?=\[해설\]|$)", paragraph)
        explanation_match = re.search(r"\[해설\]\s*(.*)$", paragraph)
        if answer_match or explanation_match:
            if answer_match:
                current["answer"] = _compact(answer_match.group(1))
            if explanation_match and explanation_match.group(1).strip():
                current["explanation_parts"].append(explanation_match.group(1))
            continue

        choice_match = CHOICE_PATTERN.search(paragraph)
        if choice_match:
            prefix = paragraph[:choice_match.start()].strip()
            if prefix:
                append_question_text(prefix)
            current["choices"].extend(_split_choices(paragraph[choice_match.start():]))
        elif current["choices"]:
            # 보기 문장이 다음 문단으로 이어지는 문서의 줄바꿈을 보존한다.
            current["choices"][-1] = _compact(current["choices"][-1] + " " + paragraph)
        else:
            append_question_text(paragraph)

    finish()
    return records


_ANSWER_SECTION_HEADING = re.compile(
    r"^\s*(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.)]?\s*)?"
    r"(?:정\s*답(?:\s*(?:\(\s*해\s*설\s*\)|및\s*해\s*설|과\s*해\s*설))?|"
    r"정답\s*/\s*해설)\s*$"
)
_ANSWER_ENTRY_START = re.compile(
    r"^\s*(?:(?:제\s*)?(\d{1,3})\s*[.)]|"
    r"(\d{1,3})\s*번(?:\s*[.)])?|Q\s*(\d{1,3})\s*[.:)])\s*(.*)$",
    re.IGNORECASE,
)


def _parse_separated_answers(paragraphs: list[str]) -> list[dict[str, Any]]:
    """정답·해설 영역을 읽고, 번호 없는 첫 해설과 페이지 머리글을 보존/제외한다."""
    answers: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    unit_index = 0
    previous_source_number: int | None = None
    in_explanation = False
    pending_parts: list[str] = []
    pending_has_section_heading = False
    leading_explanation_parts: list[str] = []
    leading_explanation_active = False

    def finish() -> None:
        if current is None:
            return
        if pending_parts and not in_explanation and not pending_has_section_heading:
            current["explanation_parts"].extend(pending_parts)
        answers.append({
            "source_number": current["source_number"],
            "unit_index": current["unit_index"],
            "answer": _compact(current["answer"]),
            "explanation": _compact(" ".join(current["explanation_parts"])),
        })

    for paragraph_index, raw in enumerate(paragraphs):
        paragraph = _compact(raw)
        if not paragraph:
            continue

        start = _ANSWER_ENTRY_START.match(paragraph)
        if start:
            source_number = int(start.group(1) or start.group(2) or start.group(3))
            if current is not None:
                finish()
            elif leading_explanation_parts and source_number == 2:
                # 일부 교재는 첫 문항 해설만 먼저 싣고 2번부터 답 번호를 표시한다.
                # 정답은 추측하지 않고 첫 문항의 해설만 연결한다.
                answers.append({
                    "source_number": 1,
                    "unit_index": unit_index,
                    "answer": "",
                    "explanation": _compact(" ".join(leading_explanation_parts)),
                })
            leading_explanation_parts = []
            leading_explanation_active = False

            if previous_source_number is not None and source_number <= previous_source_number:
                unit_index += 1

            tail = _compact(start.group(4))
            tail = re.sub(r"^(\(\s*답\s*\)|\[\s*답\s*\]|답)\s*", "", tail)
            explanation_parts: list[str] = []
            answer_text = tail
            explanation_match = re.search(r"(\(\s*해설\s*\)|\[\s*해설\s*\])", answer_text)
            if explanation_match:
                explanation_parts.append(answer_text[explanation_match.end():])
                answer_text = answer_text[:explanation_match.start()]
                in_explanation = True
            else:
                in_explanation = False
            current = {
                "source_number": source_number,
                "unit_index": unit_index,
                "answer": answer_text,
                "explanation_parts": explanation_parts,
            }
            previous_source_number = source_number
            pending_parts = []
            pending_has_section_heading = False
            continue

        explanation_marker = re.search(
            r"(\(\s*해설\s*\)|\[\s*해설\s*\])", paragraph
        )
        if current is None:
            if explanation_marker:
                leading_explanation_active = True
                tail = paragraph[explanation_marker.end():].strip()
                if tail:
                    leading_explanation_parts.append(tail)
            elif leading_explanation_active:
                leading_explanation_parts.append(paragraph)
            continue

        next_paragraph = (
            _compact(paragraphs[paragraph_index + 1])
            if paragraph_index + 1 < len(paragraphs) else ""
        )
        next_start = _ANSWER_ENTRY_START.match(next_paragraph)
        if (
            in_explanation
            and next_start
            and previous_source_number is not None
            and int(next_start.group(1) or next_start.group(2) or next_start.group(3)) <= previous_source_number
            and len(paragraph) <= 60
            and not re.search(r"[.!?。！？]", paragraph)
            and not CHOICE_PATTERN.search(paragraph)
        ):
            # 단원 제목은 다음 단원의 첫 답안 직전에 나타날 수 있다.
            continue

        if _ANSWER_SECTION_HEADING.fullmatch(paragraph):
            # 일부 파일은 단원/페이지마다 '정답' 머리글을 반복한다.
            pending_has_section_heading = True
            continue

        if explanation_marker:
            if pending_has_section_heading:
                pending_parts = []
            else:
                current["explanation_parts"].extend(pending_parts)
            pending_parts = []
            pending_has_section_heading = False
            in_explanation = True
            tail = paragraph[explanation_marker.end():].strip()
            if tail:
                current["explanation_parts"].append(tail)
            continue

        answer_marker = re.match(r"^(\(\s*답\s*\)|\[\s*답\s*\]|답)\s*(.*)$", paragraph)
        if answer_marker and not current["answer"]:
            current["answer"] = answer_marker.group(2)
            continue

        if in_explanation:
            current["explanation_parts"].append(paragraph)
        elif not current["answer"]:
            if not _is_document_header(paragraph):
                current["answer"] = paragraph
        else:
            # 다음 (해설) 표식이 나오기 전까지는 보류한다.
            # 중간에 '정답' 머리글이 나오면 페이지 헤더로 판단해 버린다.
            pending_parts.append(paragraph)

    finish()
    return answers




_TRAILING_QUESTION_NUMBER = re.compile(r"^\s*0?(\d{1,3})\s*$")


def _is_trailing_question_heading(value: str) -> bool:
    value = _compact(value)
    if not value:
        return True
    if _is_document_header(value):
        return True
    if re.fullmatch(r"[ⅤⅠⅡⅢⅣ]+|주\s*관\s*식|객\s*관\s*식", value):
        return True
    if value in {"중단원 마무리", "정답 및 해설"}:
        return True
    if re.match(r"^[-–]\s*\d+\s+.+$", value) and len(value) <= 50:
        return True
    return False


def _parse_trailing_numbered_questions(
    paragraphs: list[str],
) -> list[dict[str, Any]]:
    """문항 본문 뒤에 독립된 번호가 놓이는 교재형 문서를 파싱한다."""
    markers = [
        (index, int(match.group(1)))
        for index, paragraph in enumerate(paragraphs)
        if (match := _TRAILING_QUESTION_NUMBER.fullmatch(_compact(paragraph)))
    ]
    if len(markers) < 2:
        return []

    def clean_stem(values: list[str]) -> list[str]:
        return [
            _compact(value) for value in values
            if _compact(value) and not _is_trailing_question_heading(value)
        ]

    first_index, first_number = markers[0]
    current = {
        "source_number": first_number,
        "question_parts": clean_stem(paragraphs[:first_index]),
        "choices": [],
    }
    records: list[dict[str, Any]] = []
    next_stem: list[str] = []

    def finish() -> None:
        question = _compact(" ".join(current["question_parts"]))
        choices: list[str] = []
        for choice in current["choices"]:
            choice = _compact(choice)
            if choice and choice not in choices:
                choices.append(choice)
        if question:
            records.append({
                "number": len(records) + 1,
                "source_number": current["source_number"],
                "unit_index": 0,
                "question": question,
                "choices": choices,
                "answer": "",
                "explanation": "",
            })

    for paragraph in paragraphs[first_index + 1:]:
        value = _compact(paragraph)
        if not value:
            continue
        marker = _TRAILING_QUESTION_NUMBER.fullmatch(value)
        if marker:
            finish()
            current = {
                "source_number": int(marker.group(1)),
                "question_parts": clean_stem(next_stem),
                "choices": [],
            }
            next_stem = []
            continue

        choice_match = CHOICE_PATTERN.search(value)
        if choice_match:
            if next_stem:
                current["choices"].extend(_split_choices(value))
                continue
            current["choices"].extend(_split_choices(value))
        elif current["choices"]:
            # 선택지 뒤에 나타나는 일반 문단은 다음 문항의 본문으로 보류한다.
            next_stem.append(value)
        else:
            current["question_parts"].append(value)

    finish()
    return records


def _parse_packed_answer_key(paragraphs: list[str]) -> dict[int, str]:
    """01 ⑤ 02 ③, ④처럼 여러 정답이 한 문단에 나열된 답안표를 읽는다."""
    text = _compact(" ".join(paragraphs))
    answers: dict[int, str] = {}
    matches = list(re.finditer(
        r"(?<!\d)(\d{2})\s*([①-⑳](?:\s*[,、]\s*[①-⑳])*)",
        text,
    ))
    for index, match in enumerate(matches):
        number = int(match.group(1))
        value = _compact(match.group(2))
        if value:
            answers[number] = value

    # 주관식 답은 원문 텍스트를 보존하되, 다음 두 자리 문항 번호에서 끊는다.
    subjective = re.compile(r"(?<!\d)(2[4-9]|30)\s+(.+?)(?=\s+(?:2[4-9]|30)\s+|$)")
    for match in subjective.finditer(text):
        value = _compact(match.group(2)).strip(" ,")
        if value and not re.fullmatch(r"[①-⑳]", value):
            answers.setdefault(int(match.group(1)), value)
    return answers


def _parse_trailing_numbered_answers(
    paragraphs: list[str],
) -> tuple[dict[int, str], dict[int, str]]:
    """번호별 답안표와 해설 뒤에 놓인 독립 번호를 각각 연결한다."""
    marker_positions = [
        (index, int(match.group(1)))
        for index, paragraph in enumerate(paragraphs)
        if (match := _TRAILING_QUESTION_NUMBER.fullmatch(_compact(paragraph)))
    ]
    if not marker_positions:
        return _parse_packed_answer_key(paragraphs), {}

    first_explanation_index = marker_positions[0][0]
    answer_key_paragraphs = paragraphs[:first_explanation_index]
    answers = _parse_packed_answer_key(answer_key_paragraphs)
    key_line_indices = [
        index for index, paragraph in enumerate(answer_key_paragraphs)
        if re.search(r"(?<!\d)\d{2}\s*(?:[①-⑳]|[가-힣])", _compact(paragraph))
    ]
    explanations: dict[int, str] = {}
    chunk_start = (max(key_line_indices) + 1) if key_line_indices else first_explanation_index

    for index, number in marker_positions:
        explanation = _compact(" ".join(paragraphs[chunk_start:index]))
        if explanation:
            explanations[number] = explanation
        chunk_start = index + 1

    return answers, explanations


def _parse_trailing_numbered_document(
    question_paragraphs: list[str],
    answer_paragraphs: list[str],
) -> list[dict[str, Any]]:
    questions = _parse_trailing_numbered_questions(question_paragraphs)
    if not questions:
        return []
    answers, explanations = _parse_trailing_numbered_answers(answer_paragraphs)
    for question in questions:
        source_number = question["source_number"]
        question["answer"] = answers.get(source_number, "")
        question["explanation"] = explanations.get(source_number, "")
        question.pop("source_number", None)
        question.pop("unit_index", None)
    return questions


def parse_numbered_document_sections(paragraphs: list[str]) -> list[dict[str, Any]]:
    """문제 영역과 뒤쪽 정답·해설 영역을 분리하고 단원/문항 번호로 연결한다."""
    answer_heading_index = next(
        (
            index for index, paragraph in enumerate(paragraphs)
            if _ANSWER_SECTION_HEADING.fullmatch(_compact(paragraph))
        ),
        None,
    )
    if answer_heading_index is None:
        return _parse_numbered_paragraphs(paragraphs)

    question_paragraphs = paragraphs[:answer_heading_index]
    answer_paragraphs = paragraphs[answer_heading_index + 1:]
    questions = _parse_trailing_numbered_document(
        question_paragraphs, answer_paragraphs
    )
    if questions:
        return questions
    questions = _parse_numbered_paragraphs(question_paragraphs)
    answers = _parse_separated_answers(answer_paragraphs)
    answer_map = {
        (item["unit_index"], item["source_number"]): item
        for item in answers
    }

    # 일부 문서는 답안 번호가 단원별로 다시 시작되지 않는다. 이 경우에만
    # 문항 번호가 유일한 답안을 보조 키로 사용한다.
    unique_by_number: dict[int, dict[str, Any]] = {}
    duplicate_numbers: set[int] = set()
    for item in answers:
        number = item["source_number"]
        if number in unique_by_number:
            duplicate_numbers.add(number)
        else:
            unique_by_number[number] = item
    for number in duplicate_numbers:
        unique_by_number.pop(number, None)

    for question in questions:
        answer_item = answer_map.get(
            (question["unit_index"], question["source_number"])
        )
        if answer_item is None:
            answer_item = unique_by_number.get(question["source_number"])
        if answer_item is not None:
            question["answer"] = answer_item["answer"]
            question["explanation"] = answer_item["explanation"]
        question.pop("source_number", None)
        question.pop("unit_index", None)

    return questions
