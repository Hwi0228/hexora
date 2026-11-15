import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app import app
from hwp_engine.groq_segmenter import GroqSegmentationError
from hwp_engine.models import BlockKind, DocumentBlock, DocumentIR, SourcePosition


class GroqHwpRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp_directory = tempfile.TemporaryDirectory()
        app.config.update(
            TESTING=True,
            DATABASE=str(Path(self.temp_directory.name) / "groq-hwp.sqlite3"),
            SECRET_KEY="groq-hwp-test-secret",
        )
        self.client = app.test_client()
        self.client.get("/signup")
        with self.client.session_transaction() as session:
            token = session["csrf_token"]
        response = self.client.post(
            "/signup",
            data={
                "_csrf_token": token,
                "email": "groq-hwp@example.test",
                "display_name": "Groq HWP Test",
                "password": "long-test-password",
                "password_confirm": "long-test-password",
            },
        )
        self.assertEqual(response.status_code, 302)

    def tearDown(self):
        self.temp_directory.cleanup()

    def csrf_token(self):
        self.client.get("/hwp")
        with self.client.session_transaction() as session:
            return session["csrf_token"]

    def test_manual_segmentation_review_is_available_without_groq_key(self):
        document = DocumentIR(
            "hwpx",
            (
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "1. 첫 문항"),
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=1), "문항 내용"),
            ),
        )
        with patch("hwp_routes.HwpCoreExtractor") as extractor:
            extractor.return_value.extract_bytes.return_value = document
            with patch(
                "hwp_routes.suggest_question_boundaries",
                return_value={
                    "provider": "manual",
                    "model": None,
                    "segments": [],
                    "answer_start_block": None,
                    "warning": "GROQ_API_KEY가 설정되지 않았습니다.",
                },
            ):
                response = self.client.post(
                    "/hwp",
                    data={
                        "_csrf_token": self.csrf_token(),
                        "action": "segment",
                        "document": (io.BytesIO(b"test document"), "sample.hwpx"),
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("문항 구역 검토".encode(), response.data)
        self.assertIn("GROQ_API_KEY가 설정되지 않았습니다.".encode(), response.data)
        self.assertIn(b'class="question-boundary" checked', response.data)
        extractor.return_value.extract_bytes.assert_called_once()

    def test_groq_failure_falls_back_to_manual_review(self):
        document = DocumentIR(
            "hwp",
            (DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "첫 문항"),),
        )
        with patch("hwp_routes.HwpCoreExtractor") as extractor:
            extractor.return_value.extract_bytes.return_value = document
            with patch(
                "hwp_routes.suggest_question_boundaries",
                side_effect=GroqSegmentationError("Groq API 인증에 실패했습니다."),
            ):
                response = self.client.post(
                    "/hwp",
                    data={
                        "_csrf_token": self.csrf_token(),
                        "action": "segment",
                        "document": (io.BytesIO(b"test document"), "sample.hwp"),
                    },
                    content_type="multipart/form-data",
                )

        self.assertEqual(response.status_code, 200)
        self.assertIn("수동 분할은 계속 사용할 수 있습니다.".encode(), response.data)
        self.assertIn(b'class="question-boundary" checked', response.data)


    def test_personal_api_key_is_used_for_groq_analysis(self):
        document = DocumentIR(
            "hwpx",
            (DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "1. 첫 문항"),),
        )
        with patch("hwp_routes.HwpCoreExtractor") as extractor:
            extractor.return_value.extract_bytes.return_value = document
            with patch("hwp_routes.get_user_groq_api_key", return_value="user-specific-key") as key_lookup:
                with patch(
                    "hwp_routes.suggest_question_boundaries",
                    return_value={
                        "provider": "groq",
                        "model": "test-model",
                        "segments": [{"number": "1", "start_block": 0, "confidence": 0.9, "note": ""}],
                        "answer_start_block": None,
                        "warning": "",
                    },
                ) as suggest:
                    response = self.client.post(
                        "/hwp",
                        data={
                            "_csrf_token": self.csrf_token(),
                            "action": "segment",
                            "document": (io.BytesIO(b"test document"), "sample.hwpx"),
                        },
                        content_type="multipart/form-data",
                    )

        self.assertEqual(response.status_code, 200)
        key_lookup.assert_called_once()
        self.assertEqual(suggest.call_args.kwargs["api_key"], "user-specific-key")


if __name__ == "__main__":
    unittest.main()
