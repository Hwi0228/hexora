"""Format dispatch for the HWP extraction core; no template decisions live here."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from ..models import DocumentIR
from .rhwp_reader import MAX_DOCUMENT_BYTES, RhwpReader


class HwpCoreExtractor:
    """Select a document reader and return source-ordered structural blocks."""

    def __init__(self, reader: Any | None = None) -> None:
        self.reader = reader or RhwpReader()

    def extract(self, path: Path) -> DocumentIR:
        path = Path(path)
        if path.suffix.lower() not in self.reader.supported_extensions:
            raise ValueError(
                "지원하는 문서 형식은 .hwp와 .hwpx입니다."
            )
        return self.reader.read(path)

    def extract_bytes(
        self, content: bytes, *, filename: str = "uploaded-document.hwp"
    ) -> DocumentIR:
        extension = Path(filename).suffix.lower()
        if extension not in self.reader.supported_extensions:
            raise ValueError("지원하는 문서 형식은 .hwp와 .hwpx입니다.")
        if len(content) > MAX_DOCUMENT_BYTES:
            raise ValueError("문서 크기가 허용 한도(12MB)를 초과합니다.")
        read_bytes = getattr(self.reader, "read_bytes", None)
        if not callable(read_bytes):
            raise TypeError("선택한 Reader는 바이트 입력을 지원하지 않습니다.")
        return read_bytes(content, filename=filename)
