import unittest

from question_history_routes import _plain_revision_text, _render_diff_side


class QuestionRevisionDiffTests(unittest.TestCase):
    def test_markup_only_changes_are_normalized_away(self):
        before = _plain_revision_text("<p>다음 <strong>함수</strong>를 구하시오.</p>")
        after = _plain_revision_text("<p>다음 함수<span>를</span> 구하시오.</p>")
        self.assertEqual(before, after)

    def test_math_embeds_preserve_their_latex_payload(self):
        value = _plain_revision_text(
            '<p>식 <span class="ql-math-inline" data-latex="\\\\frac{1}{2}"></span></p>'
        )
        self.assertIn(r"$\\frac{1}{2}$", value)

    def test_changed_text_is_highlighted_on_the_correct_side(self):
        before = _render_diff_side("원래 문항", "수정 문항", "before")
        after = _render_diff_side("원래 문항", "수정 문항", "after")
        self.assertIn('<del class="diff-removed">원래</del>', before)
        self.assertIn('<ins class="diff-added">수정</ins>', after)


if __name__ == "__main__":
    unittest.main()
