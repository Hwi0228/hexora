import unittest
from pathlib import Path
from types import SimpleNamespace

from hwp_engine.core import HwpCoreExtractor, RhwpReader
from hwp_engine.models import BlockKind


class FakeIR:
    def __init__(self, blocks):
        self._blocks = blocks

    def iter_blocks(self, scope="body", recurse=True):
        return iter(self._blocks)


class FakeDocument:
    def __init__(self, ir):
        self._ir = ir

    def to_ir(self):
        return self._ir


class FakeRhwp:
    def __init__(self, ir):
        self.Document = SimpleNamespace(
            from_bytes=lambda content, source_uri: FakeDocument(ir)
        )


class CoreExtractorTests(unittest.TestCase):
    def make_ir(self):
        cell_text = SimpleNamespace(
            kind="paragraph", text="표 안의 문항", prov=SimpleNamespace(
                section_idx=0, para_idx=2, char_start=0
            )
        )
        cell_formula = SimpleNamespace(
            kind="formula", script="{a} over {b}", text_alt="a/b",
            prov=SimpleNamespace(section_idx=0, para_idx=2, char_start=5)
        )
        cell = SimpleNamespace(row=0, col=1, blocks=[cell_text, cell_formula])
        table = SimpleNamespace(
            kind="table", cells=[cell],
            prov=SimpleNamespace(section_idx=0, para_idx=2, char_start=None)
        )
        body = SimpleNamespace(
            kind="paragraph", text="본문 문단",
            prov=SimpleNamespace(section_idx=0, para_idx=3, char_start=0)
        )
        picture = SimpleNamespace(
            kind="picture", description="도형 이미지", bin_id="BIN0001",
            prov=SimpleNamespace(section_idx=0, para_idx=3, char_start=4)
        )
        return FakeIR([table, cell_text, cell_formula, body, picture])

    def test_reader_preserves_table_cell_formula_and_body_order(self):
        ir = self.make_ir()
        reader = RhwpReader(FakeRhwp(ir))
        document = reader.read_bytes(b"fake-hwp", filename="sample.hwpx")

        self.assertEqual(document.source_format, "hwpx")
        self.assertEqual([b.kind for b in document.blocks[:3]], [
            BlockKind.TABLE, BlockKind.TABLE_ROW, BlockKind.TABLE_CELL
        ])
        cell_formula = next(b for b in document.blocks if b.kind == BlockKind.FORMULA)
        self.assertEqual(cell_formula.text, "{a} over {b}")
        self.assertEqual(cell_formula.payload["original_script"], "{a} over {b}")
        self.assertEqual(cell_formula.position.row, 0)
        self.assertEqual(cell_formula.position.column, 1)
        self.assertEqual(cell_formula.position.character, 5)

        body = next(b for b in document.blocks if b.text == "본문 문단")
        picture = next(b for b in document.blocks if b.kind == BlockKind.PICTURE)
        self.assertEqual(body.position.paragraph, picture.position.paragraph)
        self.assertLess(body.position.character, picture.position.character)
        self.assertEqual(picture.payload["asset_reference"], "BIN0001")
        self.assertEqual(document.metadata["reader"], "rhwp-python")

    def test_core_rejects_unsupported_extension(self):
        extractor = HwpCoreExtractor()
        with self.assertRaises(ValueError):
            extractor.extract_bytes(b"data", filename="sample.pdf")

    def test_core_rejects_oversized_upload(self):
        class Reader:
            supported_extensions = (".hwp", ".hwpx")

        extractor = HwpCoreExtractor(Reader())
        with self.assertRaises(ValueError):
            extractor.extract_bytes(b"x" * (12 * 1024 * 1024 + 1), filename="x.hwp")


if __name__ == "__main__":
    unittest.main()
