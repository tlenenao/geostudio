# SP-17a Task 5 Report: Presigned GET S3 + Rendu pur

**Status:** DONE

## Summary

Task 5 delivered two small, independent pure functions for the Playwright export worker (SP-17a):
1. **`generate_presigned_get_url()`** — S3 presigned GET helper (mirrors existing `generate_presigned_put_url`)
2. **`render_export()`** — Pure rendering function that converts an already-navigated page to PNG/PDF bytes

Both implemented TDD (RED → GREEN) with full test coverage. Full core test suite remains green.

## Implementation Details

### 1. Presigned GET Helper (`core/app/ingestion/storage.py`)

**Added function:**
```python
def generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str:
    return client.generate_presigned_url(
        "get_object", Params={"Bucket": bucket, "Key": key}, ExpiresIn=expires_in,
    )
```

- Mirrors `generate_presigned_put_url()` signature and pattern
- Calls boto3 `generate_presigned_url()` with `"get_object"` operation
- Default expiry: 3600s (vs 900s for PUT — longer for reads)
- Used by Task 6 to generate download URLs for rendered exports on S3

**Test added to `core/tests/test_ingestion_storage.py`:**
- Verifies exact boto3 call shape: method name, Params dict with Bucket/Key, ExpiresIn
- Tests presigned URL generation via fake S3 client
- Passed: ✓

### 2. Pure Rendering Function (`core/app/export/rendering.py` — NEW)

**Interfaces:**
```python
class RenderPage(Protocol):
    def screenshot(self, *, full_page: bool) -> bytes: ...
    def pdf(self, *, format: str, landscape: bool) -> bytes: ...

def render_export(
    page: RenderPage, 
    *, 
    format: Literal["png", "pdf"], 
    print_layout: PrintLayout | None
) -> bytes:
    if format == "png":
        return page.screenshot(full_page=True)
    layout = print_layout or PrintLayout()
    return page.pdf(
        format=layout.pageSize.upper(), 
        landscape=layout.orientation == "landscape"
    )
```

**Design:**
- `RenderPage` Protocol allows testing with fake pages (no Playwright import)
- Playwright integration happens in Task 6 (`app.export.jobs`)
- PNG: calls `page.screenshot(full_page=True)`
- PDF: defaults to PrintLayout() if None, then calls `page.pdf(format=pageSize.upper(), landscape=bool)`
- Correctly maps PrintLayout fields:
  - `pageSize` ("a4"/"a3") → PDF format uppercase ("A4"/"A3")
  - `orientation` ("portrait"/"landscape") → boolean landscape flag

**Tests in `core/tests/test_export_rendering.py` (3 tests):**

1. **`test_render_export_png_takes_full_page_screenshot()`**
   - Verifies PNG format calls `screenshot(full_page=True)`
   - Confirms PDF not called

2. **`test_render_export_pdf_uses_default_layout_when_none()`**
   - Verifies PDF with `print_layout=None` defaults to PrintLayout()
   - Expects `pdf(format="A4", landscape=False)` (A4 portrait)

3. **`test_render_export_pdf_respects_page_size_and_orientation()`**
   - Verifies custom PrintLayout respected
   - Tests A3 landscape: expects `pdf(format="A3", landscape=True)`

All passed: ✓✓✓

## TDD Flow (Evidence)

### Step 1-2: Presigned GET Test (RED)
```
ImportError: cannot import name 'generate_presigned_get_url'
```

### Step 3-4: Implement Presigned GET (GREEN)
```
tests/test_ingestion_storage.py::test_generate_presigned_get_url_calls_boto_with_get_object PASSED [100%]
```

### Step 5-6: Render Export Tests (RED)
```
ModuleNotFoundError: No module named 'app.export.rendering'
```

### Step 7-8: Implement Render Export (GREEN)
```
tests/test_export_rendering.py::test_render_export_png_takes_full_page_screenshot PASSED [ 33%]
tests/test_export_rendering.py::test_render_export_pdf_uses_default_layout_when_none PASSED [ 66%]
tests/test_export_rendering.py::test_render_export_pdf_respects_page_size_and_orientation PASSED [100%]

3 passed in 0.13s
```

## Files Changed

**Modified:**
- `core/app/ingestion/storage.py` — Added `generate_presigned_get_url()` function
- `core/tests/test_ingestion_storage.py` — Added import + one test case

**Created:**
- `core/app/export/rendering.py` — New module with RenderPage Protocol + render_export()
- `core/tests/test_export_rendering.py` — New test module with 3 test cases

## Self-Review Findings

✓ **Presigned GET test verification:**
  - Inspects exact boto3 call shape: method name `"get_object"`, Params dict, ExpiresIn
  - Confirms URL returned from mocked client
  - No issues

✓ **Render export test coverage:**
  - All 3 tests pass
  - Fake page genuinely records method calls in `screenshot_calls` / `pdf_calls` lists
  - Tests verify both call recording AND return values

✓ **PNG format handling:**
  - Correctly calls `page.screenshot(full_page=True)` only for PNG
  - Does NOT call `.pdf()` for PNG (verified by empty `page.pdf_calls` list in test 1)

✓ **PDF format + default layout:**
  - Correctly defaults to `PrintLayout()` when `print_layout=None`
  - Default PrintLayout: A4 portrait (verified in test 2)

✓ **PDF format + custom layout:**
  - Correctly applies custom PrintLayout fields
  - pageSize mapping works (lowercase "a3" → uppercase "A3")
  - orientation mapping works (string "landscape" → boolean True)

✓ **No regressions:**
  - Full core test suite: 1303 passed, 137 skipped (identical to pre-task baseline)
  - No new failures
  - No import or module issues

## Concerns

None. Both implementations are minimal, pure, and well-tested. The render_export function deliberately uses Protocol for testability and leaves Playwright integration to Task 6.

## Test Results

**Task-specific tests:**
```
tests/test_ingestion_storage.py::test_generate_presigned_get_url_calls_boto_with_get_object PASSED
tests/test_export_rendering.py::test_render_export_png_takes_full_page_screenshot PASSED
tests/test_export_rendering.py::test_render_export_pdf_uses_default_layout_when_none PASSED
tests/test_export_rendering.py::test_render_export_pdf_respects_page_size_and_orientation PASSED
```

**Full suite:**
```
1303 passed, 137 skipped in 85.22s
```

## Commit

```
f27baf0 feat(core): SP-17a task 5 — presigned GET S3 + rendu pur render_export
```

Message: Implements presigned GET helper + pure render_export function with 4 tests (1 storage, 3 rendering). Full suite green.
