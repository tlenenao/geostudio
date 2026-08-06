## Task 3: Op catalogue (8 data-only ops)

**Files:**
- Create: `core/app/pipelines/__init__.py`
- Create: `core/app/pipelines/ops/__init__.py`
- Create: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `OP_KINDS: dict[str, str]`, `OP_PARAMS: dict[str, type[BaseModel]]`,
  `parse_op_params(op: str, params: dict) -> BaseModel`,
  `ops_catalog() -> dict[str, dict]` in `app.pipelines.ops.schemas`. The
  8 param classes (`ReaderCollectionParams`, `TransformFilterParams`,
  `TransformSelectParams`, `TransformDeriveParams`, `TransformAggregateParams`,
  `TransformJoinParams`, `WriterCollectionParams`, `WriterExportParams`) are
  imported directly by Tasks 5, 6 and 8.

- [ ] **Step 1: Create the package skeleton**

Create `core/app/pipelines/__init__.py` (empty file, just the license header):

```python
# SPDX-License-Identifier: Apache-2.0
```

Create `core/app/pipelines/ops/__init__.py` (same, empty):

```python
# SPDX-License-Identifier: Apache-2.0
```

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_pipeline_ops_schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.pipelines.ops.schemas import OP_KINDS, OP_PARAMS, ops_catalog, parse_op_params


def test_all_eight_phase1_ops_are_registered():
    assert set(OP_PARAMS) == {
        "reader.collection", "transform.filter", "transform.select",
        "transform.derive", "transform.aggregate", "transform.join",
        "writer.collection", "writer.export",
    }
    assert set(OP_KINDS) == set(OP_PARAMS)


@pytest.mark.parametrize(
    "op,kind",
    [
        ("reader.collection", "reader"),
        ("transform.filter", "transform"),
        ("transform.select", "transform"),
        ("transform.derive", "transform"),
        ("transform.aggregate", "transform"),
        ("transform.join", "transform"),
        ("writer.collection", "writer"),
        ("writer.export", "writer"),
    ],
)
def test_op_kind_matches(op, kind):
    assert OP_KINDS[op] == kind


def test_parse_op_params_reader_collection():
    params = parse_op_params("reader.collection", {"collectionId": "villes"})
    assert params.collectionId == "villes"


def test_parse_op_params_missing_required_field_raises():
    with pytest.raises(ValidationError):
        parse_op_params("reader.collection", {})


def test_parse_op_params_unknown_op_raises():
    with pytest.raises(ValueError, match="unknown op"):
        parse_op_params("transform.does-not-exist", {})


def test_transform_join_defaults_how_to_inner():
    params = parse_op_params("transform.join", {"withCollectionId": "x", "on": "code"})
    assert params.how == "inner"


def test_writer_export_requires_format_and_key():
    params = parse_op_params("writer.export", {"format": "csv", "key": "out.csv"})
    assert params.format == "csv"
    assert params.key == "out.csv"
    with pytest.raises(ValidationError):
        parse_op_params("writer.export", {"key": "out.csv"})


def test_ops_catalog_exposes_json_schema_per_op():
    catalog = ops_catalog()
    assert set(catalog) == set(OP_PARAMS)
    for op, entry in catalog.items():
        assert entry["kind"] == OP_KINDS[op]
        assert "properties" in entry["paramsSchema"]
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.pipelines.ops.schemas'`

- [ ] **Step 4: Implement the op catalogue**

Create `core/app/pipelines/ops/schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Catalogue des 8 opérations de données pures livrées en Phase 1 (SP-15a) —
la fourchette 6-8 op de l'étude de faisabilité §5. Chaque op porte un
manifeste de params typé (Pydantic), publié en JSON Schema par
GET /pipelines/ops pour que SP-15b réutilise le mécanisme
WcWidgetManifest/generatedPropsPanel (SP-8a) sans redesign (design §5).

filter.expr/derive.expr/aggregate.metrics[*] sont des chaînes SQL DuckDB
bornées, PAS du CEL (correction du design §5.1 — aucun moteur CEL ne
tourne côté serveur) : elles ne sont validées syntaxiquement qu'à
l'exécution (app.pipelines.expr_validation), jamais ici — ce module ne
valide que la FORME des params, pas la sémantique des expressions."""
from typing import Literal

from pydantic import BaseModel, Field


class ReaderCollectionParams(BaseModel):
    collectionId: str


class TransformFilterParams(BaseModel):
    expr: str


class TransformSelectParams(BaseModel):
    columns: dict[str, str | None] = Field(default_factory=dict)


class TransformDeriveParams(BaseModel):
    column: str
    expr: str


class TransformAggregateParams(BaseModel):
    groupBy: list[str] = Field(default_factory=list)
    metrics: dict[str, str] = Field(default_factory=dict)


class TransformJoinParams(BaseModel):
    withCollectionId: str
    on: str
    how: Literal["inner", "left"] = "inner"


class WriterCollectionParams(BaseModel):
    collectionId: str


class WriterExportParams(BaseModel):
    format: Literal["geojson", "csv"]
    key: str


OP_KINDS: dict[str, str] = {
    "reader.collection": "reader",
    "transform.filter": "transform",
    "transform.select": "transform",
    "transform.derive": "transform",
    "transform.aggregate": "transform",
    "transform.join": "transform",
    "writer.collection": "writer",
    "writer.export": "writer",
}

OP_PARAMS: dict[str, type[BaseModel]] = {
    "reader.collection": ReaderCollectionParams,
    "transform.filter": TransformFilterParams,
    "transform.select": TransformSelectParams,
    "transform.derive": TransformDeriveParams,
    "transform.aggregate": TransformAggregateParams,
    "transform.join": TransformJoinParams,
    "writer.collection": WriterCollectionParams,
    "writer.export": WriterExportParams,
}


def parse_op_params(op: str, params: dict) -> BaseModel:
    model = OP_PARAMS.get(op)
    if model is None:
        raise ValueError(f"unknown op '{op}'")
    return model.model_validate(params)


def ops_catalog() -> dict[str, dict]:
    return {
        op: {"kind": OP_KINDS[op], "paramsSchema": model.model_json_schema()}
        for op, model in OP_PARAMS.items()
    }
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: PASS (11 tests green)

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/__init__.py core/app/pipelines/ops/__init__.py \
  core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): add Phase 1 pipeline op catalogue (8 data-only ops)"
```

---

