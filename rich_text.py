import html
import re
from html.parser import HTMLParser

from parse_hwp import normalize_katex_markup


class _RichTextSanitizer(HTMLParser):
    ALLOWED_TAGS = {
        "p", "br", "strong", "b", "em", "i", "u", "s", "ul", "ol",
        "li", "blockquote", "pre", "code", "h2", "h3", "hr", "span", "div",
    }
    VOID_TAGS = {"br", "hr"}
    LITERAL_TAGS = {"script", "style", "iframe", "object", "embed", "svg"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.stack = []
        self.math_skip_depth = None
        self.math_close_tag = None

    def handle_starttag(self, tag, attrs):
        if self.math_skip_depth is not None:
            self.math_skip_depth += 1
            return
        if self.stack and self.stack[-1].startswith("__literal__:"):
            self.parts.append(html.escape(self.get_starttag_text() or f"<{tag}>"))
            return
        if tag in self.LITERAL_TAGS:
            self.parts.append(html.escape(self.get_starttag_text() or f"<{tag}>"))
            self.stack.append(f"__literal__:{tag}")
            return
        if tag not in self.ALLOWED_TAGS:
            return

        attr_map = dict(attrs)
        classes = set((attr_map.get("class") or "").split())
        math_type = attr_map.get("data-type")
        if tag == "span" and "ql-math-inline" in classes:
            math_type = "inline-math"
        elif tag in {"span", "div"} and "ql-math-block" in classes:
            math_type = "block-math"

        if tag in {"span", "div"} and math_type in {"inline-math", "block-math"}:
            latex = attr_map.get("data-latex", "") or ""
            input_format = "hancom" if attr_map.get("data-input-format") == "hancom" else "latex"
            input_source = attr_map.get("data-input-source") or latex
            safe_class = "ql-math-block" if math_type == "block-math" else "ql-math-inline"
            safe_tag = "div" if math_type == "block-math" else "span"
            self.parts.append(
                f'<{safe_tag} class="{safe_class}" '
                f'data-latex="{html.escape(latex, quote=True)}" '
                f'data-input-format="{input_format}" '
                f'data-input-source="{html.escape(input_source, quote=True)}">'
            )
            # Keep only safe equation data. Drop any embedded KaTeX markup.
            self.math_skip_depth = 1
            self.math_close_tag = safe_tag
            return

        self.parts.append(f"<{tag}>")
        if tag not in self.VOID_TAGS:
            self.stack.append(tag)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID_TAGS:
            self.handle_endtag(tag)

    def handle_endtag(self, tag):
        if self.math_skip_depth is not None:
            self.math_skip_depth -= 1
            if self.math_skip_depth == 0:
                self.math_skip_depth = None
                if self.math_close_tag:
                    self.parts.append(f"</{self.math_close_tag}>")
                    self.math_close_tag = None
            return
        if self.stack and self.stack[-1].startswith("__literal__:"):
            literal_tag = self.stack[-1].split(":", 1)[1]
            self.parts.append(html.escape(f"</{tag}>"))
            if tag == literal_tag:
                self.stack.pop()
            return
        if tag not in self.stack:
            return
        while self.stack:
            current = self.stack.pop()
            self.parts.append(f"</{current}>")
            if current == tag:
                break

    def handle_data(self, data):
        if self.math_skip_depth is None:
            self.parts.append(html.escape(data))

    def finish(self):
        while self.stack:
            tag = self.stack.pop()
            if tag.startswith("__literal__:"):
                self.parts.append(html.escape(f"</{tag.split(':', 1)[1]}>"))
            else:
                self.parts.append(f"</{tag}>")
        return "".join(self.parts)


def sanitize_rich_html(value):
    parser = _RichTextSanitizer()
    parser.feed(value or "")
    parser.close()
    return parser.finish()


def _rich_text_has_content(value):
    if not value:
        return False
    stripped = re.sub(r"<[^>]*>", "", value)
    return bool(html.unescape(stripped).strip() or 'data-latex="' in value)


def render_rich_html(value):
    # Preserve sanitized equation source metadata so existing equations can be edited
    # in the same input format while KaTeX renders only their LaTeX output.
    return sanitize_rich_html(normalize_katex_markup(value or ""))
