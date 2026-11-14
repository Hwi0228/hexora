from __future__ import annotations

import ctypes
import html
import importlib.util
import re
import stat
import zipfile
from io import BytesIO
from pathlib import PurePosixPath

from defusedxml import ElementTree as SafeET
from defusedxml.common import DefusedXmlException
from pathlib import Path
from collections import OrderedDict
from typing import Any, Iterable

from parse_hwp import _equation_to_latex
from rhwp_question_parser import (
    CHOICE_PATTERN,
    _compact,
    _parse_numbered_paragraphs,
    _parse_question_row,
    parse_numbered_document_sections,
)


MAX_DOCUMENT_BYTES = 12 * 1024 * 1024
MAX_PARSED_QUESTIONS = 500
MAX_HWPX_ENTRIES = 1024
MAX_HWPX_UNCOMPRESSED_BYTES = 64 * 1024 * 1024
MAX_HWPX_MEMBER_BYTES = 16 * 1024 * 1024
MAX_HWPX_XML_FILES = 128
MAX_HWPX_XML_NODES = 200_000
MAX_HWPX_XML_DEPTH = 128


def _validate_hwpx_archive(content: bytes) -> None:
    """Reject malformed or resource-exhausting HWPX ZIP packages before parsing."""
    try:
        archive = zipfile.ZipFile(BytesIO(content))
    except (zipfile.BadZipFile, OSError) as exc:
        raise ValueError("HWPX 파일이 올바른 ZIP 문서가 아닙니다.") from exc

    with archive:
        entries = archive.infolist()
        if not entries or len(entries) > MAX_HWPX_ENTRIES:
            raise ValueError("HWPX 내부 파일 개수가 허용 한도(1,024개)를 벗어났습니다.")

        total_uncompressed = 0
        xml_entries = 0
        for info in entries:
            normalized_name = info.filename.replace("\\", "/")
            member_path = PurePosixPath(normalized_name)
            mode = info.external_attr >> 16
            if (
                member_path.is_absolute()
                or ".." in member_path.parts
                or "\x00" in info.filename
                or stat.S_ISLNK(mode)
            ):
                raise ValueError("HWPX 내부에 허용되지 않는 파일 경로가 있습니다.")
            if info.flag_bits & 0x1:
                raise ValueError("암호화된 HWPX 내부 파일은 처리할 수 없습니다.")
            if info.file_size > MAX_HWPX_MEMBER_BYTES:
                raise ValueError("HWPX 내부 단일 파일이 허용 한도(16 MiB)를 초과합니다.")
            total_uncompressed += info.file_size
            if total_uncompressed > MAX_HWPX_UNCOMPRESSED_BYTES:
                raise ValueError("HWPX 압축 해제 총량이 허용 한도(64 MiB)를 초과합니다.")
            if (
                info.file_size > 1024 * 1024
                and info.file_size / max(info.compress_size, 1) > 200
            ):
                raise ValueError("HWPX 내부 파일의 압축률이 비정상적으로 높습니다.")

            if info.filename.lower().endswith((".xml", ".rdf")):
                xml_entries += 1
                if xml_entries > MAX_HWPX_XML_FILES:
                    raise ValueError("HWPX XML 파일 개수가 허용 한도(128개)를 초과합니다.")
                try:
                    xml_bytes = archive.read(info)
                    root = SafeET.fromstring(xml_bytes)
                except (
                    DefusedXmlException, SafeET.ParseError, RuntimeError,
                    zipfile.BadZipFile, OSError,
                ) as exc:
                    raise ValueError("HWPX 내부 XML이 안전하지 않거나 손상되었습니다.") from exc

                stack = [(root, 1)]
                node_count = 0
                while stack:
                    node, depth = stack.pop()
                    node_count += 1
                    if node_count > MAX_HWPX_XML_NODES:
                        raise ValueError("HWPX XML 요소 수가 허용 한도(200,000개)를 초과합니다.")
                    if depth > MAX_HWPX_XML_DEPTH:
                        raise ValueError("HWPX XML 중첩 깊이가 허용 한도(128단계)를 초과합니다.")
                    stack.extend((child, depth + 1) for child in node)

        if xml_entries == 0:
            raise ValueError("HWPX 문서에서 XML 콘텐츠를 찾지 못했습니다.")


def _preload_bundled_freetype() -> None:
    """Prefer the deploy-bundled FreeType over an older host system library."""
    candidates = (
        Path(__file__).resolve().parent
        / ".render-libs"
    ).rglob("libfreetype.so.6")
    library = next(candidates, None)
    if library is not None:
        ctypes.CDLL(str(library), mode=ctypes.RTLD_GLOBAL)


_preload_bundled_freetype()


def _kind(block: Any) -> str:
    return str(getattr(block, "kind", ""))


def _provenance_key(block: Any) -> tuple[int, int]:
    provenance = getattr(block, "prov", None)
    return (
        int(getattr(provenance, "section_idx", 0)),
        int(getattr(provenance, "para_idx", 0)),
    )


def _render_formula(block: Any, *, display_mode: bool = False) -> str:
    """한컴 수식을 편집기에서 재사용 가능한 Quill 수식 Embed로 직렬화한다."""
    script = str(getattr(block, "script", "") or "").strip()
    if not script:
        return ""
    try:
        latex = _equation_to_latex(script)
    except Exception:
        latex = str(getattr(block, "text_alt", "") or script).strip()
    if not latex:
        return ""

    tag = "div" if display_mode else "span"
    blot = "ql-math-block" if display_mode else "ql-math-inline"
    # Encode spaces in attributes so the paragraph compactor cannot alter the
    # original Hancom source before the rich-text sanitizer decodes it.
    latex_attr = html.escape(latex, quote=True).replace(" ", "&#32;")
    source_attr = html.escape(script, quote=True).replace(" ", "&#32;")
    return (
        f'<{tag} class="{blot}" data-latex="{latex_attr}" '
        f'data-input-format="hancom" data-input-source="{source_attr}" '
        f'data-math-object="{"block" if display_mode else "inline"}"></{tag}>'
    )


def _render_picture(block: Any) -> str:
    description = str(getattr(block, "description", "") or "").strip()
    if description:
        description = re.sub(r"\s+", " ", description)
        return f"[그림: {description}]"
    return "[그림]"


def _insert_inline_events(text: str, events: list[tuple[int | None, int, str]]) -> str:
    """char_start가 있는 컨트롤은 위치에 삽입하고, 위치가 없는 것은 문단 끝에 붙인다."""
    positioned = sorted(
        (event for event in events if event[0] is not None),
        key=lambda event: (event[0], event[1]),
    )
    trailing = [event[2] for event in events if event[0] is None]
    parts: list[str] = []
    cursor = 0
    for offset, _, rendered in positioned:
        position = max(cursor, min(int(offset), len(text)))
        parts.append(text[cursor:position])
        parts.append(rendered)
        cursor = position
    parts.append(text[cursor:])
    parts.extend(trailing)
    return "".join(parts)


def _paragraphs_from_cell(cell: Any) -> list[str]:
    """rhwp IR의 셀 블록을 문단 순서로 복원한다."""
    entries: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()
    for block in getattr(cell, "blocks", []):
        kind = _kind(block)
        key = _provenance_key(block)
        if kind in {"paragraph", "list_item"}:
            entry = entries.setdefault(key, {"text": "", "events": []})
            entry["text"] = str(getattr(block, "text", "") or "")
        elif kind in {"formula", "picture"}:
            entry = entries.setdefault(key, {"text": "", "events": []})
            provenance = getattr(block, "prov", None)
            char_start = getattr(provenance, "char_start", None)
            rendered = (
                _render_formula(block, display_mode=char_start is None)
                if kind == "formula" else _render_picture(block)
            )
            if rendered:
                entry["events"].append((char_start, len(entry["events"]), rendered))

    return [
        _insert_inline_events(entry["text"], entry["events"]).strip()
        for entry in entries.values()
        if entry["text"].strip() or entry["events"]
    ]


def _iter_tables(ir: Any) -> Iterable[Any]:
    iterator = getattr(ir, "iter_blocks", None)
    if not callable(iterator):
        raise ValueError("rhwp-python 문서에서 구조화 블록을 읽을 수 없습니다.")
    for block in iterator(scope="body", recurse=True):
        if _kind(block) == "table":
            yield block


def _paragraphs_from_document(ir: Any) -> list[str]:
    """표 구조에 의존하지 않고 본문 문단을 문서 순서대로 평문화한다."""
    iterator = getattr(ir, "iter_blocks", None)
    if not callable(iterator):
        return []

    entries: OrderedDict[tuple[int, int], dict[str, Any]] = OrderedDict()
    anonymous_index = 0
    for block in iterator(scope="body", recurse=True):
        kind = _kind(block)
        if kind not in {"paragraph", "list_item", "formula", "picture"}:
            continue

        provenance = getattr(block, "prov", None)
        if provenance is None:
            key = (10**9, anonymous_index)
            anonymous_index += 1
        else:
            key = _provenance_key(block)
        entry = entries.setdefault(key, {"text": "", "events": []})

        if kind in {"paragraph", "list_item"}:
            value = str(getattr(block, "text", "") or "")
            if value and value != entry["text"]:
                entry["text"] = (
                    f'{entry["text"]} {value}'.strip() if entry["text"] else value
                )
        else:
            char_start = getattr(provenance, "char_start", None)
            rendered = (
                _render_formula(block, display_mode=char_start is None)
                if kind == "formula" else _render_picture(block)
            )
            if rendered:
                entry["events"].append((char_start, len(entry["events"]), rendered))

    return [
        _compact(_insert_inline_events(entry["text"], entry["events"]))
        for entry in entries.values()
        if entry["text"].strip() or entry["events"]
    ]


def parse_questions_from_ir(ir: Any) -> list[dict[str, Any]]:
    """구조화된 정답/해설 표를 우선 처리하고, 일반 문단형 문서로 폴백한다."""
    questions: list[dict[str, Any]] = []
    for table in _iter_tables(ir):
        rows: dict[int, list[Any]] = {}
        for cell in getattr(table, "cells", []):
            rows.setdefault(int(getattr(cell, "row", 0)), []).append(cell)

        for row_number in sorted(rows):
            paragraphs: list[str] = []
            for cell in sorted(rows[row_number], key=lambda value: int(getattr(value, "col", 0))):
                paragraphs.extend(_paragraphs_from_cell(cell))
            parsed = _parse_question_row(paragraphs, len(questions) + 1)
            if parsed is not None:
                questions.append(parsed)

    if questions:
        if len(questions) > MAX_PARSED_QUESTIONS:
            raise ValueError("가져온 문항 수가 허용 한도(500개)를 초과했습니다.")
        return questions

    questions = parse_numbered_document_sections(_paragraphs_from_document(ir))
    if len(questions) > MAX_PARSED_QUESTIONS:
        raise ValueError("가져온 문항 수가 허용 한도(500개)를 초과했습니다.")
    if not questions:
        raise ValueError(
            "문항을 찾지 못했습니다. 문항 번호(예: 1.)로 시작하는 문단이나 "
            "[정답]/[해설] 표시가 있는 문항 표가 포함되어 있는지 확인해 주세요."
        )
    return questions


def parse_questions_from_rhwp_bytes(
    content: bytes, filename: str = "uploaded-document"
) -> list[dict[str, Any]]:
    """HWP/HWPX bytes를 rhwp-python으로 파싱한 뒤 ALEPH MATH 문항 구조로 변환한다."""
    if not content:
        raise ValueError("업로드한 문서가 비어 있습니다.")
    if len(content) > MAX_DOCUMENT_BYTES:
        raise ValueError("문서 크기가 허용 한도(12 MiB)를 초과합니다.")
    if Path(filename).suffix.lower() == ".hwpx":
        _validate_hwpx_archive(content)

    if importlib.util.find_spec("rhwp") is None:
        raise RuntimeError(
            "HWP/HWPX 파싱에 필요한 rhwp-python이 설치되지 않았습니다. "
            "requirements.txt의 의존성을 설치해 주세요."
        )

    try:
        _preload_bundled_freetype()
        import rhwp

        document = rhwp.Document.from_bytes(content, source_uri=f"upload://{filename}")
        ir = document.to_ir()
    except Exception as exc:
        # A present package can still fail to import because of an incompatible
        # optional/native dependency. Do not misreport that as a missing package.
        raise ValueError(f"rhwp-python이 문서를 해석하지 못했습니다: {exc}") from exc

    return parse_questions_from_ir(ir)
