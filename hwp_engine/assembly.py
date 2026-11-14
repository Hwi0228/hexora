"""Question/answer assembly and pre-persistence validation."""
from __future__ import annotations

from dataclasses import dataclass
import re

from .adapters import AdapterRegistry
from .detection import detect_templates
from .models import (
    AnswerTemplate, DocumentIR, ExtractedQuestion, QuestionTemplate,
    TemplateDetection,
)

CHOICE_LABELS = "①②③④⑤⑥⑦⑧⑨⑩"

@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: str
    message: str
    question_number: str | None = None
    severity: str = "error"

@dataclass(frozen=True, slots=True)
class AssembledQuestion:
    number: str
    question: str
    choices: tuple[str, ...]
    answer: str
    explanation: str
    source: object | None = None

@dataclass(frozen=True, slots=True)
class AssemblyResult:
    detection: TemplateDetection
    questions: tuple[AssembledQuestion, ...]
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not any(issue.severity == "error" for issue in self.issues)

    def as_payload(self) -> dict:
        return {
            "questions": [
                {
                    "number": index,
                    "source_number": item.number,
                    "question": item.question,
                    "choices": list(item.choices),
                    "answer": item.answer,
                    "explanation": item.explanation,
                    "source": (
                        {
                            "section": item.source.section,
                            "paragraph": item.source.paragraph,
                            "row": item.source.row,
                            "column": item.source.column,
                        } if item.source else None
                    ),
                }
                for index, item in enumerate(self.questions, 1)
            ],
            "validation": {
                "valid": self.valid,
                "issues": [
                    {
                        "code": issue.code,
                        "message": issue.message,
                        "question_number": issue.question_number,
                        "severity": issue.severity,
                    } for issue in self.issues
                ],
            },
            "detection": {
                "question_template": self.detection.question_template.value,
                "answer_template": self.detection.answer_template.value,
                "question_scores": self.detection.question_scores,
                "answer_scores": self.detection.answer_scores,
                "warnings": list(self.detection.warnings),
            },
        }

def _normalize_number(value: str) -> str:
    try:
        return str(int(value))
    except (TypeError, ValueError):
        return str(value).strip()

def _choice_values(question: ExtractedQuestion):
    return tuple(choice.content for choice in question.choices)

def validate_assembled(
    questions: list[AssembledQuestion],
    answer_map: dict[str, tuple[str | None, str | None]],
    *,
    answer_template: AnswerTemplate,
) -> tuple[ValidationIssue, ...]:
    issues = []
    seen = set()
    known = {_normalize_number(q.number) for q in questions}
    for question in questions:
        number = _normalize_number(question.number)
        if number in seen:
            issues.append(ValidationIssue("DUPLICATE_QUESTION_NUMBER", "문항 번호가 중복되었습니다.", number))
        seen.add(number)
        if not question.question.strip():
            issues.append(ValidationIssue("EMPTY_QUESTION", "문항 본문이 비어 있습니다.", number))
        if answer_template != AnswerTemplate.UNKNOWN and not question.answer.strip():
            issues.append(ValidationIssue("MISSING_ANSWER", "정답 템플릿은 감지되었지만 이 문항의 정답을 찾지 못했습니다.", number))
        if question.choices and question.answer:
            labels = set(re.findall(r"[①②③④⑤⑥⑦⑧⑨⑩]", question.answer))
            available = {CHOICE_LABELS[i] for i in range(len(question.choices))}
            invalid = labels - available
            if invalid:
                issues.append(ValidationIssue("ANSWER_OUT_OF_RANGE", f"선택지에 없는 정답 표식입니다: {', '.join(sorted(invalid))}", number))
    for number in answer_map:
        if _normalize_number(number) not in known:
            issues.append(ValidationIssue("ORPHAN_ANSWER", "연결할 문항이 없는 정답 항목입니다.", number))
    return tuple(issues)

def assemble_document(
    document: DocumentIR,
    registry: AdapterRegistry,
    *,
    detection: TemplateDetection | None = None,
) -> AssemblyResult:
    detection = detection or detect_templates(document)
    question_adapter, answer_adapter = registry.select(detection)
    issues = []
    if question_adapter is None:
        issues.append(ValidationIssue("UNKNOWN_QUESTION_TEMPLATE", "문항 템플릿을 확정하지 못했습니다. 미리보기에서 구조를 확인해 주세요."))
        return AssemblyResult(detection, (), tuple(issues))
    extracted = question_adapter.extract_questions(document)
    if not extracted:
        issues.append(ValidationIssue("NO_QUESTIONS", "문항 어댑터가 문항을 추출하지 못했습니다."))
        return AssemblyResult(detection, (), tuple(issues))
    answer_map = answer_adapter.extract_answers(document) if answer_adapter else {}
    assembled = []
    for question in extracted:
        number = _normalize_number(question.source_number)
        inline_answer = question.answer or ""
        inline_explanation = question.explanation or ""
        external = answer_map.get(number)
        answer = inline_answer
        explanation = inline_explanation
        if external:
            if inline_answer and external[0] and inline_answer.strip() != external[0].strip():
                issues.append(ValidationIssue("ANSWER_CONFLICT", "문항 내장 정답과 별도 정답표가 서로 다릅니다.", number))
            elif not answer:
                answer = external[0] or ""
            if not explanation:
                explanation = external[1] or ""
        assembled.append(AssembledQuestion(
            number=number,
            question=question.content,
            choices=_choice_values(question),
            answer=answer,
            explanation=explanation,
            source=question.source,
        ))
    issues.extend(validate_assembled(
        assembled, answer_map, answer_template=detection.answer_template
    ))
    for warning in detection.warnings:
        issues.append(ValidationIssue("TEMPLATE_WARNING", warning, severity="warning"))
    return AssemblyResult(detection, tuple(assembled), tuple(issues))
