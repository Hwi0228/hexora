"""Reader/extractor interfaces. Readers do not classify questions."""
from __future__ import annotations
from pathlib import Path
from typing import Protocol
from ..models import DocumentIR

class DocumentReader(Protocol):
    supported_extensions: tuple[str, ...]
    def read(self, path: Path) -> DocumentIR:
        """Read document structure without deciding what is a question or answer."""

class CoreExtractor(Protocol):
    def extract(self, path: Path) -> DocumentIR:
        """Select a format reader and return a source-ordered document IR."""
