import unittest

from hwp_engine.detection import detect_templates
from hwp_engine.models import (
    AnswerTemplate, BlockKind, DocumentBlock, DocumentIR,
    QuestionTemplate, SourcePosition,
)


def paragraph(text, index, *, row=None, column=None):
    return DocumentBlock(
        BlockKind.PARAGRAPH,
        SourcePosition(paragraph=index, row=row, column=column),
        text,
    )


class TemplateDetectionTests(unittest.TestCase):
    def test_prefix_questions_and_inline_answers(self):
        doc = DocumentIR("hwpx", (
            paragraph("1. 다음 중 옳은 것은?", 0),
            paragraph("① 가 ② 나", 1),
            paragraph("[정답] ② [해설] 나가 옳다.", 2),
        ))
        result = detect_templates(doc)
        self.assertEqual(result.question_template, QuestionTemplate.PREFIX_NUMBERED)
        self.assertEqual(result.answer_template, AnswerTemplate.INLINE)

    def test_suffix_questions_and_packed_answer_key(self):
        doc = DocumentIR("hwpx", (
            paragraph("삼각형의 넓이를 구하시오.", 0),
            paragraph("01", 1),
            paragraph("사각형의 넓이를 구하시오.", 2),
            paragraph("02", 3),
            paragraph("정답 및 해설", 4),
            paragraph("01 ⑤ 02 ③", 5),
        ))
        result = detect_templates(doc)
        self.assertEqual(result.question_template, QuestionTemplate.SUFFIX_NUMBERED)
        self.assertEqual(result.answer_template, AnswerTemplate.PACKED_KEY)

    def test_mixed_answer_key_supports_objective_and_subjective(self):
        doc = DocumentIR("hwpx", (
            paragraph("객관식", 0),
            paragraph("1. 다음 중 옳은 것은?", 1),
            paragraph("① 가 ② 나", 2),
            paragraph("주관식", 3),
            paragraph("다음 값을 구하시오.", 4),
            paragraph("01", 5),
            paragraph("정답 및 해설", 6),
            paragraph("01 ⑤ 02 ③", 7),
            paragraph("주관식 정답", 8),
            paragraph("24 3, 25 9", 9),
        ))
        result = detect_templates(doc)
        self.assertEqual(result.question_template, QuestionTemplate.MIXED)
        self.assertEqual(result.answer_template, AnswerTemplate.MIXED)

    def test_answer_table_does_not_override_question_template(self):
        blocks = [
            paragraph("1. 문항입니다.", 0),
            paragraph("정답 및 해설", 1),
            DocumentBlock(BlockKind.TABLE, SourcePosition(paragraph=2)),
            DocumentBlock(BlockKind.TABLE_ROW, SourcePosition(paragraph=2, row=0)),
            DocumentBlock(BlockKind.TABLE_CELL, SourcePosition(paragraph=2, row=0, column=0)),
            paragraph("01 ⑤ 02 ③", 3),
        ]
        result = detect_templates(DocumentIR("hwpx", tuple(blocks)))
        self.assertEqual(result.question_template, QuestionTemplate.PREFIX_NUMBERED)

    def test_unknown_document_does_not_guess(self):
        doc = DocumentIR("hwp", (paragraph("수학 학습 자료", 0),))
        result = detect_templates(doc)
        self.assertEqual(result.question_template, QuestionTemplate.UNKNOWN)
        self.assertEqual(result.answer_template, AnswerTemplate.UNKNOWN)
        self.assertTrue(result.warnings)


if __name__ == "__main__":
    unittest.main()
