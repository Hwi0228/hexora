import unittest

import fitz

from pdf_parser import parse_questions_from_pdf_bytes


def make_pdf(pages):
    document = fitz.open()
    for lines in pages:
        page = document.new_page()
        for index, line in enumerate(lines):
            font = "korea" if any(ord(character) > 127 for character in line) else "helv"
            page.insert_text(
                (54, 60 + index * 18),
                line,
                fontsize=11,
                fontname=font,
            )
    result = document.tobytes()
    document.close()
    return result


class PdfQuestionParserTests(unittest.TestCase):
    def test_extracts_numbered_question_choices_answer_and_explanation(self):
        content = make_pdf([[
            "1. 다음 식의 값은?",
            "① 1 ② 2 ③ 3",
            "[정답] ②",
            "[해설] 1 + 1 = 2.",
        ]])

        questions = parse_questions_from_pdf_bytes(content, "sample.pdf")

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["source_number"], 1)
        self.assertEqual(questions[0]["source_page"], 1)
        self.assertEqual(questions[0]["choices"], ["1", "2", "3"])
        self.assertEqual(questions[0]["answer"], "②")
        self.assertIn("1 + 1 = 2", questions[0]["explanation"])

    def test_preserves_page_number_for_questions_on_later_pages(self):
        content = make_pdf([
            ["수학 단원 평가"],
            [
                "2. x + 3 = 7일 때 x의 값은?",
                "[정답] 4",
            ],
        ])

        questions = parse_questions_from_pdf_bytes(content, "two-pages.pdf")

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["source_number"], 2)
        self.assertEqual(questions[0]["source_page"], 2)

    def test_rejects_image_only_pdf_with_ocr_guidance(self):
        document = fitz.open()
        document.new_page()
        content = document.tobytes()
        document.close()

        with self.assertRaisesRegex(ValueError, "OCR"):
            parse_questions_from_pdf_bytes(content, "scanned.pdf")

    def test_rejects_invalid_pdf(self):
        with self.assertRaisesRegex(ValueError, "손상"):
            parse_questions_from_pdf_bytes(b"not a PDF", "broken.pdf")

    def test_rejects_non_pdf_extension(self):
        with self.assertRaisesRegex(ValueError, "PDF 파일만"):
            parse_questions_from_pdf_bytes(b"%PDF-1.4", "exam.hwp")


    def test_decodes_hyhwp_eq_latin_digits_and_operators(self):
        from pdf_hwp_equation import decode_hyhwp_equation_text

        encoded = "\\ue0ea\\ue044\\ue0fc\\ue045\\ue047\\ue03d"
        self.assertEqual(
            decode_hyhwp_equation_text(encoded, "ABCDEF+HyhwpEQ"),
            "f(x)=0",
        )

    def test_decodes_hyhwp_eq_greek_and_structural_glyphs(self):
        from pdf_hwp_equation import decode_hyhwp_equation_text

        encoded = "\\ue088\\ue09d\\ue0ac \\ue05c\\ue06d\\ue06e"
        self.assertEqual(
            decode_hyhwp_equation_text(encoded, "HyhwpEQ"),
            "Δα\\pi \\sqrt\\over\\vec",
        )

    def test_does_not_decode_pua_from_unrelated_fonts(self):
        from pdf_hwp_equation import decode_hyhwp_equation_text

        encoded = "\\ue0ea\\ue044\\ue0fc"
        self.assertEqual(
            decode_hyhwp_equation_text(encoded, "ABCDEF+ArialMT"),
            encoded,
        )

    def test_preserves_unknown_hyhwp_eq_private_use_glyphs(self):
        from pdf_hwp_equation import decode_hyhwp_equation_text

        encoded = "\\ue0ea\\ue123\\ue044"
        self.assertEqual(
            decode_hyhwp_equation_text(encoded, "HyhwpEQ"),
            "f\\ue123(",
        )

    def test_extracts_pdf_lines_in_visual_order_and_decodes_equation_spans(self):
        from pdf_hwp_equation import extract_pdf_page_lines

        class FakePage:
            def get_text(self, mode, sort=False):
                self.asserted = (mode, sort)
                return {
                    "blocks": [
                        {
                            "lines": [
                                {
                                    "bbox": (0, 10, 100, 20),
                                    "spans": [
                                        {"bbox": (30, 10, 40, 20), "text": "\\ue0fc", "font": "HyhwpEQ"},
                                        {"bbox": (10, 10, 20, 20), "text": "\\ue0ea", "font": "HyhwpEQ"},
                                    ],
                                },
                                {
                                    "bbox": (0, 30, 100, 40),
                                    "spans": [
                                        {"bbox": (10, 30, 20, 40), "text": "문항", "font": "MalgunGothic"},
                                    ],
                                },
                            ]
                        }
                    ]
                }

        page = FakePage()
        self.assertEqual(extract_pdf_page_lines(page), ["fx", "문항"])
        self.assertEqual(page.asserted, ("dict", True))


if __name__ == "__main__":
    unittest.main()
