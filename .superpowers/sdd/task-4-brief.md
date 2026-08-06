## Task 4: Structural graph validation (`app.configs` layer) + `/configs` wiring + ETL-disabled guard

**Files:**
- Create: `core/app/configs/pipeline_validation.py`
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_pipeline_config_validation.py`

**Interfaces:**
- Consumes: `BuilderConfig`/`PipelineNode` (Task 2).
- Produces: `register_pipeline_node_validator(op, validator)`,
  `validate_pipeline_payload(session, config, *, user)` in
  `app.configs.pipeline_validation` — consumed by Task 5 (registers real
  validators) and already wired into `configs/routes.py` here. `POST/PUT
  /configs` (and `/configs/by-item/{id}`) now 403 when `kind="pipeline"` and
  `CORE_ETL_ENABLED` is false, and 422 on structural graph errors
  (cycle, >1 incoming edge) when enabled.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_config_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import pipeline_validation as pipeline_validation_module
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _linear_pipeline(**overrides) -> dict:
    body = {
        "title": "Nettoyer villes",
        "config": {
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
        },
    }
    body.update(overrides)
    return body


@pytest.fixture()
def env(monkeypatch):
    # Fake validators, isolating THIS task's structural (cycle/edge-count)
    # logic from Task 5's real op-catalog/collection checks. Using
    # monkeypatch.setitem (not a direct register_pipeline_node_validator
    # call) matters: _node_validators is a module-level global dict with no
    # reset between tests — a direct call here would permanently overwrite
    # whatever app.pipelines.config_validation registered at import time
    # (Task 5), and that overwrite would leak into test_pipeline_node_validation.py's
    # tests if this file happens to run first in the same pytest session
    # (it does, alphabetically: "config_validation" < "node_validation").
    # monkeypatch.setitem restores the previous value automatically at
    # teardown, so this file can never leak state into another test file
    # regardless of execution order.
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "reader.collection",
        lambda session, node, user: None,
    )
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "writer.collection",
        lambda session, node, user: None,
    )

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return TestClient(app)


def test_valid_linear_pipeline_saves(env):
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 201


def test_disabled_capability_refuses_pipeline_creation(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 403


def test_disabled_capability_does_not_affect_other_kinds(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json={
        "title": "App", "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
    })
    assert response.status_code == 201


def test_cyclic_graph_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "1=1"}}
    )
    body["config"]["pipeline"]["edges"] = [
        {"id": "e1", "from": "r1", "to": "t1"},
        {"id": "e2", "from": "t1", "to": "w1"},
        {"id": "e3", "from": "w1", "to": "t1"},
    ]
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "acyclic" in response.json()["detail"]


def test_node_with_two_incoming_edges_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "r2", "kind": "reader", "op": "reader.collection",
         "params": {"collectionId": "quartiers"}}
    )
    body["config"]["pipeline"]["edges"].append({"id": "e2", "from": "r2", "to": "w1"})
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "one incoming edge" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.configs.pipeline_validation'`

- [ ] **Step 3: Implement the registry + structural validation**

Create `core/app/configs/pipeline_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="pipeline" payloads without
importing app.pipelines (forbidden by the layered-architecture contract:
app.pipelines sits above app.configs). Structural graph checks (DAG
acyclic, linear+join topology — feasibility study §4.1 mitigation D1) live
here: they need no knowledge of the op catalogue. Per-node checks (op
exists, params match its manifest, collectionId exists/readable/writable)
are registered by app.pipelines.config_validation, imported for its side
effect by app.main — the only layer allowed to know about both. Mirrors
app.configs.dataset_validation exactly."""
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig, PipelineEdge, PipelineNode
from app.users.models import User

NodeValidator = Callable[[Session, PipelineNode, User], None]

_node_validators: dict[str, NodeValidator] = {}


def register_pipeline_node_validator(op: str, validator: NodeValidator) -> None:
    _node_validators[op] = validator


def _check_linear_topology(edges: list[PipelineEdge]) -> None:
    incoming_count: dict[str, int] = {}
    for edge in edges:
        incoming_count[edge.to] = incoming_count.get(edge.to, 0) + 1
    for node_id, count in incoming_count.items():
        if count > 1:
            raise HTTPException(
                status_code=422,
                detail=f"node '{node_id}' has more than one incoming edge "
                       "(linear+join topology only, SP-15a MVP)",
            )


def _check_acyclic(nodes: list[PipelineNode], edges: list[PipelineEdge]) -> None:
    adjacency: dict[str, list[str]] = {n.id: [] for n in nodes}
    for edge in edges:
        adjacency[edge.from_].append(edge.to)

    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n.id: WHITE for n in nodes}

    def visit(node_id: str) -> bool:
        color[node_id] = GRAY
        for neighbor in adjacency[node_id]:
            if color[neighbor] == GRAY:
                return True
            if color[neighbor] == WHITE and visit(neighbor):
                return True
        color[node_id] = BLACK
        return False

    if any(color[n.id] == WHITE and visit(n.id) for n in nodes):
        raise HTTPException(status_code=422, detail="pipeline graph must be acyclic")


def validate_pipeline_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "pipeline":
        return
    payload = config.pipeline
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload

    _check_acyclic(payload.nodes, payload.edges)
    _check_linear_topology(payload.edges)

    for node in payload.nodes:
        validator = _node_validators.get(node.op)
        if validator is None:
            raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
        validator(session, node, user)
```

- [ ] **Step 4: Wire it into `configs/routes.py`, plus the ETL-disabled guard**

In `core/app/configs/routes.py`, change the import lines at the top (add
`is_etl_enabled` to the existing auth import, add the new validation import
right after the dataset one):

```python
from app.auth.dependency import get_current_user, is_etl_enabled
from app.configs.bookmark_validation import validate_bookmark_payload as _validate_bookmark_payload
from app.configs.dataset_validation import validate_dataset_payload as _validate_dataset_payload
from app.configs.pipeline_validation import validate_pipeline_payload as _validate_pipeline_payload
```

Add this helper right after `_validate_extension_scope` (after line 66):

```python
def _require_etl_enabled_for_pipeline(config: BuilderConfig) -> None:
    if config.kind == "pipeline" and not is_etl_enabled():
        raise HTTPException(status_code=403, detail="ETL capability disabled on this instance")
```

Then call both the guard and the validator at the three write points. In
`create_config` (after the existing `_validate_dataset_payload`/
`_validate_bookmark_payload` calls, i.e. after line 77):

```python
    _require_etl_enabled_for_pipeline(request.config)
    _validate_pipeline_payload(session, request.config, user=user)
```

Actually place the guard *first*, before any other validation (cheapest
check, fail fast) — the full sequence in `create_config` becomes:

```python
    _require_etl_enabled_for_pipeline(request.config)
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
    _validate_bookmark_payload(session, request.config, user=user)
    _validate_pipeline_payload(session, request.config, user=user)
```

In `update_config` (mirrors `create_config`'s sequence, after
`_require_access`):

```python
    _require_etl_enabled_for_pipeline(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
```

In `update_config_by_item` (same sequence, after `_require_access`):

```python
    _require_etl_enabled_for_pipeline(config)
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
    _validate_bookmark_payload(session, config, user=user)
    _validate_pipeline_payload(session, config, user=user)
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 6: Run the full configs suite to check no regression**

Run: `cd core && uv run pytest tests/test_configs_extension_permissions.py tests/test_create_dataset.py tests/test_read_only_mode.py -v`
Expected: PASS (unchanged)

- [ ] **Step 7: Commit**

```bash
git add core/app/configs/pipeline_validation.py core/app/configs/routes.py \
  core/tests/test_pipeline_config_validation.py
git commit -m "feat(core): validate pipeline graph structure at save time, gate on CORE_ETL_ENABLED"
```

---

