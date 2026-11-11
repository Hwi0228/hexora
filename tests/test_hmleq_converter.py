import unittest
from types import SimpleNamespace
from unittest.mock import patch

from hmleq_converter import HmleqConversionError, HmleqUnavailable, convert_hancom_to_latex

class HmleqxConverterTests(unittest.TestCase):
    @patch("hmleq_converter.hmleqx", SimpleNamespace(to_latex=lambda script: r"\frac{a}{b}" + "\n"))
    def test_calls_python_api_and_returns_latex(self):
        self.assertEqual(convert_hancom_to_latex("{a} over {b}"), r"\frac{a}{b}")

    @patch("hmleq_converter.hmleqx", SimpleNamespace(to_latex=lambda script: (_ for _ in ()).throw(ValueError("unexpected token"))))
    def test_wraps_parser_value_error(self):
        with self.assertRaisesRegex(HmleqConversionError, "unexpected token"):
            convert_hancom_to_latex("bad formula")

    @patch("hmleq_converter.hmleqx", None)
    def test_reports_missing_python_package(self):
        with self.assertRaises(HmleqUnavailable):
            convert_hancom_to_latex("x over y")

    @patch("hmleq_converter.hmleqx", SimpleNamespace(to_latex=lambda script: "  "))
    def test_rejects_empty_conversion_result(self):
        with self.assertRaisesRegex(HmleqConversionError, "비어"):
            convert_hancom_to_latex("x over y")

    def test_rejects_empty_and_oversized_scripts(self):
        with self.assertRaises(HmleqConversionError):
            convert_hancom_to_latex("  ")
        with self.assertRaisesRegex(HmleqConversionError, "5000"):
            convert_hancom_to_latex("x" * 5001)

if __name__ == "__main__":
    unittest.main()
