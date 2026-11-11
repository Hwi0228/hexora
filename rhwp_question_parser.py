"""Question-row and numbered-paragraph parsing for rhwp IR documents."""

from __future__ import annotations

import re
from typing import Any

from hwp_equations import CHOICE_LABELS, strip_choice_label


CHOICE_PATTERN = re.compile(rf"[{CHOICE_LABELS}]")


def _compact(text: str) -> str:
    text = re.sub(r"[ \t\r\f\v]+", " ", text)
    text = re.sub(r"\n+", " ", text)
    text = re.sub(r"(\[그림(?::[^\]]*)?\])(?=\S)", r"\1 ", text)
    return text.strip()


def _canonical(text: str) -> str:
    """서식 차이를 줄여 요약 문단과 별도 해설 문단의 중복 구간을 비교한다."""
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
            "question": question,
            "choices": choices,
            "answer": _compact(current["answer"]),
            "explanation": _compact(" ".join(current["explanation_parts"])),
        })

    for raw_paragraph in paragraphs:
        paragraph = _compact(raw_paragraph)
        if not paragraph:
            continue

        start = _QUESTION_START.match(paragraph)
        if start:
            finish()
            current = {
                "question_parts": [],
                "choices": [],
                "answer": "",
                "explanation_parts": [],
            }
            append_question_text(start.group(4))
            continue

        if current is None:
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
