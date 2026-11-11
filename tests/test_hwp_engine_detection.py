import unittest
from hwp_engine.detection import detect_templates
from hwp_engine.models import BlockKind, DocumentBlock, DocumentIR, SourcePosition

class TemplateDetectionTests(unittest.TestCase):
    def test_prefix_questions_and_inline_answers(self):
        doc = DocumentIR("hwpx", (
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "1. 다음 중 옳은 것은?"),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=1), "① 가 ② 나"),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=2), "[정답] ② [해설] 나가 옳다."),
        ))
        result = detect_templates(doc)
        self.assertEqual(result.question_template.value, "prefix_numbered")
        self.assertEqual(result.answer_template.value, "inline")

    def test_suffix_questions_and_packed_answer_key(self):
        doc = DocumentIR("hwpx", (
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "삼각형의 넓이를 구하시오."),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=1), "01"),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=2), "사각형의 넓이를 구하시오."),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=3), "02"),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=4), "정답 및 해설"),
            DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=5), "01 ⑤ 02 ③"),
        ))
        result = detect_templates(doc)
        self.assertEqual(result.question_template.value, "suffix_numbered")
        self.assertEqual(result.answer_template.value, "packed_key")

    def test_unknown_document_does_not_guess(self):
        doc = DocumentIR("hwp", (DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(), "수학 학습 자료"),))
        result = detect_templates(doc)
        self.assertEqual(result.question_template.value, "unknown")
        self.assertEqual(result.answer_template.value, "unknown")
        self.assertTrue(result.warnings)

if __name__ == "__main__":
    unittest.main()
