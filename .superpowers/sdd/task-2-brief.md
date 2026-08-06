## Task 2: `BuilderConfig` gains `kind="pipeline"`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_pipeline_config_schema.py`

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: `PipelineNode`, `PipelineEdge`, `PipelinePayload` in
  `app.configs.schemas`, `BuilderConfig.kind` literal gains `"pipeline"`,
  `BuilderConfig.pipeline: PipelinePayload | None`. Consumed by every later
  task (`config.pipeline`, `node.id`/`node.kind`/`node.op`/`node.params`,
  `edge.from_`/`edge.to`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_config_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _pipeline_body() -> dict:
    return {
        "version": 1,
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection",
                 "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection",
                 "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }


def test_pipeline_config_valide():
    config = BuilderConfig.model_validate(_pipeline_body())
    assert config.kind == "pipeline"
    assert config.pipeline.nodes[0].op == "reader.collection"
    assert config.pipeline.edges[0].from_ == "r1"


def test_pipeline_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "pipeline"})


def test_pipeline_config_ids_dupliques_rejetes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][1]["id"] = "r1"
    with pytest.raises(ValidationError, match="unique"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_edge_vers_noeud_inconnu_rejetee():
    body = _pipeline_body()
    body["pipeline"]["edges"][0]["to"] = "does-not-exist"
    with pytest.raises(ValidationError, match="unknown node"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_reader_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][1]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="reader"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_sans_writer_rejete():
    body = _pipeline_body()
    body["pipeline"]["nodes"] = [body["pipeline"]["nodes"][0]]
    body["pipeline"]["edges"] = []
    with pytest.raises(ValidationError, match="writer"):
        BuilderConfig.model_validate(body)


def test_pipeline_config_x_y_when_acceptes_mais_inertes():
    body = _pipeline_body()
    body["pipeline"]["nodes"][0]["x"] = 100
    body["pipeline"]["nodes"][0]["y"] = 40
    body["pipeline"]["edges"][0]["when"] = "true"
    config = BuilderConfig.model_validate(body)
    assert config.pipeline.nodes[0].x == 100
    assert config.pipeline.edges[0].when == "true"
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: FAIL — `pydantic_core._pydantic_core.ValidationError: ... Input should be 'app', 'dashboard', 'map', 'site', 'dataset' or 'bookmark'` (kind literal doesn't yet accept "pipeline")

- [ ] **Step 3: Add the schemas**

In `core/app/configs/schemas.py`, change the import line at the top:

```python
from typing import Annotated, Any, Literal
```

Then add, right after `BookmarkPayload` (after line 165, before `class BuilderConfig`):

```python
class PipelineNode(BaseModel):
    id: str
    kind: Literal["reader", "transform", "writer"]
    op: str
    x: int = 0
    y: int = 0                    # idiome LayoutItem, inutilisé tant qu'il n'y a pas de
                                   # canvas (SP-15b) — posé maintenant pour ne pas migrer
                                   # le schéma plus tard (design SP-15a §4.1)
    params: dict[str, Any] = Field(default_factory=dict)
    title: str | None = None


class PipelineEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    id: str
    from_: str = Field(alias="from")
    to: str
    when: str | None = None       # CEL, routage conditionnel — accepté mais non
                                   # interprété par le compilateur avant Phase 3/4


class PipelinePayload(BaseModel):
    nodes: list[PipelineNode] = Field(default_factory=list)
    edges: list[PipelineEdge] = Field(default_factory=list)

    @model_validator(mode="after")
    def _validate_graph(self) -> "PipelinePayload":
        ids = [n.id for n in self.nodes]
        if len(ids) != len(set(ids)):
            raise ValueError("pipeline node ids must be unique")
        id_set = set(ids)
        for edge in self.edges:
            if edge.from_ not in id_set:
                raise ValueError(f"edge references unknown node '{edge.from_}'")
            if edge.to not in id_set:
                raise ValueError(f"edge references unknown node '{edge.to}'")
        if not any(n.kind == "reader" for n in self.nodes):
            raise ValueError("pipeline requires at least one reader node")
        if not any(n.kind == "writer" for n in self.nodes):
            raise ValueError("pipeline requires at least one writer node")
        return self
```

Then in `BuilderConfig`, change the `kind` literal:

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline"]
```

Add the payload field right after `bookmark: BookmarkPayload | None = None`:

```python
    pipeline: PipelinePayload | None = None
```

And add a branch to `_require_kind_payload`, right after the bookmark check:

```python
        if self.kind == "pipeline" and self.pipeline is None:
            raise ValueError("pipeline config requires a pipeline payload")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_config_schema.py -v`
Expected: PASS (7 tests green)

- [ ] **Step 5: Run the full configs test suite to check no regression**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py tests/test_configs_models.py -v`
Expected: PASS (unchanged)

- [ ] **Step 6: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_pipeline_config_schema.py
git commit -m "feat(core): add BuilderConfig kind=pipeline (PipelinePayload/Node/Edge)"
```

---

