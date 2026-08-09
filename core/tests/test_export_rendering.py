# SPDX-License-Identifier: Apache-2.0
from app.configs.schemas import PrintLayout
from app.export.rendering import render_export


class _FakePage:
    def __init__(self):
        self.screenshot_calls = []
        self.pdf_calls = []
        self.pdf_kwargs = {}

    def screenshot(self, *, full_page: bool) -> bytes:
        self.screenshot_calls.append(full_page)
        return b"PNGDATA"

    def pdf(self, **kwargs) -> bytes:
        self.pdf_kwargs = kwargs
        # Record legacy tuple format for backward compatibility with existing tests
        self.pdf_calls.append((kwargs["format"], kwargs["landscape"], kwargs["print_background"]))
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
    assert page.pdf_calls == [("A4", False, True)]


def test_render_export_pdf_respects_page_size_and_orientation():
    page = _FakePage()
    layout = PrintLayout(pageSize="a3", orientation="landscape")
    render_export(page, format="pdf", print_layout=layout)
    assert page.pdf_calls == [("A3", True, True)]


def test_render_export_pdf_always_prints_css_backgrounds():
    # Régression (fix round, finding I5) : Playwright/Chromium défaut
    # print_background à False, ce qui supprime les fonds CSS (ex. les
    # puces bg-white/90 du titre/légende/cartouche). render_export doit
    # toujours demander print_background=True, quel que soit le layout.
    page = _FakePage()
    render_export(page, format="pdf", print_layout=None)
    assert page.pdf_calls[0][2] is True


def test_render_export_pdf_sets_display_header_footer_with_generation_date_template():
    page = _FakePage()
    render_export(page, format="pdf", print_layout=None)

    assert page.pdf_kwargs["display_header_footer"] is True
    assert "Généré le" in page.pdf_kwargs["footer_template"]
    assert '<span class="date">' in page.pdf_kwargs["footer_template"]
