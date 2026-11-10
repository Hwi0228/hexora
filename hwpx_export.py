from __future__ import annotations

import copy
import io
import json
import re
import zipfile
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


_TEMPLATE_ROOT = (
    Path(__file__).resolve().parent
    / "hwp"
    / "2026학년도 10월 고1 전국연합학력평가 수학(문제+정답+해설)"
)
_HP = "http://www.hancom.co.kr/hwpml/2011/paragraph"
_HS = "http://www.hancom.co.kr/hwpml/2011/section"
_OPF = "http://www.idpf.org/2007/opf/"
_DC = "http://purl.org/dc/elements/1.1/"
_HA = "http://www.hancom.co.kr/hwpml/2011/app"
_HC = "http://www.hancom.co.kr/hwpml/2011/core"
_HH = "http://www.hancom.co.kr/hwpml/2011/head"
_HM = "http://www.hancom.co.kr/hwpml/2011/master-page"

for _prefix, _namespace in (
    ("hp", _HP), ("hs", _HS), ("opf", _OPF), ("dc", _DC),
    ("ha", _HA), ("hc", _HC), ("hh", _HH), ("hm", _HM),
):
    ET.register_namespace(_prefix, _namespace)


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

@lru_cache(maxsize=1)
def _template_section_layout():
    section_path = _TEMPLATE_ROOT / "Contents" / "section0.xml"
    root = ET.parse(section_path).getroot()
    first_paragraph = root.find(f"{{{_HP}}}p")
    if first_paragraph is None:
        raise RuntimeError("HWPX 서식 템플릿에 첫 문단이 없습니다.")

    section_properties = first_paragraph.find(
        f"./{{{_HP}}}run/{{{_HP}}}secPr"
    )
    column_properties = first_paragraph.find(
        f"./{{{_HP}}}run/{{{_HP}}}ctrl/{{{_HP}}}colPr"
    )
    if section_properties is None or column_properties is None:
        raise RuntimeError("HWPX 서식 템플릿의 페이지 설정을 읽을 수 없습니다.")

    # Preserve A4 page geometry and configure the sample's two-column layout.
    section_properties = copy.deepcopy(section_properties)
    column_properties = copy.deepcopy(column_properties)
    column_properties.set("type", "NEWSPAPER")
    column_properties.set("layout", "LEFT")
    column_properties.set("colCount", "2")
    column_properties.set("sameSz", "1")
    return section_properties, column_properties


def _build_template_header():
    header_path = _TEMPLATE_ROOT / "Contents" / "header.xml"
    root = ET.parse(header_path).getroot()
    char_properties = root.find(f".//{{{_HH}}}charProperties")
    if char_properties is None:
        raise RuntimeError("HWPX 서식의 글자 스타일을 찾을 수 없습니다.")

    if char_properties.find(f"{{{_HH}}}charPr[@id='60']") is None:
        orange_number_style = char_properties.find(f"{{{_HH}}}charPr[@id='21']")
        if orange_number_style is None:
            raise RuntimeError("주황색 문항 번호 스타일을 만들 수 없습니다.")
        orange_number_style = copy.deepcopy(orange_number_style)
        orange_number_style.set("id", "60")
        orange_number_style.set("height", "1500")
        char_properties.append(orange_number_style)
        char_properties.set(
            "itemCnt",
            str(int(char_properties.get("itemCnt", "0")) + 1),
        )

    return ET.tostring(root, encoding="utf-8", xml_declaration=True)

def _build_section_xml(questions, title, include_answers):
    section = ET.Element(f"{{{_HS}}}sec")
    section_properties, column_properties = _template_section_layout()

    first = ET.SubElement(section, f"{{{_HP}}}p", {
        "id": "1000000001", "paraPrIDRef": "19", "styleIDRef": "21",
        "pageBreak": "0", "columnBreak": "0", "merged": "0",
    })
    properties_run = ET.SubElement(first, f"{{{_HP}}}run", {"charPrIDRef": "17"})
    properties_run.append(section_properties)

    control_run = ET.SubElement(first, f"{{{_HP}}}run", {"charPrIDRef": "17"})
    control = ET.SubElement(control_run, f"{{{_HP}}}ctrl")
    control.append(column_properties)

    empty_run = ET.SubElement(first, f"{{{_HP}}}run", {"charPrIDRef": "17"})
    ET.SubElement(empty_run, f"{{{_HP}}}t")

    next_id = 1000000002

    def append_paragraph(
        paragraph_text="",
        *,
        runs=None,
        char_style="17",
        para_style="19",
        page_break=False,
    ):
        nonlocal next_id
        paragraph = ET.SubElement(section, f"{{{_HP}}}p", {
            "id": str(next_id),
            "paraPrIDRef": str(para_style),
            "styleIDRef": "21",
            "pageBreak": "1" if page_break else "0",
            "columnBreak": "0",
            "merged": "0",
        })
        next_id += 1
        run_values = runs or [{"text": str(paragraph_text or ""), "char_style": char_style}]
        for item in run_values:
            run = ET.SubElement(
                paragraph,
                f"{{{_HP}}}run",
                {"charPrIDRef": str(item.get("char_style", char_style))},
            )
            text_node = ET.SubElement(run, f"{{{_HP}}}t")
            text_node.text = str(item.get("text", "") or "")

    for paragraph in _question_paragraphs(questions, title, include_answers):
        append_paragraph(
            paragraph.get("text", ""),
            runs=paragraph.get("runs"),
            char_style=paragraph.get("char_style", "17"),
            para_style=paragraph.get("para_style", "19"),
            page_break=paragraph.get("page_break", False),
        )

    return ET.tostring(section, encoding="utf-8", xml_declaration=True)

def _build_content_package(title):
    package = ET.Element(f"{{{_OPF}}}package", {
        "version": "1.2", "unique-identifier": "hexora-exam", "id": "hexora-exam",
    })
    metadata = ET.SubElement(package, f"{{{_OPF}}}metadata")
    ET.SubElement(metadata, f"{{{_OPF}}}title").text = title
    ET.SubElement(metadata, f"{{{_OPF}}}language").text = "ko"
    ET.SubElement(metadata, f"{{{_OPF}}}meta", {
        "name": "creator", "content": "text",
    }).text = "HEXORA"

    manifest = ET.SubElement(package, f"{{{_OPF}}}manifest")
    manifest_items = (
        ("header", "Contents/header.xml"),
        ("masterpage0", "Contents/masterpage0.xml"),
        ("section0", "Contents/section0.xml"),
        ("settings", "settings.xml"),
    )
    for item_id, href in manifest_items:
        ET.SubElement(manifest, f"{{{_OPF}}}item", {
            "id": item_id, "href": href, "media-type": "application/xml",
        })

    spine = ET.SubElement(package, f"{{{_OPF}}}spine")
    for item_id in ("header", "section0"):
        ET.SubElement(spine, f"{{{_OPF}}}itemref", {
            "idref": item_id, "linear": "yes",
        })
    return ET.tostring(package, encoding="utf-8", xml_declaration=True)


def build_exam_hwpx(questions, title="시험지", include_answers=False):
    if not questions:
        raise ValueError("시험지에 넣을 문항이 없습니다.")
    title = re.sub(r"\s+", " ", str(title or "시험지")).strip()[:100] or "시험지"

    required_files = (
        "Contents/header.xml",
        "Contents/masterpage0.xml",
        "META-INF/container.xml",
        "META-INF/container.rdf",
        "META-INF/manifest.xml",
        "mimetype",
        "settings.xml",
    )
    for relative_path in required_files:
        if not (_TEMPLATE_ROOT / relative_path).is_file():
            raise RuntimeError(f"HWPX 서식 파일이 없습니다: {relative_path}")

    # Keep the original master-page two-column rule and center divider.
    masterpage_bytes = (
        _TEMPLATE_ROOT / "Contents" / "masterpage0.xml"
    ).read_bytes()

    files = {
        "Contents/content.hpf": _build_content_package(title),
        "Contents/header.xml": _build_template_header(),
        "Contents/masterpage0.xml": masterpage_bytes,
        "Contents/section0.xml": _build_section_xml(
            questions, title, include_answers
        ),
        "META-INF/container.xml": (_TEMPLATE_ROOT / "META-INF" / "container.xml").read_bytes(),
        "META-INF/container.rdf": (_TEMPLATE_ROOT / "META-INF" / "container.rdf").read_bytes(),
        "META-INF/manifest.xml": (_TEMPLATE_ROOT / "META-INF" / "manifest.xml").read_bytes(),
        "settings.xml": (_TEMPLATE_ROOT / "settings.xml").read_bytes(),
        "version.xml": (_TEMPLATE_ROOT / "version.xml").read_bytes(),
    }

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        mimetype_info = zipfile.ZipInfo("mimetype")
        mimetype_info.compress_type = zipfile.ZIP_STORED
        archive.writestr(
            mimetype_info,
            (_TEMPLATE_ROOT / "mimetype").read_bytes(),
        )
        for path, data in files.items():
            archive.writestr(path, data, compress_type=zipfile.ZIP_DEFLATED)
    return output.getvalue()
