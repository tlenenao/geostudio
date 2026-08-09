### Task 5: Presigned GET S3 + rendu pur (`app/export/rendering.py`)

**Files:**
- Modify: `core/app/ingestion/storage.py` (ajout d'une fonction)
- Create: `core/app/export/rendering.py`
- Test: `core/tests/test_ingestion_storage.py` (ajouter un cas si le fichier existe, sinon créer un fichier minimal ciblé)
- Test: `core/tests/test_export_rendering.py`

**Interfaces:**
- Produces: `generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str` (`app.ingestion.storage`). `class RenderPage(Protocol)` avec `screenshot(self, *, full_page: bool) -> bytes` et `pdf(self, *, format: str, landscape: bool) -> bytes`. `render_export(page: RenderPage, *, format: Literal["png","pdf"], print_layout: PrintLayout | None) -> bytes` (`app.export.rendering`).

- [ ] **Step 1: Écrire le test de presigned GET, qui échoue**

```python
# core/tests/test_ingestion_storage.py (ajouter à la suite si le fichier existe déjà)
from unittest.mock import MagicMock

from app.ingestion.storage import generate_presigned_get_url


def test_generate_presigned_get_url_calls_boto_with_get_object():
    client = MagicMock()
    client.generate_presigned_url.return_value = "https://minio.example.test/bucket/key?sig=x"
    url = generate_presigned_get_url(client, bucket="geostudio-exports", key="renders/job-1.pdf", expires_in=1800)
    client.generate_presigned_url.assert_called_once_with(
        "get_object", Params={"Bucket": "geostudio-exports", "Key": "renders/job-1.pdf"}, ExpiresIn=1800,
    )
    assert url == "https://minio.example.test/bucket/key?sig=x"
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: FAIL — `ImportError: cannot import name 'generate_presigned_get_url'`

- [ ] **Step 3: Implémenter `generate_presigned_get_url`**

Dans `core/app/ingestion/storage.py`, ajouter juste après `generate_presigned_put_url` (fin du fichier) :

```python
def generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in,
    )
```

- [ ] **Step 4: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_ingestion_storage.py -v`
Expected: PASS

- [ ] **Step 5: Écrire le test de `render_export`, qui échoue**

```python
# core/tests/test_export_rendering.py
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
```

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.export.rendering'`

- [ ] **Step 7: Implémenter**

```python
# core/app/export/rendering.py
# SPDX-License-Identifier: Apache-2.0
"""Fonction de rendu pure (SP-17a) : ne connaît rien de Playwright, de S3 ni
de la navigation — prend une page déjà navigée/prête et produit des octets.
Testable avec un faux `page` (Protocol), le lancement du vrai navigateur
Chromium vit dans app.export.jobs (tâche 6), seul endroit qui a besoin d'un
Playwright réel installé."""
from typing import Literal, Protocol

from app.configs.schemas import PrintLayout


class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(self, *, format: str, landscape: bool) -> bytes: ...


def render_export(page: RenderPage, *, format: Literal["png", "pdf"], print_layout: PrintLayout | None) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(format=layout.pageSize.upper(), landscape=layout.orientation == "landscape")
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_export_rendering.py -v`
Expected: PASS (3 tests)

- [ ] **Step 9: Commit**

```bash
git add core/app/ingestion/storage.py core/app/export/rendering.py core/tests/test_ingestion_storage.py core/tests/test_export_rendering.py
git commit -m "feat(core): SP-17a — presigned GET S3 + rendu pur render_export"
```

---

