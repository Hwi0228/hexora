"""Independent answer-key template adapters."""
from __future__ import annotations

import re

from .models import AnswerTemplate, BlockKind, DocumentIR

_ANSWER_HEADING = re.compile(
    r"^\s*(?:(?:[ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ]+)\s*[.)]?\s*)?"
    r"(?:정\s*답(?:\s*(?:\(해\s*설\)|및\s*해\s*설|과\s*해\s*설))?|정답\s*/\s*해설)\s*$"
)
_SUBJECTIVE_HEADING = re.compile(r"주\s*관\s*식|서\s*술\s*형|단\s*답\s*형")
_INLINE = re.compile(r"(?:\[\s*정답\s*\]|\(\s*답\s*\)|정답\s*[:：])\s*")
_NUMBERED = re.compile(
    r"^\s*(?:(?:제\s*)?(\d{1,3})\s*[.)]|(\d{1,3})\s*번)\s*"
    r"(?:(?:\[\s*답\s*\]|\(\s*답\s*\)|답)\s*[:：]?\s*)?(.*)$",
    re.I,
)
_CHOICE_ANSWER = re.compile(r"^[①②③④⑤⑥⑦⑧⑨⑩](?:\s*[,、/]\s*[①②③④⑤⑥⑦⑧⑨⑩])*$")
_PACKED = re.compile(r"(?<!\d)(\d{1,3})\s*([①②③④⑤⑥⑦⑧⑨⑩](?:\s*[,、/]\s*[①②③④⑤⑥⑦⑧⑨⑩])*)")

def _paragraphs(document):
    return [b for b in document.blocks if b.kind == BlockKind.PARAGRAPH and b.text.strip()]

def _answer_region(document):
    blocks = _paragraphs(document)
    heading = next((i for i, b in enumerate(blocks) if _ANSWER_HEADING.fullmatch(b.text.strip())), None)
    if heading is None:
        return [], []
    region = blocks[heading + 1:]
    subjective = next((i for i, b in enumerate(region) if _SUBJECTIVE_HEADING.search(b.text)), None)
    if subjective is None:
        return region, []
    return region[:subjective], region[subjective + 1:]

def _norm_number(value):
    return str(int(value))

def _extract_inline_answer(text):
    marker = _INLINE.search(text)
    if not marker:
        return None
    tail = text[marker.end():]
    explanation_match = re.search(r"(?:\[\s*해설\s*\]|\(\s*해설\s*\)|해설\s*[:：])", tail)
    if explanation_match:
        answer = tail[:explanation_match.start()].strip()
        explanation = tail[explanation_match.end():].strip()
    else:
        answer, explanation = tail.strip(), ""
    return answer, explanation

class InlineAnswerAdapter:
    template = AnswerTemplate.INLINE.value
    def extract_answers(self, document: DocumentIR):
        result = {}
        for block in _paragraphs(document):
            parsed = _extract_inline_answer(block.text)
            if parsed is None:
                continue
            match = _NUMBERED.match(block.text)
            number = _norm_number(next((g for g in match.groups()[:2] if g), str(len(result) + 1))) if match else str(len(result) + 1)
            if number in result:
                continue
            result[number] = parsed
        return result

class NumberedAnswerAdapter:
    template = AnswerTemplate.NUMBERED_ENTRIES.value
    def extract_answers(self, document: DocumentIR):
        entries, _ = _answer_region(document)
        result, current, explanation = {}, None, []
        for block in entries:
            match = _NUMBERED.match(block.text)
            if match:
                if current is not None:
                    answer, *rest = current
                    result[current[0]] = (answer, "\n".join(explanation).strip() or rest[0])
                number = _norm_number(match.group(1) or match.group(2))
                tail = match.group(3).strip()
                parsed = _extract_inline_answer(tail)
                if parsed:
                    current = (number, parsed[0], parsed[1])
                else:
                    current = (number, tail, "")
                explanation = []
            elif current is not None:
                clean = re.sub(r"^(?:\[\s*해설\s*\]|\(\s*해설\s*\)|해설\s*[:：])\s*", "", block.text.strip())
                if clean:
                    explanation.append(clean)
        if current is not None:
            result[current[0]] = (current[1], "\n".join([current[2], *explanation]).strip())
        return result

class PackedAnswerAdapter:
    template = AnswerTemplate.PACKED_KEY.value
    def extract_answers(self, document: DocumentIR):
        entries, _ = _answer_region(document)
        text = "\n".join(block.text for block in entries)
        result = {}
        for match in _PACKED.finditer(text):
            number = _norm_number(match.group(1))
            answer = re.sub(r"\s+", "", match.group(2))
            if number in result:
                # Duplicate keys are retained as an explicit conflict by the assembler.
                result[number] = (result[number][0] + " | " + answer, result[number][1])
            else:
                result[number] = (answer, "")
        return result

class SubjectiveAnswerAdapter:
    template = AnswerTemplate.SUBJECTIVE.value
    def extract_answers(self, document: DocumentIR):
        _, entries = _answer_region(document)
        result = {}
        for block in entries:
            text = block.text.strip()
            if not text or _SUBJECTIVE_HEADING.search(text):
                continue
            # Accept numbered lines such as "24 3", "25. x=4", or "1번: 12".
            match = re.match(r"^\s*(\d{1,3})\s*(?:번|[.)])?\s*[:：]?\s+(.+?)\s*$", text)
            if match:
                number, answer = _norm_number(match.group(1)), match.group(2).strip()
                if number in result:
                    result[number] = (result[number][0] + " | " + answer, result[number][1])
                else:
                    result[number] = (answer, "")
        return result

class MixedAnswerAdapter:
    template = AnswerTemplate.MIXED.value
    def extract_answers(self, document: DocumentIR):
        combined = {}
        for adapter in (PackedAnswerAdapter(), SubjectiveAnswerAdapter(), NumberedAnswerAdapter()):
            for number, value in adapter.extract_answers(document).items():
                if number in combined and combined[number][0] != value[0]:
                    combined[number] = (combined[number][0] + " | " + value[0], combined[number][1] + "\n" + value[1])
                else:
                    combined[number] = value
        return combined

def answer_adapters():
    return (
        InlineAnswerAdapter(), NumberedAnswerAdapter(),
        PackedAnswerAdapter(), SubjectiveAnswerAdapter(), MixedAnswerAdapter(),
    )
