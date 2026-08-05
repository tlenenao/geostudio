## Task 1: Core — `BookmarkPayload` schema (Pydantic)

**Files:**
- Modify: `core/app/configs/schemas.py:88-142` (insert new models before `BuilderConfig`, extend `BuilderConfig.kind`/fields/validator)
- Test: `core/tests/test_bookmark_config_schema.py` (new)

**Interfaces:**
- Produces: `BookmarkCrossFilterEntry(field: str, value: str | list[str], originSourceId: str)`, `BookmarkTimeRange(from_: str [alias "from"], to: str)`, `BookmarkPayload(appId: str, pageId: str, timeRange: BookmarkTimeRange | None, extent: tuple[float,float,float,float] | None, crossFilter: dict[str, BookmarkCrossFilterEntry])`. `BuilderConfig.kind` gains the literal `"bookmark"` and a new field `bookmark: BookmarkPayload | None = None`. These are the exact names Task 2 (validation) and Task 3 (MCP tool) import.

- [ ] **Step 1: Write the failing schema tests**

Create `core/tests/test_bookmark_config_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _bookmark_body(**overrides) -> dict:
    body = {
        "version": 1,
        "kind": "bookmark",
        "bookmark": {
            "appId": "app-1",
            "pageId": "page-1",
            "timeRange": {"from": "2026-01-01", "to": "2026-02-01"},
            "extent": [2.0, 46.0, 3.0, 47.0],
            "crossFilter": {
                "dataset-1": {"field": "region", "value": "Nord", "originSourceId": "src-1"},
            },
        },
    }
    body["bookmark"].update(overrides)
    return body


def test_bookmark_config_valide():
    config = BuilderConfig.model_validate(_bookmark_body())
    assert config.kind == "bookmark"
    assert config.bookmark.appId == "app-1"
    assert config.bookmark.pageId == "page-1"
    assert config.bookmark.timeRange.from_ == "2026-01-01"
    assert config.bookmark.timeRange.to == "2026-02-01"
    assert config.bookmark.extent == (2.0, 46.0, 3.0, 47.0)
    assert config.bookmark.crossFilter["dataset-1"].field == "region"
    assert config.bookmark.crossFilter["dataset-1"].originSourceId == "src-1"


def test_bookmark_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "bookmark"})


def test_bookmark_config_time_range_extent_cross_filter_optionnels():
    body = _bookmark_body()
    del body["bookmark"]["timeRange"]
    del body["bookmark"]["extent"]
    del body["bookmark"]["crossFilter"]
    config = BuilderConfig.model_validate(body)
    assert config.bookmark.timeRange is None
    assert config.bookmark.extent is None
    assert config.bookmark.crossFilter == {}


def test_bookmark_config_page_id_vide_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId=""))


def test_bookmark_config_page_id_blanc_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(_bookmark_body(pageId="   "))


def test_bookmark_config_round_trips_through_dump_and_validate():
    # by_alias=True is what configs_repo.create_config persists with — this
    # is the exact round trip a saved-then-reloaded bookmark goes through.
    config = BuilderConfig.model_validate(_bookmark_body())
    dumped = config.model_dump(by_alias=True)
    assert dumped["bookmark"]["timeRange"]["from"] == "2026-01-01"
    reloaded = BuilderConfig.model_validate(dumped)
    assert reloaded.bookmark.timeRange.from_ == "2026-01-01"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_bookmark_config_schema.py -v`
Expected: FAIL — `kind` literal doesn't accept `"bookmark"` / `BuilderConfig` has no field `bookmark` (Pydantic `ValidationError` raised where the test expects success, or `AttributeError`).

- [ ] **Step 3: Implement the schema**

In `core/app/configs/schemas.py`, insert immediately after the `DatasetPayload` class (after its closing `_require_source_id` validator, before `class BuilderConfig`):

```python
class BookmarkCrossFilterEntry(BaseModel):
    field: str
    value: str | list[str]
    originSourceId: str


class BookmarkTimeRange(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str


class BookmarkPayload(BaseModel):
    appId: str
    pageId: str
    timeRange: BookmarkTimeRange | None = None
    extent: tuple[float, float, float, float] | None = None
    crossFilter: dict[str, BookmarkCrossFilterEntry] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _require_non_empty_page_id(self) -> "BookmarkPayload":
        if not self.pageId.strip():
            raise ValueError("bookmark pageId must not be empty")
        return self
```

Then edit `BuilderConfig` (same file):

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark"]
```

and add the field alongside `dataset`:

```python
    dataset: DatasetPayload | None = None
    bookmark: BookmarkPayload | None = None
```

and extend `_require_kind_payload`:

```python
        if self.kind == "dataset" and self.dataset is None:
            raise ValueError("dataset config requires a dataset payload")
        if self.kind == "bookmark" and self.bookmark is None:
            raise ValueError("bookmark config requires a bookmark payload")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_bookmark_config_schema.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: same pass/skip counts as before, plus the 6 new tests (no existing test references an exhaustive `kind` literal list, per the earlier grep sweep of `core/app`).

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_bookmark_config_schema.py
git commit -m "feat(core): bookmark config schema (SP-14m)"
```
