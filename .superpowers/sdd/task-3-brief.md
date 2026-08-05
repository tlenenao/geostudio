## Task 3: Core — `crossFilterLinks` on `DatasetPayload`

**Files:**
- Modify: `core/app/configs/schemas.py:2-4` (`Annotated` import), `:95-102` (`DatasetPayload`, insert new models above it)
- Test: `core/tests/test_dataset_config_schema.py` (append)

**Interfaces:**
- Produces: `DatasetCrossFilterLinkAttribute(mode="attribute", targetDatasetId: str, sourceField: str, targetField: str)`, `DatasetCrossFilterLinkSpatial(mode="spatial", targetDatasetId: str, precision: Literal["bbox","exact"]="bbox")`, and `DatasetPayload.crossFilterLinks: list[...]` (discriminated union on `mode`, default `[]`). These are the exact names the shell's round-trip (Task 4) mirrors field-for-field, same convention as `BookmarkPayload` mirroring `AnalyticsContextState`.

- [ ] **Step 1: Write the failing schema tests**

Append to `core/tests/test_dataset_config_schema.py`:

```python
def test_dataset_config_cross_filter_links_default_empty():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.dataset.crossFilterLinks == []


def test_dataset_config_attribute_cross_filter_link():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {"mode": "attribute", "targetDatasetId": "ds-2", "sourceField": "commune", "targetField": "nom_commune"},
    ]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "attribute"
    assert link.targetDatasetId == "ds-2"
    assert link.sourceField == "commune"
    assert link.targetField == "nom_commune"


def test_dataset_config_spatial_cross_filter_link_defaults_to_bbox_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "spatial", "targetDatasetId": "ds-2"}]
    config = BuilderConfig.model_validate(body)
    link = config.dataset.crossFilterLinks[0]
    assert link.mode == "spatial"
    assert link.precision == "bbox"


def test_dataset_config_spatial_cross_filter_link_exact_precision():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [
        {"mode": "spatial", "targetDatasetId": "ds-2", "precision": "exact"},
    ]
    config = BuilderConfig.model_validate(body)
    assert config.dataset.crossFilterLinks[0].precision == "exact"


def test_dataset_config_cross_filter_link_unknown_mode_rejected():
    body = _dataset_body()
    body["dataset"]["crossFilterLinks"] = [{"mode": "join", "targetDatasetId": "ds-2"}]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -k cross_filter -v`
Expected: FAIL — `DatasetPayload` has no field `crossFilterLinks` (Pydantic silently drops the unrecognized key by default, so `config.dataset.crossFilterLinks` raises `AttributeError`).

- [ ] **Step 3: Implement**

In `core/app/configs/schemas.py`, extend the import (line 2):

```python
from typing import Annotated, Literal
```

Insert right before `class DatasetPayload` (after `DatasetColumnMeta`):

```python
class DatasetCrossFilterLinkAttribute(BaseModel):
    mode: Literal["attribute"] = "attribute"
    targetDatasetId: str
    sourceField: str
    targetField: str


class DatasetCrossFilterLinkSpatial(BaseModel):
    mode: Literal["spatial"] = "spatial"
    targetDatasetId: str
    precision: Literal["bbox", "exact"] = "bbox"


DatasetCrossFilterLink = Annotated[
    DatasetCrossFilterLinkAttribute | DatasetCrossFilterLinkSpatial,
    Field(discriminator="mode"),
]
```

Extend `DatasetPayload` (add the field right after `reactsToExtent`):

```python
class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None
    arcgisItemId: str | None = None
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None
    reactsToExtent: bool = False
    crossFilterLinks: list[DatasetCrossFilterLink] = Field(default_factory=list)  # SP-14n
```

(the `_require_source_id` validator below is unchanged).

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: PASS (all tests in the file, including the 5 new ones).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: same baseline plus 5 new tests, no regressions — `crossFilterLinks` is additive with a default, so every existing dataset payload (without it) still validates identically.

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_dataset_config_schema.py
git commit -m "feat(core): crossFilterLinks on DatasetPayload (SP-14n)"
```

---

