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


if __name__ == "__main__":
    unittest.main()
