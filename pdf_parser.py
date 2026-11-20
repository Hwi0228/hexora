"""Text-based PDF question extraction for HEXORA.

The parser deliberately does not OCR image-only pages. It extracts selectable
PDF text, then reuses the numbered-question and answer-key parser used by HWP.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import fitz

from pdf_hwp_equation import extract_pdf_page_lines

from rhwp_question_parser import (
    _ANSWER_SECTION_HEADING,
    _QUESTION_START,
    _compact,
    parse_numbered_document_sections,
)


MAX_PDF_BYTES = 12 * 1024 * 1024
MAX_PDF_PAGES = 200
MAX_PDF_QUESTIONS = 500

def _extract_page_paragraphs(page: fitz.Page) -> list[str]:
    """Extract selectable text while decoding font-scoped HyhwpEQ glyphs."""
    paragraphs: list[str] = []
    for raw_line in extract_pdf_page_lines(page):
        line = re.sub(r"[\t\u00a0 ]+", " ", raw_line).strip()
        if not line:
            continue
        # Page-number-only lines are not useful question content.
        if re.fullmatch(r"(?:-\s*)?\d{1,3}(?:\s*-)?", line):
            continue
        paragraphs.append(line)
    return paragraphs


def parse_questions_from_pdf_bytes(
    content: bytes,
    filename: str = "uploaded-document.pdf",
) -> list[dict[str, Any]]:
    """Parse numbered questions from a text-based PDF.

    Returned fields follow the HWP importer contract and additionally carry
    source_page/source_number for provenance. No source file is written to disk.
    """
    if not content:
        raise ValueError("업로드한 PDF가 비어 있습니다.")
    if len(content) > MAX_PDF_BYTES:
        raise ValueError("PDF 크기가 허용 한도(12 MiB)를 초과합니다.")
    if Path(filename).suffix.lower() != ".pdf":
        raise ValueError("PDF 파일만 처리할 수 있습니다.")

    try:
        document = fitz.open(stream=content, filetype="pdf")
    except (fitz.FileDataError, RuntimeError, ValueError) as exc:
        raise ValueError("PDF 파일이 손상되었거나 올바른 PDF가 아닙니다.") from exc

    with document:
        if document.needs_pass:
            raise ValueError("암호가 설정된 PDF는 처리할 수 없습니다.")
        if document.page_count < 1:
            raise ValueError("PDF에 페이지가 없습니다.")
        if document.page_count > MAX_PDF_PAGES:
            raise ValueError(
                f"PDF 페이지 수가 허용 한도({MAX_PDF_PAGES}페이지)를 초과합니다."
            )

        paragraphs: list[str] = []
        question_starts: list[tuple[int, int]] = []
        in_answer_section = False

        for page_number, page in enumerate(document, start=1):
            page_paragraphs = _extract_page_paragraphs(page)
            for paragraph in page_paragraphs:
                normalized = _compact(paragraph)
                if _ANSWER_SECTION_HEADING.fullmatch(normalized):
                    in_answer_section = True
                if not in_answer_section:
                    match = _QUESTION_START.match(normalized)
                    if match:
                        source_number = int(
                            match.group(1) or match.group(2) or match.group(3)
                        )
                        question_starts.append((source_number, page_number))
                paragraphs.append(paragraph)

        if not paragraphs:
            raise ValueError(
                "PDF에서 선택 가능한 텍스트를 찾지 못했습니다. "
                "스캔 이미지 PDF는 현재 OCR을 지원하지 않습니다."
            )

        if any("\ufffd" in paragraph for paragraph in paragraphs):
            raise ValueError(
                "PDF 글꼴 인코딩을 해석하지 못한 문자가 있습니다. "
                "텍스트가 선택되는 PDF인지 확인해 주세요."
            )

        questions = parse_numbered_document_sections(paragraphs)
        if not questions:
            raise ValueError(
                "문항을 찾지 못했습니다. '1.', '1)', '1번' 등 문항 번호로 "
                "시작하는 텍스트가 있는지 확인해 주세요."
            )
        if len(questions) > MAX_PDF_QUESTIONS:
            raise ValueError(
                f"문항 수가 허용 한도({MAX_PDF_QUESTIONS}개)를 초과합니다."
            )

        # Keep all detected questions, including questions without an answer key.
        # Filtering here would also shift the source-page provenance.
        return [
            {
                **question,
                "number": index + 1,
                "source_number": (
                    question_starts[index][0]
                    if index < len(question_starts)
                    else question.get("number", index + 1)
                ),
                "source_page": (
                    question_starts[index][1]
                    if index < len(question_starts)
                    else None
                ),
            }
            for index, question in enumerate(questions)
        ]
