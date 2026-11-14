import unittest

from hwp_engine.adapters import default_registry
from hwp_engine.assembly import assemble_document
from hwp_engine.detection import detect_templates
from hwp_engine.models import (
    BlockKind, DocumentBlock, DocumentIR, SourcePosition,
    QuestionTemplate, AnswerTemplate,
)

def p(text, index, *, row=None, column=None):
    return DocumentBlock(
        BlockKind.PARAGRAPH,
        SourcePosition(paragraph=index, row=row, column=column),
        text,
    )

def table_row(index, row):
    return DocumentBlock(
        BlockKind.TABLE_ROW, SourcePosition(paragraph=index, row=row)
    )

class QuestionAdapterTests(unittest.TestCase):
    def setUp(self):
        self.registry = default_registry()

    def test_prefix_questions_and_numbered_answers_are_assembled(self):
        doc = DocumentIR("hwpx", (
            p("1. 다음 중 옳은 것은?", 0),
            p("① 가 ② 나", 1),
            p("2. 다음 중 바른 것은?", 2),
            p("① 다 ② 라", 3),
            p("정답 및 해설", 4),
            p("1. (답) ②", 5),
            p("(해설) 첫 번째 풀이", 6),
            p("2. (답) ①", 7),
            p("(해설) 두 번째 풀이", 8),
        ))
        result = assemble_document(doc, self.registry)
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(result.detection.question_template, QuestionTemplate.PREFIX_NUMBERED)
        self.assertEqual(result.detection.answer_template, AnswerTemplate.NUMBERED_ENTRIES)
        self.assertEqual([q.answer for q in result.questions], ["②", "①"])
        self.assertEqual(result.questions[0].explanation, "첫 번째 풀이")
        self.assertEqual(result.as_payload()["detection"]["question_evidence"]["prefix_markers"], 2)

    def test_suffix_question_adapter_uses_repeated_sequential_markers(self):
        doc = DocumentIR("hwpx", (
            p("삼각형의 넓이를 구하시오.", 0),
            p("01", 1),
            p("사각형의 넓이를 구하시오.", 2),
            p("02", 3),
            p("정답 및 해설", 4),
            p("01 ⑤ 02 ③", 5),
        ))
        result = assemble_document(doc, self.registry)
        self.assertEqual(result.detection.question_template, QuestionTemplate.SUFFIX_NUMBERED)
        self.assertEqual(result.detection.answer_template, AnswerTemplate.PACKED_KEY)
        self.assertEqual([q.number for q in result.questions], ["1", "2"])
        self.assertEqual([q.answer for q in result.questions], ["⑤", "③"])

    def test_table_adapter_preserves_row_and_cell_boundaries(self):
        doc = DocumentIR("hwpx", (
            table_row(0, 0),
            p("1", 0, row=0, column=0),
            p("다음 식의 값을 구하시오. ① 1 ② 2", 0, row=0, column=1),
            table_row(1, 1),
            p("2", 1, row=1, column=0),
            p("다음 중 옳은 것은? ① 가 ② 나", 1, row=1, column=1),
        ))
        detection = detect_templates(doc)
        self.assertEqual(detection.question_template, QuestionTemplate.TABLE_ROWS)
        adapter, _ = self.registry.select(detection)
        questions = adapter.extract_questions(doc)
        self.assertEqual([q.source_number for q in questions], ["1", "2"])
        self.assertEqual(len(questions[0].choices), 2)

    def test_inline_answer_adapter_extracts_embedded_answers(self):
        doc = DocumentIR("hwpx", (
            p("1. 다음 중 옳은 것은?", 0),
            p("① 가 ② 나", 1),
            p("[정답] ② [해설] 나가 옳다.", 2),
        ))
        result = assemble_document(doc, self.registry)
        self.assertEqual(result.detection.answer_template, AnswerTemplate.INLINE)
        self.assertEqual(result.questions[0].answer, "②")
        self.assertEqual(result.questions[0].explanation, "나가 옳다.")

    def test_subjective_answer_adapter_preserves_equation_text(self):
        doc = DocumentIR("hwpx", (
            p("1. 값을 구하시오.", 0),
            p("정답 및 해설", 1),
            p("주관식 정답", 2),
            p("1  x=\\dfrac{1}{2}", 3),
        ))
        result = assemble_document(doc, self.registry)
        self.assertEqual(result.detection.answer_template, AnswerTemplate.SUBJECTIVE)
        self.assertEqual(result.questions[0].answer, r"x=\dfrac{1}{2}")

    def test_mixed_answer_template_combines_packed_and_subjective_entries(self):
        doc = DocumentIR("hwpx", (
            p("객관식", 0),
            p("1. 다음 중 옳은 것은?", 1),
            p("① 가 ② 나", 2),
            p("주관식", 3),
            p("2. 값을 구하시오.", 4),
            p("3. 다음 중 바른 것은?", 5),
            p("① 다 ② 라", 6),
            p("정답 및 해설", 7),
            p("01 ② 03 ③", 8),
            p("주관식 정답", 9),
            p("02 24", 10),
        ))
        result = assemble_document(doc, self.registry)
        self.assertEqual(result.detection.question_template, QuestionTemplate.MIXED)
        self.assertEqual(result.detection.answer_template, AnswerTemplate.MIXED)
        self.assertEqual([q.answer for q in result.questions], ["②", "24", "③"])

    def test_validator_rejects_missing_out_of_range_and_orphan_answers(self):
        doc = DocumentIR("hwpx", (
            p("1. 다음 중 옳은 것은?", 0),
            p("① 가 ② 나", 1),
            p("2. 다음 중 바른 것은?", 2),
            p("① 다 ② 라", 3),
            p("정답 및 해설", 4),
            p("1. (답) ⑤", 5),
            p("2. (답) ①", 6),
            p("9. (답) ①", 7),
        ))
        result = assemble_document(doc, self.registry)
        codes = {issue.code for issue in result.issues}
        self.assertIn("ANSWER_OUT_OF_RANGE", codes)
        self.assertIn("ORPHAN_ANSWER", codes)
        self.assertFalse(result.valid)

if __name__ == "__main__":
    unittest.main()
