import subprocess
import unittest
from unittest.mock import patch

from hmleq_converter import (
    HmleqConversionError,
    HmleqUnavailable,
    _executable,
    convert_hancom_to_latex,
)


class HmleqConverterTests(unittest.TestCase):
    @patch("hmleq_converter._executable", return_value="/usr/bin/hmleq")
    @patch("hmleq_converter.subprocess.run")
    def test_sends_script_on_stdin_and_returns_latex(self, run, _executable):
        run.return_value = subprocess.CompletedProcess(
            args=["hmleq"], returncode=0, stdout=r"\frac{a}{b}" + "\n", stderr=""
        )

        result = convert_hancom_to_latex("{a} over {b}")

        self.assertEqual(result, r"\frac{a}{b}")
        self.assertEqual(run.call_args.args[0], ["/usr/bin/hmleq"])
        self.assertEqual(run.call_args.kwargs["input"], "{a} over {b}")
        self.assertEqual(run.call_args.kwargs["timeout"], 5)
        self.assertNotIn("shell", run.call_args.kwargs)

    @patch("hmleq_converter._executable", return_value="/usr/bin/hmleq")
    @patch("hmleq_converter.subprocess.run")
    def test_reports_parser_errors(self, run, _executable):
        run.return_value = subprocess.CompletedProcess(
            args=["hmleq"], returncode=1, stdout="", stderr="unexpected token"
        )

        with self.assertRaisesRegex(HmleqConversionError, "unexpected token"):
            convert_hancom_to_latex("bad formula")

    @patch("hmleq_converter._executable", return_value=None)
    def test_reports_missing_binary(self, _executable):
        with self.assertRaises(HmleqUnavailable):
            convert_hancom_to_latex("x over y")

    @patch("hmleq_converter._executable", return_value="/usr/bin/hmleq")
    @patch("hmleq_converter.subprocess.run", side_effect=subprocess.TimeoutExpired("hmleq", 5))
    def test_times_out_boundedly(self, _run, _executable):
        with self.assertRaisesRegex(HmleqConversionError, "초과"):
            convert_hancom_to_latex("x over y")

    def test_rejects_empty_and_oversized_scripts(self):
        with self.assertRaises(HmleqConversionError):
            convert_hancom_to_latex("  ")
        with self.assertRaisesRegex(HmleqConversionError, "4096"):
            convert_hancom_to_latex("x" * 4097)

    @unittest.skipUnless(_executable(), "hmleq CLI is installed by build.sh")
    def test_real_hmleq_converts_fraction_radical_and_matrix(self):
        self.assertEqual(convert_hancom_to_latex("1 over 2"), r"\frac{1}{2}")
        self.assertIn(r"\sqrt", convert_hancom_to_latex("sqrt {x}"))
        matrix = convert_hancom_to_latex("pmatrix { a & b # c & d }")
        self.assertIn(r"\begin{pmatrix}", matrix)
        self.assertIn(r"\end{pmatrix}", matrix)


if __name__ == "__main__":
    unittest.main()
