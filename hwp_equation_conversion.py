"""Hancom equation-script conversion with a local legacy fallback."""

from __future__ import annotations

import os
import re
from pathlib import Path

from hmleq_converter import HmleqUnavailable
from hwp_equations import normalize_katex_expression


GROUPED_COMMAND = re.compile(
    r"(?<!\w)(?:vec|dyad|acute|grave|dot|ddot|bar|hat|check|arch|tilde|BOX|"
    r"matrix|pmatrix|bmatrix|dmatrix|cases)(?=\s*\{)"
)
HANGUL = re.compile(r"[\uac00-\ud7a3]")


def equation_to_latex(script: str, *, legacy_converter, primary_converter) -> str:
    script = script.replace("`", "").strip()
    script = re.sub(r"(?<!\w)LEFT\s+LBRACE(?!\w)", "LEFT {", script)
    script = re.sub(r"(?<!\w)RIGHT\s+RBRACE(?!\w)", "RIGHT }", script)
    script = re.sub(r"(?<!\w)LBRACE(?!\w)", "{", script)
    script = re.sub(r"(?<!\w)RBRACE(?!\w)", "}", script)
    script = re.sub(r"(?<!\w)div(?!\w)", "÷", script)
    script = re.sub(r"(?<!\w)CASES(?!\w)", "cases", script)
    script = re.sub(r"(?<!\w)cdots(?!\w)", "CDOTS", script)
    script = re.sub(r"(?<!\w)EQALIGN(?!\w)", "eqalign", script)
    script = re.sub(r"(?<!\w)angle(?!\w)", "ANGLE", script)
    # HWP uses "it" to close a roman-style quoted identifier. Explicit braces
    # keep hmleqx's rm scope from swallowing the following relation/degree.
    script = re.sub(
        r'(?<!\w)rm\s+"([^"]*)"\s+it\b',
        lambda match: "{rm " + match.group(1) + "}",
        script,
    )
    script = re.sub(r"(?<!\w)triangle(?!\w)", "TRIANGLE", script)
    search_from = 0
    while True:
        match = GROUPED_COMMAND.search(script, search_from)
        if match is None:
            break
        argument_start = script.find("{", match.end())
        depth = 0
        argument_end = None
        for index in range(argument_start, len(script)):
            if script[index] == "{":
                depth += 1
            elif script[index] == "}":
                depth -= 1
                if depth == 0:
                    argument_end = index + 1
                    break
        if argument_end is None:
            raise ValueError("HWP 수식에서 그룹 연산자의 범위를 찾을 수 없습니다.")
        wrapped_command = "{" + script[match.start() : argument_end] + "}"
        script = (
            script[: match.start()]
            + wrapped_command
            + script[argument_end:]
        )
        search_from = match.start() + 4
    if os.environ.get("HMLEQ_USE_LEGACY") == "1":
        converted = legacy_converter(script).strip()
    else:
        try:
            converted = primary_converter(script)
        except HmleqUnavailable:
            # Local parsing remains available before Rust is installed. Render's
            # build marker makes a missing production binary a hard failure.
            if (
                os.environ.get("HMLEQ_REQUIRED") == "1"
                or Path(__file__).with_name(".render-require-hmleq").exists()
            ):
                raise
            converted = legacy_converter(script).strip()
    converted = re.sub(
        r'\brm\s+"([^"]*)"(?:\s+it\b)?',
        lambda match: (
            rf"\text{{{match.group(1)}}}"
            if HANGUL.search(match.group(1))
            else rf"\mathrm{{{match.group(1)}}}"
        ),
        converted,
    )
    # HWP formulas are embedded as inline KaTeX. Keep fractions compact
    # even though hmleqx emits display-sized fractions in standalone output.
    normalized = normalize_katex_expression(converted)
    return re.sub(r"\\dfrac\b", lambda _: r"\frac", normalized)
