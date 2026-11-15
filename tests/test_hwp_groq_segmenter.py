import json
import unittest
from unittest.mock import patch

from hwp_engine.groq_segmenter import (
    GroqSegmentationError,
    document_blocks_for_segmentation,
    suggest_question_boundaries,
    validate_segmentation,
)
from hwp_engine.models import BlockKind, DocumentBlock, DocumentIR, SourcePosition


class GroqSegmentationTests(unittest.TestCase):
    def setUp(self):
        self.document = DocumentIR(
            "hwpx",
            (
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=0), "1. 첫 번째 문제"),
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=1), "보기 ① 가 ② 나"),
                DocumentBlock(
                    BlockKind.FORMULA,
                    SourcePosition(paragraph=2),
                    "x over 2",
                    {"original_script": "x over 2"},
                ),
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=3), "정답 및 해설"),
                DocumentBlock(BlockKind.PARAGRAPH, SourcePosition(paragraph=4), "1번 정답은 ①"),
            ),
        )
        self.blocks = document_blocks_for_segmentation(self.document)

    def test_projection_keeps_formula_source_script(self):
        self.assertEqual(len(self.blocks), 5)
        self.assertEqual(self.blocks[2]["text"], "[수식 원문] x over 2")
        self.assertEqual(self.blocks[2]["source_index"], 2)

    def test_missing_api_key_returns_manual_mode_without_network(self):
        with patch.dict("os.environ", {"GROQ_API_KEY": ""}, clear=False):
            with patch("hwp_engine.groq_segmenter.urlopen") as urlopen:
                result = suggest_question_boundaries(self.blocks)
        self.assertEqual(result["provider"], "manual")
        self.assertEqual(result["segments"], [])
        urlopen.assert_not_called()

    def test_validates_sorted_question_starts_and_answer_start(self):
        result = validate_segmentation(
            {
                "segments": [
                    {"number": "1", "start_block": 0, "confidence": 0.9},
                    {"number": "2", "start_block": 2, "confidence": 0.7},
                ],
                "answer_start_block": 4,
            },
            len(self.blocks),
        )
        self.assertEqual(result["segments"][0]["number"], "1")
        self.assertEqual(result["segments"][1]["start_block"], 2)
        self.assertEqual(result["answer_start_block"], 4)

    def test_rejects_duplicate_or_out_of_order_and_out_of_range_starts(self):
        for payload in (
            {"segments": [
                {"start_block": 0},
                {"start_block": 0},
            ]},
            {"segments": [
                {"start_block": 2},
                {"start_block": 1},
            ]},
            {"segments": [{"start_block": 99}]},
        ):
            with self.subTest(payload=payload):
                with self.assertRaises(GroqSegmentationError):
                    validate_segmentation(payload, len(self.blocks))

    def test_groq_response_is_parsed_and_model_output_is_validated(self):
        model_payload = {
            "segments": [
                {"number": "1", "start_block": 0, "confidence": 0.93, "note": "번호 표식"}
            ],
            "answer_start_block": 3,
        }
        response_body = {
            "choices": [{"message": {"content": json.dumps(model_payload)}}]
        }

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(response_body).encode("utf-8")

        with patch("hwp_engine.groq_segmenter.urlopen", return_value=FakeResponse()) as urlopen:
            result = suggest_question_boundaries(self.blocks, api_key="test-key", model="test-model")

        self.assertEqual(result["provider"], "groq")
        self.assertEqual(result["model"], "test-model")
        self.assertEqual(result["segments"][0]["start_block"], 0)
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer test-key")
        self.assertNotIn("test-key", request.data.decode("utf-8"))


if __name__ == "__main__":
    unittest.main()
