"""Template adapter contracts and registry."""
from __future__ import annotations
from typing import Protocol
from .models import DocumentIR, ExtractedQuestion, TemplateDetection

class QuestionAdapter(Protocol):
    template: str
    def extract_questions(self, document: DocumentIR) -> list[ExtractedQuestion]: ...

class AnswerAdapter(Protocol):
    template: str
    def extract_answers(self, document: DocumentIR) -> dict[str, tuple[str | None, str | None]]: ...

class AdapterRegistry:
    def __init__(self) -> None:
        self.question_adapters: dict[str, QuestionAdapter] = {}
        self.answer_adapters: dict[str, AnswerAdapter] = {}
    def register_question(self, adapter: QuestionAdapter) -> None:
        self.question_adapters[adapter.template] = adapter
    def register_answer(self, adapter: AnswerAdapter) -> None:
        self.answer_adapters[adapter.template] = adapter
    def select(self, detection: TemplateDetection) -> tuple[QuestionAdapter | None, AnswerAdapter | None]:
        return (self.question_adapters.get(detection.question_template.value), self.answer_adapters.get(detection.answer_template.value))
