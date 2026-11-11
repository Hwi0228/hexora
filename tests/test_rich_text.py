from rich_text import _rich_text_has_content, sanitize_rich_html


def test_rich_text_strips_presentation_styles():
    html = '<p style="font-size: 32px; letter-spacing: 8px; line-height: 3">문제</p>'
    assert sanitize_rich_html(html) == "<p>문제</p>"


def test_rich_text_preserves_table_structure_and_spans():
    html = (
        '<table><tbody><tr><td colspan="2">가</td></tr>'
        '<tr><td rowspan="2">나</td><td>다</td></tr></tbody></table>'
    )
    assert sanitize_rich_html(html) == (
        "<table><tbody><tr><td colspan=\"2\">가</td></tr>"
        "<tr><td rowspan=\"2\">나</td><td>다</td></tr></tbody></table>"
    )


def test_rich_text_preserves_embedded_image():
    html = '<p><img src="data:image/webp;base64,QUJD" alt="도형"></p>'
    assert sanitize_rich_html(html) == html
    assert _rich_text_has_content(html)


def test_rich_text_rejects_unsafe_image_sources():
    html = '<p><img src="javascript:alert(1)" alt="unsafe"></p>'
    assert sanitize_rich_html(html) == "<p></p>"
    assert not _rich_text_has_content(sanitize_rich_html(html))
