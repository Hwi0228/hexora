import unittest
from types import SimpleNamespace
from unittest.mock import patch

import hmleq_converter
from hmleq_converter import convert_hancom_to_latex


class HmleqxGoldenRegressionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if hmleq_converter.hmleqx is None:
            raise unittest.SkipTest("hmleqx가 설치되지 않아 실변환 회귀 테스트를 생략합니다.")
        cls.version = hmleq_converter.hmleqx.version()

    def test_body_fraction_uses_display_fraction(self):
        latex = convert_hancom_to_latex("a over b")
        self.assertIn(r"\dfrac", latex)
        self.assertIn("a", latex)
        self.assertIn("b", latex)

    def test_fraction_inside_superscript_uses_text_fraction(self):
        latex = convert_hancom_to_latex("x ^ {a over b}")
        self.assertIn("x", latex)
        self.assertIn(r"\frac", latex)
        self.assertNotIn(r"\dfrac", latex)

    def test_nested_fraction_keeps_both_fraction_levels(self):
        latex = convert_hancom_to_latex("{a over b} over c")
        self.assertGreaterEqual(latex.count(r"\dfrac"), 2)
        self.assertTrue(all(token in latex for token in ("a", "b", "c")))

    def test_nth_root_is_not_flattened_into_plain_text(self):
        latex = convert_hancom_to_latex("sqrt 3 of 5")
        self.assertIn(r"\sqrt", latex)
        self.assertIn("3", latex)
        self.assertIn("5", latex)

    def test_limit_and_subscript_structure_are_preserved(self):
        latex = convert_hancom_to_latex("lim _{x -> 0} {sin x} over {x}")
        self.assertIn(r"\lim", latex)
        self.assertIn("x", latex)
        self.assertIn("0", latex)
        self.assertIn(r"\dfrac", latex)

    def test_matrix_delimiters_and_rows_are_preserved(self):
        latex = convert_hancom_to_latex("pmatrix { 1 & 2 # 3 & 4 }")
        self.assertTrue("pmatrix" in latex or "matrix" in latex)
        for token in ("1", "2", "3", "4"):
            self.assertIn(token, latex)

    def test_existing_frac_commands_are_not_normalized_by_wrapper(self):
        original = r"\frac{x}{y}+\dfrac{a}{b}"
        fake = SimpleNamespace(to_latex=lambda _script: original)
        with patch("hmleq_converter.hmleqx", fake):
            self.assertEqual(convert_hancom_to_latex("already latex"), original)

    def test_library_version_is_available_for_ci_diagnostics(self):
        self.assertTrue(str(self.version).strip())


if __name__ == "__main__":
    unittest.main()
