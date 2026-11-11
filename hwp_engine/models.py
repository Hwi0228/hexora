"""Loss-minimizing document IR and normalized parser models."""
from __future__ import annotations
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any

class BlockKind(StrEnum):
    PARAGRAPH = "paragraph"
    TABLE = "table"
    TABLE_ROW = "table_row"
    TABLE_CELL = "table_cell"
    FORMULA = "formula"
    PICTURE = "picture"
    PAGE_BREAK = "page_break"
    UNKNOWN = "unknown"

@dataclass(frozen=True, slots=True)
class SourcePosition:
    section: int = 0
    paragraph: int = 0
    row: int | None = None
    column: int | None = None
    character: int | None = None

@dataclass(frozen=True, slots=True)
class DocumentBlock:
    kind: BlockKind
    position: SourcePosition
    text: str = ""
    payload: dict[str, Any] = field(default_factory=dict)

@dataclass(frozen=True, slots=True)
class DocumentIR:
    source_format: str
    blocks: tuple[DocumentBlock, ...]
    metadata: dict[str, Any] = field(default_factory=dict)

    def paragraphs(self) -> tuple[DocumentBlock, ...]:
        return tuple(b for b in self.blocks if b.kind == BlockKind.PARAGRAPH)

    def tables(self) -> tuple[DocumentBlock, ...]:
        return tuple(b for b in self.blocks if b.kind == BlockKind.TABLE)

class QuestionTemplate(StrEnum):
    TABLE_ROWS = "table_rows"
    PREFIX_NUMBERED = "prefix_numbered"
    SUFFIX_NUMBERED = "suffix_numbered"
    MIXED = "mixed"
    UNKNOWN = "unknown"

class AnswerTemplate(StrEnum):
    INLINE = "inline"
    NUMBERED_ENTRIES = "numbered_entries"
    PACKED_KEY = "packed_key"
    SUBJECTIVE = "subjective"
    MIXED = "mixed"
    UNKNOWN = "unknown"

@dataclass(frozen=True, slots=True)
class TemplateDetection:
    question_template: QuestionTemplate
    answer_template: AnswerTemplate
    question_scores: dict[str, float] = field(default_factory=dict)
    answer_scores: dict[str, float] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

@dataclass(frozen=True, slots=True)
class ExtractedChoice:
    label: str
    content: str
    source: SourcePosition

@dataclass(frozen=True, slots=True)
class ExtractedQuestion:
    source_number: str
    content: str
    choices: tuple[ExtractedChoice, ...] = ()
    answer: str | None = None
    explanation: str | None = None
    source: SourcePosition | None = None
    confidence: float = 1.0
    warnings: tuple[str, ...] = ()
