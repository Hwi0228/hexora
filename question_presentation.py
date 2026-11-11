"""Shared presentation transforms for question records."""

import json

from hwp_equations import strip_choice_label
from rich_text import render_rich_html


def prepare_question_for_display(question, *, rich_fields=()):
    """Return a display-ready copy without mutating the database row."""
    result = dict(question)
    raw_choices = result.get("choices") or "[]"
    if isinstance(raw_choices, str):
        try:
            raw_choices = json.loads(raw_choices)
        except (TypeError, json.JSONDecodeError):
            raw_choices = []
    if not isinstance(raw_choices, list):
        raw_choices = []

    result["choices"] = [
        render_rich_html(strip_choice_label(str(choice or "")))
        for choice in raw_choices
    ]
    for field in rich_fields:
        result[field] = render_rich_html(result.get(field, ""))
    return result
