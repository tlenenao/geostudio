# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import PrintLayout
from app.export.rendering import render_export


class _FakePage:
    def __init__(self):
        self.screenshot_calls = []
        self.pdf_calls = []

    def screenshot(self, *, full_page: bool) -> bytes:
        self.screenshot_calls.append(full_page)
        return b"PNGDATA"

    def pdf(self, *, format: str, landscape: bool) -> bytes:
        self.pdf_calls.append((format, landscape))
        return b"PDFDATA"


def test_render_export_png_takes_full_page_screenshot():
    page = _FakePage()
    result = render_export(page, format="png", print_layout=None)
    assert result == b"PNGDATA"
    assert page.screenshot_calls == [True]
    assert page.pdf_calls == []


def test_render_export_pdf_uses_default_layout_when_none():
    page = _FakePage()
    result = render_export(page, format="pdf", print_layout=None)
    assert result == b"PDFDATA"
    assert page.pdf_calls == [("A4", False)]


def test_render_export_pdf_respects_page_size_and_orientation():
    page = _FakePage()
    layout = PrintLayout(pageSize="a3", orientation="landscape")
    render_export(page, format="pdf", print_layout=layout)
    assert page.pdf_calls == [("A3", True)]
