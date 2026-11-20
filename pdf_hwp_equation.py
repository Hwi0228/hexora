"""Clean-room HyhwpEQ private-use glyph decoding for text-based PDFs.

The mapping records the public character-code conventions used by Hangul's
HyhwpEQ equation font. Decoding is deliberately font-scoped: identical PUA
code points in unrelated fonts are left untouched.

Structural operators are emitted as TeX primitives (\over, \sqrt, \vec).
The surrounding PDF layout is not sufficient in every document to infer
fraction/radical grouping, so callers must preserve geometry for later review.
"""
from __future__ import annotations

from typing import Final


# HyhwpEQ maps Latin capitals and lowercase letters into separate PUA ranges.
_LATIN_CAPITALS: Final = {
    chr(0xE000 + index): chr(ord("A") + index) for index in range(26)
}
_LATIN_LOWERCASE: Final = {
    chr(0xE0E5 + index): chr(ord("a") + index) for index in range(26)
}
_DIGITS: Final = {
    chr(0xE034 + index): str(index + 1) for index in range(9)
} | {chr(0xE03D): "0"}

_SYMBOLS: Final = {
    0xE03E: "!",
    0xE03F: "@",
    0xE041: "$",
    0xE042: r"\%",
    0xE043: r"\ast",
    0xE044: "(",
    0xE045: ")",
    0xE046: "-",
    0xE047: "=",
    0xE048: "+",
    0xE049: "[",
    0xE04A: "]",
    0xE04B: r"\{",
    0xE04C: r"\}",
    0xE04D: r"\vert",
    0xE04F: ":",
    0xE052: ",",
    0xE053: ".",
    0xE054: "/",
    0xE055: "<",
    0xE056: ">",
    0xE057: "?",
    0xE05C: r"\sqrt",
    0xE06D: r"\over",
    0xE06E: r"\vec",
    0xE0BB: r"\ell",
    0xE0C8: r"^{\circ}",
}

# The PUA assignments follow the equation-font code ranges, not the Unicode
# positions of Greek letters. Gaps in the Greek alphabet are retained.
_GREEK_RANGES: Final = (
    (0x0391, 0x03A1, 0xE085),  # Α..Ρ
    (0x03A3, 0x03A9, 0xE096),  # Σ..Ω
    (0x03B1, 0x03C1, 0xE09D),  # α..ρ
    (0x03C3, 0x03C9, 0xE0AE),  # σ..ω
)
_GREEK: Final = {
    chr(code): chr(unicode_start + code - pua_start)
    for unicode_start, unicode_end, pua_start in _GREEK_RANGES
    for code in range(pua_start, pua_start + unicode_end - unicode_start + 1)
}
# Variant and named Greek symbols whose code points are not in a contiguous run.
_GREEK.update({
    chr(0xE0A1): "ϵ",
    chr(0xE0A2): "ζ",
    chr(0xE0A3): "η",
    chr(0xE0A4): "θ",
    chr(0xE0A5): "ι",
    chr(0xE0A6): "κ",
    chr(0xE0A7): "λ",
    chr(0xE0A8): "μ",
    chr(0xE0A9): "ν",
    chr(0xE0AA): "ξ",
    chr(0xE0AB): "ο",
    chr(0xE0AC): r"\pi",
    chr(0xE0AD): "ρ",
    chr(0xE0B0): "υ",
    chr(0xE0B1): "φ",
    chr(0xE0B2): "χ",
    chr(0xE0B3): "ψ",
    chr(0xE0B4): "ω",
    chr(0xE10E): "ε",
})

HYHWPEQ_GLYPHS: Final = (
    _LATIN_CAPITALS | _LATIN_LOWERCASE | _DIGITS | _GREEK
    | {chr(code): value for code, value in _SYMBOLS.items()}
)


def is_hyhwp_eq_font(font_name: str) -> bool:
    """Recognize full and subset-prefixed HyhwpEQ PDF font names."""
    normalized = (font_name or "").replace(" ", "").casefold()
    return "hyhwpeq" in normalized


def decode_hyhwp_equation_text(text: str, font_name: str) -> str:
    """Decode known HyhwpEQ PUA characters; leave other fonts untouched."""
    if not is_hyhwp_eq_font(font_name):
        return text
    return "".join(HYHWPEQ_GLYPHS.get(char, char) for char in text)


def extract_pdf_page_lines(page) -> list[str]:
    """Extract page lines in visual order while decoding HyhwpEQ spans.

    PyMuPDF's sorted text mode can still flatten multi-column layouts. This
    helper keeps line boundaries and sorts spans within each visual line.
    """
    blocks = page.get_text("dict", sort=True).get("blocks", ())
    positioned_lines: list[tuple[float, float, str]] = []
    for block in blocks:
        if "lines" not in block:
            continue
        for line in block["lines"]:
            spans = sorted(
                line.get("spans", ()),
                key=lambda span: (float(span.get("bbox", (0, 0, 0, 0))[0])),
            )
            pieces = [
                decode_hyhwp_equation_text(
                    str(span.get("text", "")), str(span.get("font", ""))
                )
                for span in spans
            ]
            value = "".join(pieces).strip()
            if value:
                bbox = line.get("bbox", (0, 0, 0, 0))
                positioned_lines.append((float(bbox[1]), float(bbox[0]), value))
    positioned_lines.sort(key=lambda item: (round(item[0], 1), item[1]))
    return [value for _, _, value in positioned_lines]
