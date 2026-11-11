import html
import re
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path
from unittest.mock import patch

from parse_hwp import (
    _equation_to_latex,
    normalize_katex_expression,
    parse_questions,
    parse_questions_from_xml,
)


def _canonical_latex(value: str) -> str:
    """Normalize equivalent TeX spellings for semantic assertions."""
    value = html.unescape(value)
    value = re.sub(r"([_^])\{([^{}])\}", r"\1\2", value)
    return re.sub(r"\s+", "", value)


def _embedded_latex(markup: str) -> list[str]:
    """Read math from serialized Quill HTML, decoding attribute entities."""
    values = re.findall(r'data-latex="([^"]*)"', markup)
    return [_canonical_latex(value) for value in values]


class HwpParsingTests(unittest.TestCase):
    @patch("parse_hwp.convert_hancom_to_latex", return_value=r"\frac{1}{2}")
    def test_prefers_hmleq_for_equation_scripts(self, convert):
        with patch.dict("os.environ", {"HMLEQ_USE_LEGACY": ""}):
            self.assertEqual(_equation_to_latex("1 over 2 `"), r"\frac{1}{2}")
        convert.assert_called_once_with("1 over 2")

    def test_extracts_question_choices_answer_explanation_and_math(self):
        xml = """\
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
         xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl>
    <hp:tr>
      <hp:tc>
        <hp:subList>
          <hp:p styleIDRef="45">
            <hp:run><hp:t>[정답] ③[해설]</hp:t><hp:pic/>
              <hp:t>계산하면 </hp:t>
              <hp:equation><hp:script>2+2 `</hp:script></hp:equation>
              <hp:t>문제 서두</hp:t>
            </hp:run>
          </hp:p>
          <hp:p styleIDRef="57"><hp:run><hp:t>[정답] ③</hp:t></hp:run></hp:p>
          <hp:p styleIDRef="57"><hp:run><hp:t>[해설]</hp:t></hp:run></hp:p>
          <hp:p styleIDRef="57">
            <hp:run><hp:t>계산하면 </hp:t>
              <hp:equation><hp:script>2+2 `</hp:script></hp:equation>
            </hp:run>
          </hp:p>
          <hp:p styleIDRef="21"><hp:run><hp:t>표에 있는 조건</hp:t></hp:run></hp:p>
          <hp:p styleIDRef="46"><hp:run><hp:t>마지막 문제 문장 [2점]</hp:t></hp:run></hp:p>
          <hp:p styleIDRef="52">
            <hp:run><hp:t>① 첫째 ② 둘째 ③ 셋째</hp:t></hp:run>
          </hp:p>
        </hp:subList>
      </hp:tc>
    </hp:tr>
  </hp:tbl>
</hs:sec>
"""
        with tempfile.TemporaryDirectory() as directory:
            xml_path = Path(directory) / "section0.xml"
            xml_path.write_text(xml, encoding="utf-8")

            questions = parse_questions(xml_path)

        self.assertEqual(
            {
                key: questions[0][key]
                for key in ("number", "question", "choices", "answer")
            },
            {
                "number": 1,
                "question": "문제 서두 표에 있는 조건 마지막 문제 문장 [그림]",
                "choices": ["첫째", "둘째", "셋째"],
                "answer": "③",
            },
        )
        self.assertTrue(questions[0]["explanation"].startswith("[그림] 계산하면 "))
        # hmleqx may serialize operator spacing as HTML character references;
        # x^2 and x^{2} are also equivalent TeX forms. Compare decoded math.
        self.assertEqual(_embedded_latex(questions[0]["explanation"]), ["2+2"])

    def test_converts_hml_equation_script_to_latex(self):
        xml = """\
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
         xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl><hp:tr><hp:tc><hp:subList>
    <hp:p styleIDRef="45"><hp:run><hp:t>[정답] ①[해설]풀이 </hp:t>
      <hp:equation><hp:script>LEFT ⌊ a+b RIGHT ⌋ `</hp:script></hp:equation>
      <hp:t>문제 본문</hp:t></hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:t>[정답] ①</hp:t></hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:t>[해설]</hp:t></hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:t>풀이 </hp:t>
      <hp:equation><hp:script>LEFT ⌊ a+b RIGHT ⌋ `</hp:script></hp:equation>
    </hp:run></hp:p>
  </hp:subList></hp:tc></hp:tr></hp:tbl>
</hs:sec>
"""

        questions = parse_questions_from_xml(xml.encode("utf-8"))

        self.assertIn('class="ql-math-inline"', questions[0]["explanation"])
        self.assertEqual(_embedded_latex(questions[0]["explanation"]), [r"\left\lfloora+b\right\rfloor"])
        self.assertEqual(questions[0]["question"], "문제 본문")

        bar_xml = xml.replace(
            "LEFT ⌊ a+b RIGHT ⌋",
            'bar {rm "AD" it} =x',
        )
        bar_questions = parse_questions_from_xml(bar_xml.encode("utf-8"))
        bar_latex = _embedded_latex(bar_questions[0]["explanation"])[0]
        self.assertIn(r"\overline", bar_latex)
        self.assertIn("AD", bar_latex)

        dot_xml = xml.replace(
            "LEFT ⌊ a+b RIGHT ⌋",
            "0 . dot {0} dot {2}",
        )
        dot_questions = parse_questions_from_xml(dot_xml.encode("utf-8"))
        self.assertIn(r"\dot{", dot_questions[0]["explanation"])
        self.assertIn("data-input-format=\"latex\"", dot_questions[0]["explanation"])

        angle_xml = xml.replace(
            "LEFT ⌊ a+b RIGHT ⌋",
            'angle rm "C" it = 90 DEG',
        )
        angle_questions = parse_questions_from_xml(angle_xml.encode("utf-8"))
        self.assertEqual(_embedded_latex(angle_questions[0]["explanation"]), [r"\angle\mathrm{C}=90\deg"])

    def test_preserves_fraction_commands_when_converting_hancom(self):
        xml = """\
<hs:sec xmlns:hs="http://www.hancom.co.kr/hwpml/2011/section"
         xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
  <hp:tbl><hp:tr><hp:tc><hp:subList>
    <hp:p styleIDRef="45"><hp:run><hp:t>[정답] ①[해설]</hp:t>
      <hp:equation><hp:script>{5} over {6} `</hp:script></hp:equation>
      <hp:t>문제 </hp:t><hp:equation><hp:script>{3} over {4} `</hp:script></hp:equation>
    </hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:t>[정답] ①</hp:t></hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:t>[해설]</hp:t></hp:run></hp:p>
    <hp:p styleIDRef="57"><hp:run><hp:equation><hp:script>{5} over {6} `</hp:script></hp:equation></hp:run></hp:p>
    <hp:p styleIDRef="52"><hp:run><hp:t>① </hp:t><hp:equation><hp:script>{7} over {8} `</hp:script></hp:equation></hp:run></hp:p>
  </hp:subList></hp:tc></hp:tr></hp:tbl>
</hs:sec>
"""

        question = parse_questions_from_xml(xml.encode("utf-8"))[0]

        self.assertIn(r"\frac{", question["question"])
        self.assertIn(r"\frac{", question["explanation"])
        self.assertIn(r"\frac{", question["choices"][0])
        self.assertNotIn(r"\dfrac", question["question"])

    def test_normalizes_hancom_braces_division_and_alignment_for_katex(self):
        brace_formula = _equation_to_latex(
            r"LEFT LBRACE {4} over {3} - LEFT ( - {1} over {3} RIGHT ) RIGHT RBRACE div LEFT ( - {1} over {9} RIGHT )"
        )
        self.assertEqual(
            _canonical_latex(brace_formula),
            _canonical_latex(
                r"\left\{\frac{4}{3}-\left(-\frac{1}{3}\right)\right\}\div\left(-\frac{1}{9}\right)"
            ),
        )

        aligned_formula = _equation_to_latex(
            r'EQALIGN { & rm "가입비 15000원" # & rm "- 가입 시 추가 요금 없이 무제한 편집 가능" }'
        )
        self.assertIn(r"\begin{aligned}", aligned_formula)
        self.assertIn(r"\text{가입비 15000원}", aligned_formula)
        self.assertIn(r"\text{- 가입 시 추가 요금 없이 무제한 편집 가능}", aligned_formula)
        self.assertIn(r"\end{aligned}", aligned_formula)

    def test_fraction_commands_are_preserved_for_katex(self):
        expression = r"\frac{a}{b} + \tfrac{c}{d} + \cfrac{1}{2} + \dfrac{3}{4}"
        self.assertEqual(normalize_katex_expression(expression), expression)

    def test_normalizes_legacy_formula_markup_for_existing_db_questions(self):
        expression = r"\frac{a}{b} + \tfrac{c}{d} + \cfrac{1}{2} + \dfrac{3}{4}"
        self.assertEqual(normalize_katex_expression(expression), expression)
        self.assertEqual(
            normalize_katex_expression(
                r"\eqalign{ & \mathrm{가입비 15000원} \\ & \mathrm{- 가입 시 추가 요금 없이 가능} }"
            ),
            r"\begin{aligned} & \text{가입비 15000원} \\ & \text{- 가입 시 추가 요금 없이 가능} \end{aligned}",
        )
        self.assertEqual(
            normalize_katex_expression(
                r"\left LBRACE \dfrac{4}{3} \right RBRACE div 2"
            ),
            r"\left \{ \dfrac{4}{3} \right \} \div 2",
        )


if __name__ == "__main__":
    unittest.main()
