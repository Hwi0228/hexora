"""Question template adapters that preserve source provenance."""
from __future__ import annotations

import re
from collections import defaultdict

from .models import (
    BlockKind, DocumentIR, ExtractedChoice, ExtractedQuestion, QuestionTemplate,
)

_PREFIX = re.compile(
    r"^\s*(?:(?:제\s*)?(\d{1,3})\s*[.)]|(\d{1,3})\s*번(?:\s*[.)])?|Q\s*(\d{1,3})\s*[.:)])",
    re.I,
)
_SUFFIX = re.compile(r"^\s*0?(\d{1,3})\s*$")
_CHOICE = re.compile(r"([①②③④⑤⑥⑦⑧⑨⑩])\s*")
_ANSWER_HEADING = re.compile(
    r"^\s*(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.)]?\s*)?"
    r"(?:정\s*답(?:\s*(?:\(해\s*설\)|및\s*해\s*설|과\s*해\s*설))?|정답\s*/\s*해설)\s*$"
)

def _question_blocks(document: DocumentIR):
    paragraphs = [b for b in document.blocks if b.kind == BlockKind.PARAGRAPH and b.text.strip()]
    heading = next((i for i, b in enumerate(paragraphs) if _ANSWER_HEADING.fullmatch(b.text.strip())), None)
    return paragraphs if heading is None else paragraphs[:heading]

def _number(match: re.Match) -> str:
    return next(group for group in match.groups() if group is not None).lstrip("0") or "0"

def _split_choices(text: str, source):
    matches = list(_CHOICE.finditer(text))
    if not matches:
        return text.strip(), ()
    stem = text[:matches[0].start()].strip()
    choices = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        content = text[match.end():end].strip()
        if content:
            choices.append(ExtractedChoice(match.group(1), content, source))
    return stem, tuple(choices)

def _make_question(number: str, parts: list, source):
    text = "\n".join(value.strip() for value in parts if value and value.strip()).strip()
    content, choices = _split_choices(text, source)
    if not content and not choices:
        return None
    return ExtractedQuestion(number, content, choices, source=source)

class PrefixQuestionAdapter:
    template = QuestionTemplate.PREFIX_NUMBERED.value
    def extract_questions(self, document: DocumentIR) -> list[ExtractedQuestion]:
        result, number, parts, source = [], None, [], None
        for block in _question_blocks(document):
            match = _PREFIX.match(block.text)
            if match:
                if number is not None:
                    item = _make_question(number, parts, source)
                    if item: result.append(item)
                number = _number(match)
                source = block.position
                parts = [block.text[match.end():]]
            elif number is not None:
                parts.append(block.text)
        if number is not None:
            item = _make_question(number, parts, source)
            if item: result.append(item)
        return result

class SuffixQuestionAdapter:
    template = QuestionTemplate.SUFFIX_NUMBERED.value
    def extract_questions(self, document: DocumentIR) -> list[ExtractedQuestion]:
        blocks = _question_blocks(document)
        markers = []
        for index, block in enumerate(blocks):
            match = _SUFFIX.fullmatch(block.text.strip())
            if match and index > 0:
                markers.append((index, str(int(match.group(1)))))
        if len(markers) < 2:
            return []
        # Only accept sequential marker runs; isolated page numbers are ignored.
        runs, current = [], [markers[0]]
        for marker in markers[1:]:
            if int(marker[1]) == int(current[-1][1]) + 1:
                current.append(marker)
            else:
                if len(current) >= 2: runs.append(current)
                current = [marker]
        if len(current) >= 2: runs.append(current)
        accepted = {index: number for run in runs for index, number in run}
        result, parts, source = [], [], None
        for index, block in enumerate(blocks):
            if index in accepted:
                item = _make_question(accepted[index], parts, source)
                if item: result.append(item)
                parts, source = [], None
            else:
                if source is None: source = block.position
                parts.append(block.text)
        return result

class TableQuestionAdapter:
    template = QuestionTemplate.TABLE_ROWS.value
    def extract_questions(self, document: DocumentIR) -> list[ExtractedQuestion]:
        rows = defaultdict(list)
        for block in document.blocks:
            if block.kind == BlockKind.PARAGRAPH and block.position.row is not None:
                key = (block.position.section, block.position.paragraph, block.position.row)
                rows[key].append(block)
        result = []
        for key, blocks in sorted(rows.items()):
            blocks.sort(key=lambda b: (
                -1 if b.position.column is None else b.position.column,
                -1 if b.position.character is None else b.position.character,
            ))
            cells = defaultdict(list)
            for block in blocks:
                cells[block.position.column or 0].append(block.text)
            number = None
            parts = []
            for column in sorted(cells):
                value = "\n".join(cells[column]).strip()
                if number is None:
                    prefix = _PREFIX.match(value)
                    if prefix:
                        number = _number(prefix)
                        value = value[prefix.end():].strip()
                    elif re.fullmatch(r"\d{1,3}", value):
                        number = str(int(value))
                        value = ""
                if value:
                    parts.append(value)
            if number is None:
                number = str(len(result) + 1)
            source = blocks[0].position
            item = _make_question(number, parts, source)
            if item: result.append(item)
        return result

class MixedQuestionAdapter:
    template = QuestionTemplate.MIXED.value
    def extract_questions(self, document: DocumentIR) -> list[ExtractedQuestion]:
        prefix = PrefixQuestionAdapter().extract_questions(document)
        suffix = SuffixQuestionAdapter().extract_questions(document)
        combined = {(
            item.source.section if item.source else 0,
            item.source.paragraph if item.source else 0,
            item.source.row if item.source else None,
            item.source.column if item.source else None,
        ): item for item in prefix + suffix}
        return sorted(combined.values(), key=lambda q: (
            q.source.section if q.source else 0,
            q.source.paragraph if q.source else 0,
        ))

def question_adapters():
    return (
        TableQuestionAdapter(), PrefixQuestionAdapter(),
        SuffixQuestionAdapter(), MixedQuestionAdapter(),
    )
