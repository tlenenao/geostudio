## Task 8: `encode_analytics_context`

**Files:**
- Create: `core/app/reports/ctx.py`
- Test: `core/tests/test_report_ctx.py`

**Interfaces:**
- Consumes: `BookmarkPayload` (existing, `core/app/configs/schemas.py`).
- Produces: `encode_analytics_context(bookmark: BookmarkPayload) -> str`, consumed by Task 9.

This must produce the same base64url string shell's `shell/src/lib/analyticsContextUrl.ts::encodeAnalyticsContext` would produce for the equivalent `{timeRange, extent, crossFilter}` state, since `AppRuntimePage` decodes it with `decodeAnalyticsContext` (base64url → JSON, `{timeRange, extent, crossFilter}`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_report_ctx.py
# SPDX-License-Identifier: Apache-2.0
import base64
import json

from app.configs.schemas import BookmarkPayload
from app.reports.ctx import encode_analytics_context


def _decode(raw: str) -> dict:
    # Mirrors shell/src/lib/analyticsContextUrl.ts::decodeAnalyticsContext's
    # base64url handling exactly (- -> +, _ -> /, re-pad to a multiple of 4).
    padded = raw.replace("-", "+").replace("_", "/")
    padded += "=" * ((4 - len(padded) % 4) % 4)
    return json.loads(base64.b64decode(padded).decode("utf-8"))


def test_encode_round_trips_full_context():
    bookmark = BookmarkPayload.model_validate({
        "appId": "app-1", "pageId": "page-1",
        "timeRange": {"from": "2026-01-01", "to": "2026-12-31"},
        "extent": [1.0, 2.0, 3.0, 4.0],
        "crossFilter": {
            "dataset-1": {"field": "score", "value": {"from": "10", "to": "90"}, "originSourceId": "src-1"},
        },
    })

    encoded = encode_analytics_context(bookmark)
    decoded = _decode(encoded)

    assert decoded["timeRange"] == {"from": "2026-01-01", "to": "2026-12-31"}
    assert decoded["extent"] == [1.0, 2.0, 3.0, 4.0]
    assert decoded["crossFilter"] == {
        "dataset-1": {"field": "score", "value": {"from": "10", "to": "90"}, "originSourceId": "src-1"},
    }


def test_encode_handles_empty_context():
    bookmark = BookmarkPayload.model_validate({"appId": "app-1", "pageId": "page-1"})

    decoded = _decode(encode_analytics_context(bookmark))

    assert decoded == {"timeRange": None, "extent": None, "crossFilter": {}}


def test_encode_is_url_safe():
    bookmark = BookmarkPayload.model_validate({
        "appId": "app-1", "pageId": "page-1",
        "crossFilter": {"f": {"field": "libellé", "value": ["a", "b", "c???/+++"], "originSourceId": "s"}},
    })

    encoded = encode_analytics_context(bookmark)

    assert "+" not in encoded
    assert "/" not in encoded
    assert "=" not in encoded
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_report_ctx.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.reports.ctx'`.

- [ ] **Step 3: Write `ctx.py`**

```python
# core/app/reports/ctx.py
# SPDX-License-Identifier: Apache-2.0
"""Mirrors shell/src/lib/analyticsContextUrl.ts::encodeAnalyticsContext byte
for byte: base64url (RFC 4648 §5) of the UTF-8 JSON encoding of
{timeRange, extent, crossFilter} — the exact three fields AppRuntimePage's
decodeAnalyticsContext reads back out of ?ctx=. Kept as its own tiny module
(not inlined in jobs.py) so it can be unit-tested against the JS
implementation's exact wire format without needing a running sweep."""
import base64
import json

from app.configs.schemas import BookmarkPayload


def encode_analytics_context(bookmark: BookmarkPayload) -> str:
    state = {
        "timeRange": bookmark.timeRange.model_dump(by_alias=True) if bookmark.timeRange else None,
        "extent": list(bookmark.extent) if bookmark.extent else None,
        "crossFilter": {key: entry.model_dump() for key, entry in bookmark.crossFilter.items()},
    }
    json_bytes = json.dumps(state).encode("utf-8")
    return base64.urlsafe_b64encode(json_bytes).decode("ascii").rstrip("=")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_report_ctx.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
cd /home/lenen/projets/geostudio
git add core/app/reports/ctx.py core/tests/test_report_ctx.py
git commit -m "feat(core): encode_analytics_context mirrors shell's ?ctx= wire format (SP-17b)"
```

---

