from pathlib import Path
import json
import unittest
import zipfile
from io import BytesIO

from werkzeug.datastructures import MultiDict

from hwp_routes import _validated_import
from parse_rhwp import _validate_hwpx_archive
from hwp_import_validation import _get_section_xml, MAX_SECTION_XML_SIZE


class HwpImportValidationTests(unittest.TestCase):
    def _hwpx(self, files):
        output = BytesIO()
        with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            for name, content in files.items():
                archive.writestr(name, content)
        return output.getvalue()

    def test_valid_hwpx_zip_is_accepted(self):
        content = self._hwpx({
            "mimetype": "application/hwp+zip",
            "Contents/section0.xml": "<section><p>문항</p></section>",
        })
        _validate_hwpx_archive(content)

    def test_non_zip_hwpx_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "ZIP"):
            _validate_hwpx_archive(b"not a zip")

    def test_zip_path_traversal_is_rejected(self):
        content = self._hwpx({
            "../outside.xml": "<root/>",
            "Contents/section0.xml": "<root/>",
        })
        with self.assertRaisesRegex(ValueError, "파일 경로"):
            _validate_hwpx_archive(content)

    def test_unsafe_xml_entities_are_rejected(self):
        content = self._hwpx({
            "Contents/section0.xml": (
                '<!DOCTYPE root [<!ENTITY x "expanded">]><root>&x;</root>'
            ),
        })
        with self.assertRaises(ValueError):
            _validate_hwpx_archive(content)

    def test_single_xml_upload_limit_is_16_mib(self):
        self.assertEqual(_get_section_xml("section0.xml", b"<root/>"), b"<root/>")
        with self.assertRaisesRegex(ValueError, "16MB"):
            _get_section_xml("section0.xml", b"x" * (MAX_SECTION_XML_SIZE + 1))

    def test_import_sanitizes_and_preserves_math_embed_metadata(self):
        math = '<span class="ql-math-inline" data-latex="x^2" data-input-format="hancom" data-input-source="x ^ 2" data-math-object="inline"></span>'
        form = MultiDict([
            ("questions_json", json.dumps({"questions": [{
                "number": 1, "question": "다음 식 " + math, "choices": [],
                "answer": math, "explanation": "",
            }]}, ensure_ascii=False)),
            ("subject", "수학"), ("grade", "고1"), ("unit", "테스트 단원"),
            ("source", "업로드 문서"), ("license", "ORIGINAL"),
            ("source_type", "기타"), ("selected_questions", "0"),
        ])
        questions, selection, errors, error = _validated_import(form)
        self.assertIsNone(error)
        self.assertEqual(errors, [])
        self.assertIn('class="ql-math-inline"', questions[0]["question"])
        self.assertIn('data-latex="x^2"', questions[0]["answer"])
        self.assertIn('data-input-format="hancom"', questions[0]["answer"])

    def test_import_review_does_not_render_processing_logs_in_the_user_interface(self):
        template = (
            Path(__file__).resolve().parents[1]
            / "static" / "templates" / "hwp_parser.html"
        ).read_text(encoding="utf-8")
        self.assertNotIn("processing-log", template)
        self.assertNotIn("process-feedback", template)
        script = (
            Path(__file__).resolve().parents[1]
            / "static" / "scripts" / "hwp-import-review.js"
        ).read_text(encoding="utf-8")
        self.assertIn('list.addEventListener("paste"', script)
        self.assertIn('list.addEventListener("drop"', script)
        self.assertIn("const cardState = new WeakMap()", script)
        self.assertIn("schedulePayloadSync()", script)
        self.assertIn("question.original && typeof question.original === \"object\"", script)
        self.assertIn("range.cloneContents()", script)
        self.assertIn('captureCard(editor.closest("[data-import-question]"))', script)
        self.assertIn('form.addEventListener("hexora:sync-import-payload"', script)
        upload_script = (
            Path(__file__).resolve().parents[1]
            / "static" / "scripts" / "hwp-import.js"
        ).read_text(encoding="utf-8")
        self.assertIn('dispatchEvent(new Event("hexora:sync-import-payload"))', upload_script)

    def test_formula_comparison_data_survives_validation_and_retry(self):
        payload = {
            "questions": [{
                "number": 1,
                "source_number": "1",
                "question": "수식이 포함된 문제",
                "choices": [],
                "answer": "",
                "explanation": "",
                "math_objects": [{
                    "original_script": "a over b",
                    "latex": r"\\dfrac{a}{b}",
                    "conversion_error": None,
                    "source_position": {"section": 0, "paragraph": 1},
                }],
            }],
        }
        form = MultiDict([
            ("questions_json", json.dumps(payload, ensure_ascii=False)),
            ("subject", "수학"), ("grade", "고1"), ("unit", "테스트 단원"),
            ("source", "업로드 문서"), ("license", "ORIGINAL"),
            ("source_type", "기타"), ("selected_questions", "0"),
        ])
        questions, selection, errors, error = _validated_import(form)
        self.assertIsNone(error)
        self.assertEqual(errors, [])
        self.assertEqual(questions[0]["math_objects"][0]["original_script"], "a over b")
        self.assertEqual(questions[0]["math_objects"][0]["latex"], r"\\dfrac{a}{b}")

    def test_multiple_questions_can_be_corrected_and_selected_together(self):
        payload = {
            "questions": [
                {
                    "number": 1, "source_number": "1", "question": "수정 문제 1",
                    "choices": ["수정 보기 1"], "answer": "①", "explanation": "수정 해설 1",
                    "original": {
                        "source_number": "1", "question": "원본 문제 1",
                        "choices": ["원본 보기 1"], "answer": "②", "explanation": "원본 해설 1",
                    },
                    "corrected_fields": ["question", "choices", "answer", "explanation"],
                },
                {
                    "number": 2, "source_number": "2-b", "question": "수정 문제 2",
                    "choices": [], "answer": "42", "explanation": "",
                    "original": {
                        "source_number": "2", "question": "원본 문제 2",
                        "choices": [], "answer": "", "explanation": "",
                    },
                    "corrected_fields": ["source_number", "question", "answer", "question_boundary"],
                },
            ],
        }
        form = MultiDict([
            ("questions_json", json.dumps(payload, ensure_ascii=False)),
            ("subject", "수학"), ("grade", "고1"), ("unit", "테스트 단원"),
            ("source", "업로드 문서"), ("license", "ORIGINAL"),
            ("source_type", "기타"), ("selected_questions", "0"),
            ("selected_questions", "1"),
        ])
        questions, selection, errors, error = _validated_import(form)
        self.assertIsNone(error)
        self.assertEqual(errors, [])
        self.assertEqual(selection[1], [0, 1])
        self.assertEqual(questions[0]["original"]["question"], "원본 문제 1")
        self.assertEqual(questions[1]["original"]["question"], "원본 문제 2")
        self.assertIn("question_boundary", questions[1]["corrected_fields"])

    def test_manual_corrections_keep_original_values_and_source_number(self):
        form = MultiDict([
            ("questions_json", json.dumps({"questions": [{
                "number": 1,
                "source_number": "4-b",
                "question": "수정한 문제",
                "choices": ["수정 선택지"],
                "answer": "②",
                "explanation": "수정 해설",
                "original": {
                    "source_number": "4",
                    "question": "원본 문제",
                    "choices": ["원본 선택지"],
                    "answer": "①",
                    "explanation": "원본 해설",
                },
                "corrected_fields": ["question", "choices", "answer", "question_boundary"],
            }]}, ensure_ascii=False)),
            ("subject", "수학"), ("grade", "고1"), ("unit", "테스트 단원"),
            ("source", "업로드 문서"), ("license", "ORIGINAL"),
            ("source_type", "기타"), ("selected_questions", "0"),
        ])
        questions, selection, errors, error = _validated_import(form)
        self.assertIsNone(error)
        self.assertEqual(errors, [])
        self.assertEqual(questions[0]["source_number"], "4-b")
        self.assertEqual(questions[0]["original"]["question"], "원본 문제")
        self.assertIn("question_boundary", questions[0]["corrected_fields"])

    def test_structural_warnings_require_explicit_review_acknowledgement(self):
        payload = {
            "questions": [{
                "number": 1, "source_number": "1", "question": "문제",
                "choices": [], "answer": "", "explanation": "",
            }],
            "validation": {
                "valid": True,
                "issues": [{
                    "code": "LOW_CONFIDENCE",
                    "message": "문항 경계를 확인해 주세요.",
                    "severity": "warning",
                }],
            },
        }
        base = [
            ("questions_json", json.dumps(payload, ensure_ascii=False)),
            ("subject", "수학"), ("grade", "고1"), ("unit", "테스트 단원"),
            ("source", "업로드 문서"), ("license", "ORIGINAL"),
            ("source_type", "기타"), ("selected_questions", "0"),
        ]
        questions, selection, errors, error = _validated_import(MultiDict(base))
        self.assertIsNone(questions)
        self.assertIn("경고", " ".join(errors))
        acknowledged = MultiDict(base + [("warnings_acknowledged", "1")])
        questions, selection, errors, error = _validated_import(acknowledged)
        self.assertIsNone(error)
        self.assertEqual(errors, [])

    def test_structural_validation_failure_is_rejected_before_persistence(self):
        form = MultiDict([
            ("questions_json", json.dumps({
                "questions": [{
                    "number": 1,
                    "source_number": "1",
                    "question": "다음 중 옳은 것은?",
                    "choices": ["가", "나"],
                    "answer": "⑤",
                    "explanation": "",
                }],
                "validation": {
                    "valid": False,
                    "issues": [{
                        "code": "ANSWER_OUT_OF_RANGE",
                        "message": "선택지에 없는 정답 표식입니다.",
                        "question_number": "1",
                        "severity": "error",
                    }],
                },
            }, ensure_ascii=False)),
        ])

        questions, selection, errors, error = _validated_import(form)

        self.assertIsNone(questions)
        self.assertIsNone(selection)
        self.assertIsNone(error)
        self.assertIn("선택지에 없는 정답 표식입니다.", errors)

    def test_document_without_answer_or_explanation_can_be_imported(self):
        form = MultiDict([
            ("questions_json", json.dumps({
                "questions": [{
                    "number": 1,
                    "question": "지역의 자연환경 특성을 파악하는 문제",
                    "choices": ["교통", "기후"],
                    "answer": "",
                    "explanation": "",
                }]
            }, ensure_ascii=False)),
            ("subject", "수학"),
            ("grade", "고1"),
            ("unit", "테스트 단원"),
            ("source", "업로드 문서"),
            ("license", "ORIGINAL"),
            ("source_type", "기타"),
            ("selected_questions", "0"),
        ])

        questions, selection, errors, error = _validated_import(form)

        self.assertIsNone(error)
        self.assertEqual(errors, [])
        self.assertEqual(questions[0]["answer"], "")
        self.assertEqual(questions[0]["explanation"], "")
        self.assertEqual(selection[1], [0])
