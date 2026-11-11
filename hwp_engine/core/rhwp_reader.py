"""rhwp-python adapter that preserves document structure without parsing questions."""
from __future__ import annotations

from collections import defaultdict
from importlib import import_module
from pathlib import Path
from typing import Any

from ..models import BlockKind, DocumentBlock, DocumentIR, SourcePosition

MAX_DOCUMENT_BYTES = 12 * 1024 * 1024

_KIND_MAP = {
    "paragraph": BlockKind.PARAGRAPH,
    "list_item": BlockKind.PARAGRAPH,
    "table": BlockKind.TABLE,
    "formula": BlockKind.FORMULA,
    "picture": BlockKind.PICTURE,
    "page_break": BlockKind.PAGE_BREAK,
    "pagebreak": BlockKind.PAGE_BREAK,
}

_SNAPSHOT_FIELDS = (
    "style_id", "para_style_id", "char_shape_id", "para_shape_id",
    "script", "text_alt", "description", "bin_id", "asset_id", "width",
    "height", "mime_type", "name",
)


def _kind(block: Any) -> str:
    value = getattr(block, "kind", "unknown")
    return str(getattr(value, "value", value)).lower()


def _provenance(block: Any) -> Any:
    return getattr(block, "prov", None)


def _position(block: Any, *, row: int | None = None, column: int | None = None) -> SourcePosition:
    prov = _provenance(block)
    return SourcePosition(
        section=int(getattr(prov, "section_idx", 0) or 0),
        paragraph=int(getattr(prov, "para_idx", 0) or 0),
        row=row,
        column=column,
        character=getattr(prov, "char_start", None),
    )


def _snapshot(block: Any) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for name in _SNAPSHOT_FIELDS:
        value = getattr(block, name, None)
        if isinstance(value, (str, int, float, bool)) or value is None:
            if value is not None:
                result[name] = value
    return result


def _source_key(block: Any) -> tuple[int, int, str, int | None]:
    pos = _position(block)
    return (pos.section, pos.paragraph, _kind(block), pos.character)


class RhwpReader:
    """Read HWP/HWPX through rhwp-python into a loss-minimizing DocumentIR."""

    supported_extensions = (".hwp", ".hwpx")

    def __init__(self, rhwp_module: Any | None = None) -> None:
        self._rhwp = rhwp_module

    def _module(self) -> Any:
        if self._rhwp is None:
            try:
                self._rhwp = import_module("rhwp")
            except ImportError as exc:
                raise RuntimeError(
                    "HWP/HWPX 추출 코어에는 rhwp-python이 필요합니다."
                ) from exc
        return self._rhwp

    def read(self, path: Path) -> DocumentIR:
        path = Path(path)
        return self.read_bytes(path.read_bytes(), filename=path.name)

    def read_bytes(self, content: bytes, *, filename: str = "uploaded-document") -> DocumentIR:
        if not content:
            raise ValueError("업로드한 문서가 비어 있습니다.")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError("문서 크기가 허용 한도(12MB)를 초과합니다.")

        try:
            module = self._module()
            document = module.Document.from_bytes(
                content, source_uri=f"upload://{Path(filename).name}"
            )
            ir = document.to_ir()
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise ValueError(f"rhwp-python이 문서 구조를 읽지 못했습니다: {exc}") from exc

        return self.from_ir(ir, filename=filename)

    @classmethod
    def from_ir(cls, ir: Any, *, filename: str = "") -> DocumentIR:
        iterator = getattr(ir, "iter_blocks", None)
        if not callable(iterator):
            raise ValueError("rhwp-python IR에 iter_blocks 인터페이스가 없습니다.")
        try:
            source_blocks = list(iterator(scope="body", recurse=True))
        except TypeError:
            source_blocks = list(iterator())

        output: list[DocumentBlock] = []
        table_child_ids: set[int] = set()
        table_child_keys: set[tuple[int, int, str, int | None]] = set()

        # Expand tables into explicit table/row/cell/child blocks. Cell boundaries
        # are retained instead of flattening their text into a single paragraph.
        for table_index, table in enumerate(b for b in source_blocks if _kind(b) == "table"):
            table_pos = _position(table)
            cells = list(getattr(table, "cells", []) or [])
            rows: dict[int, list[Any]] = defaultdict(list)
            for cell in cells:
                rows[int(getattr(cell, "row", 0) or 0)].append(cell)

            output.append(DocumentBlock(
                BlockKind.TABLE, table_pos, "",
                {"table_index": table_index, "row_count": len(rows), "cell_count": len(cells),
                 **_snapshot(table)},
            ))
            for row_number in sorted(rows):
                row_cells = sorted(
                    rows[row_number], key=lambda cell: int(getattr(cell, "col", 0) or 0)
                )
                output.append(DocumentBlock(
                    BlockKind.TABLE_ROW,
                    SourcePosition(table_pos.section, table_pos.paragraph, row=row_number),
                    "",
                    {"cell_count": len(row_cells)},
                ))
                for cell in row_cells:
                    column = int(getattr(cell, "col", 0) or 0)
                    output.append(DocumentBlock(
                        BlockKind.TABLE_CELL,
                        SourcePosition(table_pos.section, table_pos.paragraph,
                                       row=row_number, column=column),
                        "",
                        {"row": row_number, "column": column},
                    ))
                    children = list(getattr(cell, "blocks", []) or [])
                    children.sort(key=lambda item: (
                        _position(item).section, _position(item).paragraph,
                        _position(item).character if _position(item).character is not None else -1,
                    ))
                    for child in children:
                        table_child_ids.add(id(child))
                        table_child_keys.add(_source_key(child))
                        output.append(cls._convert_block(
                            child, row=row_number, column=column
                        ))

        # Keep body blocks not already represented inside a table cell.
        for block in source_blocks:
            kind = _kind(block)
            if kind == "table" or id(block) in table_child_ids:
                continue
            if _source_key(block) in table_child_keys and kind in {
                "paragraph", "list_item", "formula", "picture"
            }:
                continue
            output.append(cls._convert_block(block))

        # Stable ordering keeps inline objects at their original character offsets.
        priority = {
            BlockKind.TABLE: 0, BlockKind.TABLE_ROW: 1, BlockKind.TABLE_CELL: 2,
            BlockKind.PARAGRAPH: 3, BlockKind.FORMULA: 4, BlockKind.PICTURE: 5,
            BlockKind.PAGE_BREAK: 6, BlockKind.UNKNOWN: 7,
        }
        output.sort(key=lambda block: (
            block.position.section,
            block.position.paragraph,
            -1 if block.position.row is None else block.position.row,
            -1 if block.position.column is None else block.position.column,
            -1 if block.position.character is None else block.position.character,
            priority[block.kind],
        ))
        metadata = {
            "source_name": Path(filename).name if filename else "",
            "reader": "rhwp-python",
            "block_count": len(output),
        }
        return DocumentIR(
            source_format=Path(filename).suffix.lower().lstrip(".") or "unknown",
            blocks=tuple(output),
            metadata=metadata,
        )

    @staticmethod
    def _convert_block(
        block: Any, *, row: int | None = None, column: int | None = None
    ) -> DocumentBlock:
        raw_kind = _kind(block)
        kind = _KIND_MAP.get(raw_kind, BlockKind.UNKNOWN)
        position = _position(block, row=row, column=column)
        payload = _snapshot(block)
        text = ""

        if raw_kind in {"paragraph", "list_item"}:
            text = str(getattr(block, "text", "") or "")
        elif raw_kind == "formula":
            # Keep the original Hancom script; conversion belongs to a later layer.
            text = str(getattr(block, "script", "") or "")
            payload["original_script"] = text
            alt = getattr(block, "text_alt", None)
            if alt:
                payload["text_alt"] = str(alt)
        elif raw_kind == "picture":
            text = str(getattr(block, "description", "") or "")
            payload["asset_reference"] = (
                getattr(block, "bin_id", None) or getattr(block, "asset_id", None)
            )
        elif raw_kind not in {"table"}:
            value = getattr(block, "text", None)
            if value is not None:
                text = str(value)

        return DocumentBlock(kind, position, text, payload)
