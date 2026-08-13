## Task 5: PDF footer template (generation date) on every export

**Files:**
- Modify: `core/app/export/rendering.py`
- Test: `core/tests/test_export_rendering.py` (extended)

**Interfaces:**
- Produces: `render_export(page, *, format, print_layout)` now calls `page.pdf(..., display_header_footer=True, footer_template=...)`. `RenderPage.pdf` Protocol signature grows two required kwargs.

- [ ] **Step 1: Write the failing test**

Read `core/tests/test_export_rendering.py` first for its existing fake-page fixture (it will need a `pdf(self, **kwargs)` that records kwargs — reuse it, extending its recorded-kwargs assertion). Add:

```python
def test_render_export_pdf_sets_display_header_footer_with_generation_date_template():
    page = _FakePage()  # reuse this file's existing fake
    render_export(page, format="pdf", print_layout=None)

    assert page.pdf_kwargs["display_header_footer"] is True
    assert "Généré le" in page.pdf_kwargs["footer_template"]
    assert '<span class="date">' in page.pdf_kwargs["footer_template"]
```

If the existing fake page's `pdf()` doesn't record its kwargs on a `pdf_kwargs` attribute already, extend the fake in this file to do so — check what the pre-existing `test_render_export_*` tests already assert against before renaming anything.

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_export_rendering.py -k footer -v`
Expected: FAIL — `KeyError: 'display_header_footer'` or similar.

- [ ] **Step 3: Update `RenderPage` and `render_export`**

```python
# core/app/export/rendering.py
class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(
        self, *, format: str, landscape: bool, print_background: bool,
        display_header_footer: bool, footer_template: str,
    ) -> bytes: ...


_FOOTER_TEMPLATE = (
    '<div style="font-size:8px; width:100%; text-align:center; color:#666;">'
    'Généré le <span class="date"></span></div>'
)


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(
        format=layout.pageSize.upper(), landscape=layout.orientation == "landscape", print_background=True,
        # display_header_footer/footer_template (SP-17b) : seul morceau
        # d'"en-tête/pied" retenu dans le périmètre resserré du design — pas
        # de numérotation de section, une seule page source par export.
        # <span class="date"> est une classe Chromium native, remplie
        # automatiquement à la date du rendu — rien à calculer côté Python.
        display_header_footer=True, footer_template=_FOOTER_TEMPLATE,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: PASS, no regressions.

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/export/rendering.py core/tests/test_export_rendering.py
git commit -m "feat(core): PDF exports get a generation-date footer (SP-17b)"
```

---

