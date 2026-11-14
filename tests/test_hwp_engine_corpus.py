import io
import unittest
import zipfile

from hwp_engine.adapters import default_registry
from hwp_engine.assembly import assemble_document
from hwp_engine.core import HwpCoreExtractor


HWP_NS = "http://www.hancom.co.kr/hwpml/2011/paragraph"
SECTION_NS = "http://www.hancom.co.kr/hwpml/2011/section"
HEAD_NS = "http://www.hancom.co.kr/hwpml/2011/head"
OPF_NS = "http://www.idpf.org/2007/opf/"
CONTAINER_NS = "urn:oasis:names:tc:opendocument:xmlns:container"


def build_original_hwpx_fixture():
    """Create a small, original OWPML package; no third-party exam content."""
    paragraphs = (
        "1. 다음 중 옳은 것은?",
        "① 가 ② 나",
        "2. 다음 중 바른 것은?",
        "① 다 ② 라",
        "정답 및 해설",
        "1. (답) ②",
        "2. (답) ①",
    )
    section = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        f'<hs:sec xmlns:hs="{SECTION_NS}" xmlns:hp="{HWP_NS}">',
    ]
    for index, text in enumerate(paragraphs, 1):
        section.append(
            f'<hp:p id="{index}" paraPrIDRef="0" styleIDRef="0" '
            f'pageBreak="0" columnBreak="0" merged="0">'
            f'<hp:run charPrIDRef="0"><hp:t>{text}</hp:t></hp:run></hp:p>'
        )
    section.append("</hs:sec>")
    section_xml = "".join(section).encode("utf-8")

    content = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<opf:package xmlns:opf="{OPF_NS}" version="1.2" '
        f'unique-identifier="hexora-test" id="hexora-test">'
        f'<opf:metadata><opf:title>HEXORA original regression fixture</opf:title>'
        f'<opf:language>ko</opf:language></opf:metadata>'
        f'<opf:manifest>'
        f'<opf:item id="header" href="Contents/header.xml" media-type="application/xml"/>'
        f'<opf:item id="section0" href="Contents/section0.xml" media-type="application/xml"/>'
        f'</opf:manifest><opf:spine>'
        f'<opf:itemref idref="header" linear="yes"/>'
        f'<opf:itemref idref="section0" linear="yes"/>'
        f'</opf:spine></opf:package>'
    ).encode("utf-8")
    header = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<hh:head xmlns:hh="{HEAD_NS}" version="1.2" secCnt="1">'
        f'<hh:beginNum page="1" footnote="1" endnote="1" pic="1" tbl="1" equation="1"/>'
        f'<hh:refList/></hh:head>'
    ).encode("utf-8")
    container = (
        f'<?xml version="1.0" encoding="UTF-8"?>'
        f'<ocf:container xmlns:ocf="{CONTAINER_NS}"><ocf:rootfiles>'
        f'<ocf:rootfile full-path="Contents/content.hpf" '
        f'media-type="application/hwpml-package+xml"/>'
        f'</ocf:rootfiles></ocf:container>'
    ).encode("utf-8")

    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        mimetype = zipfile.ZipInfo("mimetype")
        mimetype.compress_type = zipfile.ZIP_STORED
        archive.writestr(mimetype, b"application/hwp+zip")
        archive.writestr("META-INF/container.xml", container)
        archive.writestr("Contents/content.hpf", content)
        archive.writestr("Contents/header.xml", header)
        archive.writestr("Contents/section0.xml", section_xml)
    return output.getvalue()


class HwpRegressionCorpusTests(unittest.TestCase):
    def test_original_hwpx_fixture_runs_through_reader_detector_and_assembler(self):
        fixture = build_original_hwpx_fixture()
        with zipfile.ZipFile(io.BytesIO(fixture)) as archive:
            self.assertEqual(archive.testzip(), None)
            self.assertEqual(archive.read("mimetype"), b"application/hwp+zip")

        document = HwpCoreExtractor().extract_bytes(
            fixture, filename="hexora-original-prefix-answer.hwpx"
        )
        self.assertEqual(document.source_format, "hwpx")
        self.assertTrue(any("다음 중 옳은 것은" in block.text for block in document.blocks))

        result = assemble_document(document, default_registry())
        self.assertTrue(result.valid, result.issues)
        self.assertEqual(len(result.questions), 2)
        self.assertEqual([question.answer for question in result.questions], ["②", "①"])


if __name__ == "__main__":
    unittest.main()
