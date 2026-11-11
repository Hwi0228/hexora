"""Question content formatting for HWPX exam-sheet generation."""

import json
import re
from html.parser import HTMLParser


class _RichTextLines(HTMLParser):
    BLOCK_TAGS = {"p", "div", "li", "blockquote", "pre", "h2", "h3"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []

    def _line_break(self):
        if self.parts and self.parts[-1] != "\n":
            self.parts.append("\n")

    def handle_starttag(self, tag, attrs):
        if tag == "br":
            self._line_break()
        elif tag in self.BLOCK_TAGS:
            self._line_break()
            if tag == "li":
                self.parts.append("• ")

    def handle_endtag(self, tag):
        if tag in self.BLOCK_TAGS:
            self._line_break()

    def handle_data(self, data):
        self.parts.append(data)

    def lines(self):
        self._line_break()
        value = "".join(self.parts).replace("\r\n", "\n").replace("\r", "\n")
        result = []
        for line in value.split("\n"):
            line = re.sub(r"[ \t\f\v]+", " ", line).strip()
            if line:
                result.append(line)
        return result


def rich_text_to_lines(value):
    if not value:
        return []
    parser = _RichTextLines()
    parser.feed(str(value))
    parser.close()
    return parser.lines()


def _choice_text(value):
    text = str(value or "").strip()
    return re.sub(r"^\s*(?:[①②③④⑤]|[0-9]{1,2}[.)])\s*", "", text)


def _question_paragraphs(questions, title, include_answers):
    paragraphs = []

    def add(text="", *, char_style="17", para_style="19", page_break=False):
        paragraphs.append({
            "text": str(text or ""),
            "char_style": str(char_style),
            "para_style": str(para_style),
            "page_break": bool(page_break),
        })

    def add_runs(runs, *, para_style="19"):
        paragraphs.append({
            "runs": runs,
            "char_style": "17",
            "para_style": str(para_style),
            "page_break": False,
        })

    # Branded exam-sheet masthead and student information fields.
    add("HEXORA", char_style="21", para_style="39")
    add("MATHEMATICS  ·  ASSESSMENT", char_style="24", para_style="58")
    add(title, char_style="15", para_style="39")
    add("(_____________)반 (______) ", char_style="24", para_style="58")
    add("이름: ____________________", char_style="24", para_style="58")
    add("")

    for number, question in enumerate(questions, start=1):
        add(f"QUESTION {number:02d}", char_style="45")
        if question.get("title"):
            add(str(question["title"]).strip(), char_style="23")

        passage_lines = rich_text_to_lines(question.get("passage"))
        if passage_lines:
            add("〈지문〉", char_style="23")
            for line in passage_lines:
                add(line)

        prompt_lines = rich_text_to_lines(question.get("prompt"))
        point_label = ""
        try:
            if question.get("points") is not None and int(question["points"]) > 0:
                point_label = f"  ({int(question['points'])}점)"
        except (TypeError, ValueError):
            pass

        first_line = prompt_lines.pop(0) if prompt_lines else ""
        add(f"{first_line}{point_label}", char_style="17")
        for line in prompt_lines:
            add(line)

        example_lines = rich_text_to_lines(question.get("examples"))
        if example_lines:
            add("〈보기〉", char_style="23")
            for line in example_lines:
                add(line)

        try:
            choices = question.get("choices") or []
            if isinstance(choices, str):
                choices = json.loads(choices)
            if not isinstance(choices, list):
                choices = []
        except (TypeError, ValueError, json.JSONDecodeError):
            choices = []

        choice_labels = "①②③④⑤"
        for index, choice in enumerate(choices):
            label = choice_labels[index] if index < len(choice_labels) else f"{index + 1}."
            lines = rich_text_to_lines(_choice_text(choice))
            for line_index, line in enumerate(lines):
                add(f"{label} {line}" if line_index == 0 else f"   {line}")

        add("")

    if include_answers:
        add(
            "ANSWER KEY  ·  TEACHER COPY",
            char_style="46",
            para_style="39",
            page_break=True,
        )
        add("정답 및 해설", char_style="15", para_style="39")
        for number, question in enumerate(questions, start=1):
            answer_lines = rich_text_to_lines(question.get("answer"))
            explanation_lines = rich_text_to_lines(question.get("explanation"))
            answer = " ".join(answer_lines) if answer_lines else "미기재"
            add_runs([
                {"text": f"{number:02d}", "char_style": "60"},
                {"text": f"  정답: {answer}", "char_style": "17"},
            ])
            if explanation_lines:
                add("해설:", char_style="23")
                for line in explanation_lines:
                    add(line)

    return paragraphs
