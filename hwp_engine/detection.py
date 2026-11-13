"""Advisory template detection using separate question/answer regions."""
from __future__ import annotations

import re
from collections import Counter

from .models import (
    AnswerTemplate, BlockKind, DocumentIR, QuestionTemplate, TemplateDetection,
)

_PREFIX = re.compile(
    r"^\s*(?:(?:제\s*)?\d{1,3}\s*[.)]|\d{1,3}\s*번(?:\s*[.)])?|Q\s*\d{1,3}\s*[.:)])",
    re.I,
)
_SUFFIX = re.compile(r"^\s*0?(\d{1,3})\s*$")
_PACKED = re.compile(r"(?<!\d)(\d{1,2})\s*([①-⑳](?:\s*[,、/]\s*[①-⑳])*)")
_INLINE = re.compile(r"(?:\[\s*정답\s*\]|\(\s*답\s*\)|정답\s*[:：])")
_NUMBERED_ANSWER = re.compile(
    r"^\s*(?:(?:제\s*)?\d{1,3}\s*[.)]|\d{1,3}\s*번)\s*(?:\(\s*답\s*\)|\[\s*답\s*\]|답)?",
    re.I,
)
_ANSWER_HEADING = re.compile(
    r"^\s*(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.)]?\s*)?"
    r"(?:정\s*답(?:\s*(?:\(\s*해\s*설\s*\)|및\s*해\s*설|과\s*해\s*설))?|"
    r"정답\s*/\s*해설)\s*$"
)
_SUBJECTIVE_HEADING = re.compile(r"주\s*관\s*식|서\s*술\s*형|단\s*답\s*형")
_CHOICE = re.compile(r"[①②③④⑤⑥⑦⑧⑨⑩]")


def _normalize(scores: Counter[str]) -> dict[str, float]:
    total = sum(scores.values())
    if not total:
        return {}
    return {key: round(value / total, 3) for key, value in scores.items()}


def _paragraphs(blocks):
    return [
        block for block in blocks
        if block.kind == BlockKind.PARAGRAPH and block.text.strip()
    ]


def _split_regions(document: DocumentIR):
    paragraphs = _paragraphs(document.blocks)
    heading_index = next(
        (i for i, block in enumerate(paragraphs)
         if _ANSWER_HEADING.fullmatch(block.text.strip())),
        None,
    )
    if heading_index is None:
        return paragraphs, paragraphs, False
    return paragraphs[:heading_index], paragraphs[heading_index + 1:], True


def _sequential_suffix_count(paragraphs) -> int:
    markers = []
    for index, block in enumerate(paragraphs):
        match = _SUFFIX.fullmatch(block.text.strip())
        if match and index > 0:
            markers.append((index, int(match.group(1))))
    if len(markers) < 2:
        return 0

    # Isolated numeric paragraphs are meaningful only when they form a
    # repeated sequence. This avoids treating page numbers as question IDs.
    runs = []
    current = [markers[0]]
    for marker in markers[1:]:
        if marker[1] == current[-1][1] + 1:
            current.append(marker)
        else:
            if len(current) >= 2:
                runs.append(current)
            current = [marker]
    if len(current) >= 2:
        runs.append(current)
    return sum(len(run) for run in runs)


def detect_templates(document: DocumentIR) -> TemplateDetection:
    question_blocks, answer_blocks, has_answer_heading = _split_regions(document)
    question_text = [block.text.strip() for block in question_blocks]
    answer_text = [block.text.strip() for block in answer_blocks]
    top_level_question_text = [
        block.text.strip() for block in question_blocks
        if block.position.row is None and block.position.column is None
    ]

    q_scores: Counter[str] = Counter()
    a_scores: Counter[str] = Counter()

    prefix_count = sum(bool(_PREFIX.match(text)) for text in top_level_question_text)
    suffix_count = _sequential_suffix_count(question_blocks)
    choice_count = sum(len(_CHOICE.findall(text)) for text in question_text)
    has_subjective_heading = any(_SUBJECTIVE_HEADING.search(text) for text in question_text)

    question_table_rows = sum(
        1 for block in document.blocks
        if block.kind == BlockKind.TABLE_ROW
        and block.position.paragraph <= (
            question_blocks[-1].position.paragraph if question_blocks else -1
        )
    )
    if question_table_rows:
        q_scores[QuestionTemplate.TABLE_ROWS.value] += question_table_rows
    if prefix_count:
        q_scores[QuestionTemplate.PREFIX_NUMBERED.value] += prefix_count
    if suffix_count:
        q_scores[QuestionTemplate.SUFFIX_NUMBERED.value] += suffix_count
    if has_subjective_heading and choice_count:
        q_scores[QuestionTemplate.MIXED.value] += max(2, prefix_count, suffix_count)

    # Inline answer markers may occur in the question area, not only after a
    # global answer heading.
    inline_count = sum(len(_INLINE.findall(text)) for text in question_text + answer_text)
    if inline_count:
        a_scores[AnswerTemplate.INLINE.value] += inline_count

    answer_blob = " ".join(answer_text)
    packed_matches = list(_PACKED.finditer(answer_blob))
    if len(packed_matches) >= 2:
        a_scores[AnswerTemplate.PACKED_KEY.value] += len(packed_matches)

    numbered_entries = sum(bool(_NUMBERED_ANSWER.match(text)) for text in answer_text)
    if has_answer_heading and numbered_entries >= 2:
        a_scores[AnswerTemplate.NUMBERED_ENTRIES.value] += numbered_entries

    subjective_answer = any(_SUBJECTIVE_HEADING.search(text) for text in answer_text)
    if subjective_answer:
        a_scores[AnswerTemplate.SUBJECTIVE.value] += 2

    # A document containing both a packed multiple-choice key and a
    # subjective answer section needs a composite answer adapter.
    if (
        a_scores[AnswerTemplate.PACKED_KEY.value]
        and a_scores[AnswerTemplate.SUBJECTIVE.value]
    ):
        a_scores[AnswerTemplate.MIXED.value] += (
            a_scores[AnswerTemplate.PACKED_KEY.value]
            + a_scores[AnswerTemplate.SUBJECTIVE.value]
        )

    q_normalized = _normalize(q_scores)
    a_normalized = _normalize(a_scores)
    warnings: list[str] = []

    def choose(scores: dict[str, float], unknown: str, label: str) -> str:
        if not scores:
            warnings.append(f"{label} 템플릿을 판별할 구조적 단서가 부족합니다.")
            return unknown
        ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
        if len(ranked) > 1 and ranked[0][1] - ranked[1][1] < 0.12:
            warnings.append(f"{label} 템플릿 후보가 경합합니다. 자동 선택하지 않습니다.")
            return unknown
        return ranked[0][0]

    qtype = choose(q_normalized, QuestionTemplate.UNKNOWN.value, "문항")
    atype = choose(a_normalized, AnswerTemplate.UNKNOWN.value, "정답")
    if not has_answer_heading and not inline_count:
        warnings.append("명시적인 정답 영역 표식을 찾지 못했습니다.")

    return TemplateDetection(
        QuestionTemplate(qtype),
        AnswerTemplate(atype),
        q_normalized,
        a_normalized,
        tuple(warnings),
    )
