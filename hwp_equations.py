"""Hancom equation markup normalization and choice-label helpers."""

import re
from functools import lru_cache


CHOICE_LABELS = "①②③④⑤"
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def _group_end(expression: str, open_index: int) -> int | None:
    depth = 0
    for index in range(open_index, len(expression)):
        if expression[index] not in "{}":
            continue
        backslashes = 0
        previous = index - 1
        while previous >= 0 and expression[previous] == "\\":
            backslashes += 1
            previous -= 1
        if backslashes % 2:
            continue
        if expression[index] == "{":
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return index
    return None


def _replace_group_environment(
    expression: str, command: str, environment: str
) -> str:
    pattern = re.compile(rf"(?<!\w)(?:\\{command}|{command})\s*\{{")
    search_from = 0
    while match := pattern.search(expression, search_from):
        open_index = expression.find("{", match.start(), match.end())
        close_index = _group_end(expression, open_index)
        if close_index is None:
            search_from = match.end()
            continue
        body = expression[open_index + 1 : close_index].replace("#", r"\\")
        body = re.sub(r"\s*\\\\\s*", r" \\\\ ", body.strip())
        replacement = rf"\begin{{{environment}}} {body} \end{{{environment}}}"
        expression = expression[: match.start()] + replacement + expression[close_index + 1 :]
        search_from = match.start() + len(replacement)
    return expression


def normalize_katex_expression(expression: str) -> str:
    expression = _replace_group_environment(expression, "eqalign", "aligned")
    expression = _replace_group_environment(expression, "CASES", "cases")
    expression = re.sub(r"(?<!\w)LEFT\s+LBRACE(?!\w)", r"\\left \\{", expression)
    expression = re.sub(r"(?<!\w)RIGHT\s+RBRACE(?!\w)", r"\\right \\}", expression)
    expression = re.sub(r"(?<!\w)LBRACE(?!\w)", r"\\{", expression)
    expression = re.sub(r"(?<!\w)RBRACE(?!\w)", r"\\}", expression)
    expression = re.sub(r"(?<!\w)LEFT(?!\w)", r"\\left", expression)
    expression = re.sub(r"(?<!\w)RIGHT(?!\w)", r"\\right", expression)
    for token, command in (
        ("div", r"\div"),
        ("times", r"\times"),
        ("sqrt", r"\sqrt"),
        ("cdots", r"\cdots"),
        ("triangle", r"\triangle"),
    ):
        expression = re.sub(
            rf"(?<![\w\\]){token}(?!\w)", lambda _: command, expression
        )
    expression = expression.replace("#", " ")
    expression = re.sub(
        r"\\mathrm\{([^{}]*)\}",
        lambda match: (
            rf"\text{{{match.group(1)}}}"
            if HANGUL.search(match.group(1))
            else match.group(0)
        ),
        expression,
    )
    return expression


@lru_cache(maxsize=4096)


def normalize_katex_markup(text: str) -> str:
    delimiters = re.compile(r"\$\$.*?\$\$|\$[^$]*\$|\\\(.*?\\\)|\\\[.*?\\\]", re.DOTALL)

    def normalize(match: re.Match[str]) -> str:
        value = match.group(0)
        if value.startswith("$$"):
            left, right = "$$", "$$"
        elif value.startswith("$"):
            left, right = "$", "$"
        elif value.startswith(r"\("):
            left, right = r"\(", r"\)"
        else:
            left, right = r"\[", r"\]"
        return left + normalize_katex_expression(value[len(left) : -len(right)]) + right

    return delimiters.sub(normalize, text)


def strip_choice_label(choice: str) -> str:
    return re.sub(f"^[{CHOICE_LABELS}]\\s*", "", choice, count=1).strip()
