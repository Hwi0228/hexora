"""Convert a supported LaTeX subset to Hancom equation-script syntax.

Unsupported commands fail explicitly so an export never creates a broken native
formula object or silently claims that raw TeX is a Hancom equation.
"""
from __future__ import annotations

import re


class LatexEquationConversionError(ValueError):
    """Raised when a LaTeX expression cannot be represented safely."""


_SYMBOLS = {
    "alpha": "alpha", "beta": "beta", "gamma": "gamma", "delta": "delta",
    "epsilon": "epsilon", "varepsilon": "varepsilon", "zeta": "zeta",
    "eta": "eta", "theta": "theta", "vartheta": "vartheta", "iota": "iota",
    "kappa": "kappa", "lambda": "lambda", "mu": "mu", "nu": "nu",
    "xi": "xi", "pi": "pi", "varpi": "varpi", "rho": "rho",
    "sigma": "sigma", "tau": "tau", "upsilon": "upsilon", "phi": "phi",
    "varphi": "varphi", "chi": "chi", "psi": "psi", "omega": "omega",
    "Gamma": "GAMMA", "Delta": "DELTA", "Theta": "THETA", "Lambda": "LAMBDA",
    "Xi": "XI", "Pi": "PI", "Sigma": "SIGMA", "Phi": "PHI",
    "Psi": "PSI", "Omega": "OMEGA",
    "cdot": "cdot", "times": "times", "div": "div", "pm": "+-", "mp": "-+",
    "le": "<=", "leq": "<=", "ge": ">=", "geq": ">=", "neq": "!=", "ne": "!=",
    "approx": "approx", "equiv": "equiv", "sim": "sim", "propto": "propto",
    "in": "in", "notin": "notin", "subset": "subset", "subseteq": "subseteq",
    "supset": "supset", "supseteq": "supseteq", "cup": "cup", "cap": "cap",
    "emptyset": "emptyset", "infty": "infinity", "forall": "forall",
    "exists": "exists", "to": "->", "rightarrow": "->", "leftarrow": "<-",
    "leftrightarrow": "<->", "mapsto": "mapsto", "perp": "perp",
    "parallel": "parallel", "angle": "angle", "therefore": "therefore",
    "because": "because", "ldots": "...", "cdots": "...", "vdots": "vdots",
    "sum": "sum", "prod": "prod", "int": "int", "iint": "iint",
    "oint": "oint", "lim": "lim", "sin": "sin", "cos": "cos", "tan": "tan",
    "cot": "cot", "sec": "sec", "csc": "csc", "log": "log", "ln": "ln",
    "exp": "exp", "max": "max", "min": "min", "det": "det", "gcd": "gcd",
    "lbrace": "lbrace", "rbrace": "rbrace", "langle": "langle",
    "rangle": "rangle", "vert": "|", "Vert": "||",
}
_IGNORED = {
    "left", "right", "displaystyle", "textstyle", "scriptstyle",
    "scriptscriptstyle", "limits", "nolimits", "big", "Big", "bigg", "Bigg",
    "quad", "qquad", "enspace", "thinspace",
}
_GROUP_COMMANDS = {
    "text", "textrm", "textnormal", "mathrm", "operatorname",
    "mathbf", "mathbb", "mathcal", "mathsf", "mathtt",
}
_MATRIX_ENVIRONMENTS = {
    "matrix", "pmatrix", "bmatrix", "Bmatrix", "vmatrix", "Vmatrix",
    "cases", "aligned", "array",
}


def _skip_spaces(source: str, index: int) -> int:
    while index < len(source) and source[index].isspace():
        index += 1
    return index


def _read_group(source: str, index: int) -> tuple[str, int]:
    index = _skip_spaces(source, index)
    if index >= len(source) or source[index] != "{":
        raise LatexEquationConversionError("LaTeX 명령의 중괄호 인수가 필요합니다.")
    depth = 1
    cursor = index + 1
    parts = []
    while cursor < len(source):
        char = source[cursor]
        if char == "\\" and cursor + 1 < len(source) and source[cursor + 1] in "{}":
            parts.extend((char, source[cursor + 1]))
            cursor += 2
            continue
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return "".join(parts), cursor + 1
        parts.append(char)
        cursor += 1
    raise LatexEquationConversionError("닫히지 않은 LaTeX 중괄호가 있습니다.")


def _read_optional(source: str, index: int) -> tuple[str | None, int]:
    index = _skip_spaces(source, index)
    if index >= len(source) or source[index] != "[":
        return None, index
    depth = 1
    cursor = index + 1
    parts = []
    while cursor < len(source):
        char = source[cursor]
        if char == "[":
            depth += 1
        elif char == "]":
            depth -= 1
            if depth == 0:
                return "".join(parts), cursor + 1
        parts.append(char)
        cursor += 1
    raise LatexEquationConversionError("닫히지 않은 LaTeX 대괄호가 있습니다.")


def _convert_sequence(source: str) -> str:
    output = []
    index = 0
    while index < len(source):
        char = source[index]
        if char == "\\":
            if source.startswith("\\\\", index):
                output.append(" # ")
                index += 2
                continue
            index += 1
            if index >= len(source):
                raise LatexEquationConversionError("끝에 단독 역슬래시가 있습니다.")
            if source[index].isalpha():
                match = re.match(r"[A-Za-z]+", source[index:])
                command = match.group(0)
                index += len(command)
            else:
                command = source[index]
                index += 1

            if command in {"frac", "dfrac", "tfrac", "cfrac"}:
                numerator, index = _read_group(source, index)
                denominator, index = _read_group(source, index)
                output.append(f"{{{_convert_sequence(numerator)}}} over {{{_convert_sequence(denominator)}}}")
            elif command == "sqrt":
                degree, index = _read_optional(source, index)
                radicand, index = _read_group(source, index)
                if degree is None:
                    output.append(f"sqrt {{{_convert_sequence(radicand)}}}")
                else:
                    output.append(
                        f"sqrt {{{_convert_sequence(degree)}}} of {{{_convert_sequence(radicand)}}}"
                    )
            elif command == "binom":
                upper, index = _read_group(source, index)
                lower, index = _read_group(source, index)
                output.append(f"{{{_convert_sequence(upper)}}} choose {{{_convert_sequence(lower)}}}")
            elif command == "begin":
                environment, index = _read_group(source, index)
                if environment not in _MATRIX_ENVIRONMENTS:
                    raise LatexEquationConversionError(
                        f"지원하지 않는 수식 환경: {environment}"
                    )
                if environment == "array":
                    _column_spec, index = _read_group(source, index)
                end_marker = f"\\end{{{environment}}}"
                end_index = source.find(end_marker, index)
                if end_index < 0:
                    raise LatexEquationConversionError(
                        f"닫히지 않은 수식 환경: {environment}"
                    )
                body = source[index:end_index]
                body = re.sub(r"\\\\\s*", " # ", body)
                matrix_name = "matrix" if environment in {"aligned", "array"} else environment
                output.append(f"{matrix_name} {{ {_convert_sequence(body)} }}")
                index = end_index + len(end_marker)
            elif command in _GROUP_COMMANDS:
                argument, index = _read_group(source, index)
                output.append(f"rm {{{_convert_sequence(argument)}}}")
            elif command in {"overline", "underline", "vec", "hat", "bar", "dot", "ddot"}:
                argument, index = _read_group(source, index)
                output.append(f"{command} {{{_convert_sequence(argument)}}}")
            elif command in _IGNORED:
                if command in {"quad", "qquad", "enspace", "thinspace"}:
                    output.append(" ")
            elif command in _SYMBOLS:
                output.append(_SYMBOLS[command])
            elif command == " ":
                output.append(" ")
            elif command == "%":
                output.append("%")
            elif command == "_":
                output.append("_")
            elif command == "{":
                output.append("lbrace")
            elif command == "}":
                output.append("rbrace")
            elif command == "&":
                output.append("&")
            elif command in {"over", "atop", "choose"}:
                output.append(command)
            else:
                raise LatexEquationConversionError(
                    f"지원하지 않는 LaTeX 명령어: \\{command}"
                )
        elif char in {"^", "_"}:
            operator = char
            index += 1
            index = _skip_spaces(source, index)
            if index < len(source) and source[index] == "{":
                argument, index = _read_group(source, index)
                output.append(f" {operator} {{{_convert_sequence(argument)}}}")
            elif index < len(source):
                output.append(f" {operator} {source[index]}")
                index += 1
            else:
                raise LatexEquationConversionError("지수 또는 아래첨자 값이 비어 있습니다.")
        elif char == "&":
            output.append(" & ")
            index += 1
        else:
            output.append(char)
            index += 1

    return re.sub(r"\s+", " ", "".join(output)).strip()


def convert_latex_to_hancom(latex: str) -> str:
    if not isinstance(latex, str) or not latex.strip():
        raise LatexEquationConversionError("변환할 LaTeX 수식이 비어 있습니다.")
    if len(latex) > 5000:
        raise LatexEquationConversionError("수식은 5000자 이내로 입력해 주세요.")
    converted = _convert_sequence(latex.strip())
    if not converted:
        raise LatexEquationConversionError("Hancom 수식 변환 결과가 비어 있습니다.")
    return converted
