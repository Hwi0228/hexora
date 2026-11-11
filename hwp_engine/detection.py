"""Advisory template detection; it never mutates or drops source blocks."""
from __future__ import annotations
import re
from collections import Counter
from .models import AnswerTemplate, BlockKind, DocumentIR, QuestionTemplate, TemplateDetection

_PREFIX = re.compile(r"^\s*(?:(?:제\s*)?\d{1,3}\s*[.)]|\d{1,3}\s*번|Q\s*\d{1,3})", re.I)
_SUFFIX = re.compile(r"^\s*0?\d{1,3}\s*$")
_PACKED = re.compile(r"(?<!\d)\d{1,2}\s*[①-⑳]")
_INLINE = re.compile(r"(?:\[정답\]|\(답\)|정답\s*[:：])")
_ANSWER_HEADING = re.compile(r"^\s*(?:정답|정답\s*(?:및|과)\s*해설|정답\s*\(해설\))\s*$")

def _normalize(scores: Counter[str]) -> dict[str, float]:
    total = sum(scores.values())
    return {key: round(value / total, 3) for key, value in scores.items()} if total else {}

def detect_templates(document: DocumentIR) -> TemplateDetection:
    paragraphs = [b.text.strip() for b in document.blocks if b.kind == BlockKind.PARAGRAPH and b.text.strip()]
    kinds = Counter(b.kind for b in document.blocks)
    q, a = Counter(), Counter()
    prefix_count = sum(bool(_PREFIX.match(text)) for text in paragraphs)
    suffix_count = sum(bool(_SUFFIX.fullmatch(text)) for text in paragraphs)
    headings = [i for i, text in enumerate(paragraphs) if _ANSWER_HEADING.fullmatch(text)]
    answer_text = " ".join(paragraphs[headings[0] + 1:]) if headings else " ".join(paragraphs)
    if kinds[BlockKind.TABLE] or kinds[BlockKind.TABLE_ROW] or kinds[BlockKind.TABLE_CELL]:
        q[QuestionTemplate.TABLE_ROWS.value] += max(1, kinds[BlockKind.TABLE_ROW])
    if prefix_count:
        q[QuestionTemplate.PREFIX_NUMBERED.value] += prefix_count
    if suffix_count:
        q[QuestionTemplate.SUFFIX_NUMBERED.value] += suffix_count
    if prefix_count and any(re.search(r"주관식|서술형|단답형", text) for text in paragraphs):
        q[QuestionTemplate.MIXED.value] += 1
    if _INLINE.search(answer_text):
        a[AnswerTemplate.INLINE.value] += len(_INLINE.findall(answer_text))
    if headings and re.search(r"(?m)^\s*\d{1,3}\s*[.)]", answer_text):
        a[AnswerTemplate.NUMBERED_ENTRIES.value] += 1
    if _PACKED.search(answer_text):
        a[AnswerTemplate.PACKED_KEY.value] += len(_PACKED.findall(answer_text))
    if re.search(r"주관식|서술형|단답형", answer_text):
        a[AnswerTemplate.SUBJECTIVE.value] += 1
    qs, ans = _normalize(q), _normalize(a)
    qtype = max(qs, key=qs.get) if qs else QuestionTemplate.UNKNOWN.value
    atype = max(ans, key=ans.get) if ans else AnswerTemplate.UNKNOWN.value
    warnings = []
    if not qs:
        warnings.append("문항 템플릿을 판별할 구조적 단서가 부족합니다.")
    elif len(qs) > 1 and sorted(qs.values(), reverse=True)[0] - sorted(qs.values(), reverse=True)[1] < .15:
        warnings.append("문항 템플릿 후보가 비슷해 추가 검토가 필요합니다.")
    if not ans:
        warnings.append("정답 템플릿을 판별하지 못했습니다. 정답이 없는 문서일 수 있습니다.")
    return TemplateDetection(QuestionTemplate(qtype), AnswerTemplate(atype), qs, ans, tuple(warnings))
