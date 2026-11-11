import unittest
from types import SimpleNamespace

from parse_rhwp import parse_questions_from_ir


def provenance(index, char_start=None):
    return SimpleNamespace(section_idx=0, para_idx=index, char_start=char_start)


def paragraph(text, index):
    return SimpleNamespace(kind="paragraph", text=text, prov=provenance(index))


class RhwpQuestionParserTests(unittest.TestCase):
    def build_ir(self, blocks):
        cell = SimpleNamespace(row=0, col=0, blocks=blocks)
        table = SimpleNamespace(kind="table", cells=[cell])
        return SimpleNamespace(
            iter_blocks=lambda scope="body", recurse=True: iter([table])
        )

    def test_extracts_question_answer_explanation_and_choices(self):
        blocks = [
            paragraph('[정답] ②[해설]이 값은 <span class="ql-math-inline" data-latex="1+1" data-input-format="hancom" data-input-source="1+1" data-math-object="inline"></span> 문제 본문', 0),
            paragraph("[정답] ②", 1),
            paragraph("[해설]", 2),
            paragraph("이 값은 ", 3),
            SimpleNamespace(
                kind="formula",
                script="1+1",
                text_alt="1 + 1",
                prov=provenance(3, char_start=len("이 값은 ")),
            ),
            paragraph("추가 조건을 고려하시오.", 4),
            paragraph("① 하나 ② 둘", 5),
        ]
        questions = parse_questions_from_ir(self.build_ir(blocks))
        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["number"], 1)
        self.assertEqual(questions[0]["answer"], "②")
        self.assertIn('class="ql-math-inline"', questions[0]["explanation"])
        self.assertIn('data-latex="1+1"', questions[0]["explanation"])
        self.assertEqual(questions[0]["question"], "문제 본문 추가 조건을 고려하시오.")
        self.assertEqual(questions[0]["choices"], ["하나", "둘"])

    def test_picture_block_is_preserved_as_a_placeholder(self):
        blocks = [
            paragraph("[정답] ①[해설]풀이 문제 본문", 0),
            paragraph("[정답] ①", 1),
            paragraph("[해설]", 2),
            paragraph("풀이", 3),
            paragraph("그림을 참고하시오.", 4),
            SimpleNamespace(
                kind="picture",
                description="좌표평면",
                prov=provenance(4, char_start=None),
            ),
        ]
        questions = parse_questions_from_ir(self.build_ir(blocks))
        self.assertIn("[그림: 좌표평면]", questions[0]["question"])

    def test_ignores_tables_without_question_markers(self):
        blocks = [paragraph("일반적인 표 내용", 0)]
        with self.assertRaisesRegex(ValueError, "문항을 찾지 못했습니다"):
            parse_questions_from_ir(self.build_ir(blocks))


if __name__ == "__main__":
    unittest.main()


class RhwpFlexibleDocumentTests(unittest.TestCase):

    def test_matches_separate_answer_sections_by_unit_and_question_number(self):
        blocks = [
            paragraph("Ⅰ. 수와 연산", 0),
            paragraph("소인수분해", 1),
            paragraph("1. 12의 약수를 고르시오.", 2),
            paragraph("보기: 1, 2, 3, 4", 3),
            paragraph("① 1 ② 2", 4),
            paragraph("2. 18의 약수를 고르시오.", 5),
            paragraph("① 1 ② 3", 6),
            paragraph("최대공약수와 최소공배수", 7),
            paragraph("1. 두 수의 최대공약수를 구하시오.", 8),
            paragraph("① 2 ② 3", 9),
            paragraph("정답 (해설)", 10),
            paragraph("소인수분해", 11),
            paragraph("1. (답) ④", 12),
            paragraph("(해설)", 13),
            paragraph("첫 번째 풀이입니다.", 14),
            paragraph("2. (답) ②", 15),
            paragraph("(해설) 두 번째 풀이입니다.", 16),
            paragraph("최대공약수와 최소공배수", 17),
            paragraph("1. (답) ①", 18),
            paragraph("(해설) 세 번째 풀이입니다.", 19),
        ]
        ir = SimpleNamespace(iter_blocks=lambda scope="body", recurse=True: iter(blocks))

        questions = parse_questions_from_ir(ir)

        self.assertEqual(len(questions), 3)
        self.assertEqual([item["number"] for item in questions], [1, 2, 3])
        self.assertEqual(questions[0]["answer"], "④")
        self.assertEqual(questions[0]["explanation"], "첫 번째 풀이입니다.")
        self.assertEqual(questions[1]["answer"], "②")
        self.assertEqual(questions[1]["explanation"], "두 번째 풀이입니다.")
        self.assertEqual(questions[2]["answer"], "①")
        self.assertEqual(questions[2]["explanation"], "세 번째 풀이입니다.")
        self.assertIn("보기: 1, 2, 3, 4", questions[0]["question"])
        self.assertEqual(questions[0]["choices"], ["1", "2"])

    def test_does_not_treat_answer_entries_as_new_questions(self):
        blocks = [
            paragraph("소인수분해", 0),
            paragraph("1. 문제 본문", 1),
            paragraph("① 가 ② 나", 2),
            paragraph("정답 (해설)", 3),
            paragraph("1. (답) ②", 4),
            paragraph("(해설) 정답은 나입니다.", 5),
        ]
        ir = SimpleNamespace(iter_blocks=lambda scope="body", recurse=True: iter(blocks))

        questions = parse_questions_from_ir(ir)

        self.assertEqual(len(questions), 1)
        self.assertEqual(questions[0]["question"], "문제 본문")
        self.assertEqual(questions[0]["answer"], "②")
        self.assertEqual(questions[0]["explanation"], "정답은 나입니다.")

    def test_parses_numbered_paragraph_document_without_answer_or_explanation(self):
        blocks = [
            paragraph("Ⅰ. 세계화 시대, 지리의 힘", 0),
            paragraph("1. 지역의 자연환경 특성을 파악하고자 할 때 조사할 내용으로 옳은 것은?", 1),
            paragraph("① 교통 ② 기후 ③ 산업", 2),
            paragraph("④ 문화 ⑤ 인구", 3),
            paragraph("2. ㉠에 들어갈 용어로 옳은 것은?", 4),
            paragraph("( ㉠ )은/는 일정한 곳에 차지하고 있는 자리를 말한다.", 5),
            paragraph("① 기후 ② 위치 ③ 장소 ④ 인문환경 ⑤ 자연환경", 6),
        ]
        ir = SimpleNamespace(iter_blocks=lambda scope="body", recurse=True: iter(blocks))

        questions = parse_questions_from_ir(ir)

        self.assertEqual(len(questions), 2)
        self.assertEqual(questions[0]["question"], "지역의 자연환경 특성을 파악하고자 할 때 조사할 내용으로 옳은 것은?")
        self.assertEqual(questions[0]["choices"], ["교통", "기후", "산업", "문화", "인구"])
        self.assertEqual(questions[0]["answer"], "")
        self.assertEqual(questions[0]["explanation"], "")
        self.assertEqual(questions[1]["choices"], ["기후", "위치", "장소", "인문환경", "자연환경"])
        self.assertEqual(questions[1]["question"], "㉠에 들어갈 용어로 옳은 것은? ( ㉠ )은/는 일정한 곳에 차지하고 있는 자리를 말한다.")

    def test_parses_optional_answer_and_explanation_markers(self):
        blocks = [
            paragraph("1. 다음 중 옳은 것은?", 0),
            paragraph("① 가 ② 나", 1),
            paragraph("[정답] ②", 2),
            paragraph("[해설] 나가 옳습니다.", 3),
        ]
        ir = SimpleNamespace(iter_blocks=lambda scope="body", recurse=True: iter(blocks))

        question = parse_questions_from_ir(ir)[0]

        self.assertEqual(question["answer"], "②")
        self.assertEqual(question["explanation"], "나가 옳습니다.")
        self.assertEqual(question["choices"], ["가", "나"])

    def test_keeps_formula_and_picture_content_in_unstructured_paragraphs(self):
        blocks = [
            paragraph("1. 다음 그림과 수식을 참고하시오.", 0),
            SimpleNamespace(
                kind="formula",
                script="x^2",
                text_alt="x squared",
                prov=provenance(0, char_start=len("1. 다음 그림과 수식을 참고하시오.")),
            ),
            SimpleNamespace(
                kind="picture",
                description="좌표평면",
                prov=provenance(0, char_start=None),
            ),
        ]
        ir = SimpleNamespace(iter_blocks=lambda scope="body", recurse=True: iter(blocks))

        question = parse_questions_from_ir(ir)[0]

        self.assertIn('class="ql-math-inline"', question["question"])
        self.assertIn('data-latex="x^2"', question["question"])
        self.assertIn("[그림: 좌표평면]", question["question"])
