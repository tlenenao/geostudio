## Task 5: Per-node validation (`app.pipelines` layer, registered into Task 4)

**Files:**
- Create: `core/app/pipelines/config_validation.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_pipeline_node_validation.py`

**Interfaces:**
- Consumes: `register_pipeline_node_validator` (Task 4), `OP_PARAMS` (Task 3).
- Produces: real per-op validators registered as a side effect of importing
  `app.pipelines.config_validation` — from this task on, `test_pipeline_config_validation.py`'s
  fake validators are no longer the only ones in play for a real app instance
  (the fakes remain fine as unit-test isolation, unaffected).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_pipeline_node_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _pipeline_body(*, reader_collection: str, writer_collection: str) -> dict:
    return {
        "title": "P",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection",
                     "params": {"collectionId": reader_collection}},
                    {"id": "w1", "kind": "writer", "op": "writer.collection",
                     "params": {"collectionId": writer_collection}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('readable', :t, :o, 'readable', 'Readable', '', 'id', NULL, 1, 1)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('writable', :t, :o, 'writable', 'Writable', '', 'id', NULL, 0, 1)"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable) "
            "VALUES ('locked', :t, :o, 'locked', 'Locked', '', 'id', NULL, 0, 0)"
        ), {"t": tenant.id, "o": other.id})
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    return TestClient(app)


def test_valid_pipeline_with_existing_collections_saves(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="writable",
    ))
    assert response.status_code == 201


def test_reader_collection_missing_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="does-not-exist", writer_collection="writable",
    ))
    assert response.status_code == 422
    assert "not found" in response.json()["detail"]


def test_writer_collection_not_editable_is_rejected(env):
    response = env.post("/configs", json=_pipeline_body(
        reader_collection="readable", writer_collection="locked",
    ))
    assert response.status_code == 422


def test_missing_required_param_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["params"] = {}
    response = env.post("/configs", json=body)
    assert response.status_code == 422


def test_unknown_op_is_rejected(env):
    body = _pipeline_body(reader_collection="readable", writer_collection="writable")
    body["config"]["pipeline"]["nodes"][0]["op"] = "reader.does-not-exist"
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "unknown op" in response.json()["detail"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
Expected: FAIL — `test_reader_collection_missing_is_rejected` and others get
`422 unknown op 'reader.collection'` (no real validator registered yet in a
freshly-created app — the fake validators from Task 4's own test file don't
leak across test modules) instead of the specific collection-not-found
message; `test_valid_pipeline_with_existing_collections_saves` fails with 422.

- [ ] **Step 3: Implement the real per-node validators**

Create `core/app/pipelines/config_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registers the real per-op node validators for kind="pipeline" configs
(see app.configs.pipeline_validation for why this indirection exists).
Imported for its side effect by app.main, the only layer allowed to know
about both app.pipelines and app.configs — mirrors
app.collections.dataset_validation exactly.

Boundary decision (design SP-15a, Global Constraints): only param SHAPE
(Pydantic) and referenced-collection existence/permission are checked here,
at save time. Bounded SQL expressions (filter.expr, derive.expr,
aggregate.metrics values) and transform.join.on column existence are only
checked at execution time (app.pipelines.expr_validation / runtime) — a bad
expression fails the run clearly, it never blocks saving the pipeline."""
from fastapi import HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.collections import repository as collections_repo
from app.configs.pipeline_validation import register_pipeline_node_validator
from app.configs.schemas import PipelineNode
from app.pipelines.ops.schemas import OP_PARAMS
from app.sharing.authorization import can
from app.users.models import User

_COLLECTION_PARAM_FIELD = {
    "reader.collection": "collectionId",
    "transform.join": "withCollectionId",
    "writer.collection": "collectionId",
}
_WRITE_OPS = {"writer.collection"}


def _validate_params(node: PipelineNode) -> BaseModel:
    model = OP_PARAMS.get(node.op)
    if model is None:
        raise HTTPException(status_code=422, detail=f"unknown op '{node.op}'")
    try:
        return model.model_validate(node.params)
    except Exception as exc:  # pydantic.ValidationError, reported verbatim
        raise HTTPException(status_code=422, detail=f"{node.op}: {exc}") from exc


def _require_readable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        # Same message as not-found: don't leak collection existence.
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")


def _require_writable_collection(session: Session, *, user: User, collection_id: str) -> None:
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=collection_id,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' not found")
    writable = can(
        session, user_id=user.id, action="write",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not writable or not collection.editable:
        raise HTTPException(status_code=422, detail=f"collection '{collection_id}' is not writable")


def _validate_node(session: Session, node: PipelineNode, user: User) -> None:
    params = _validate_params(node)
    field = _COLLECTION_PARAM_FIELD.get(node.op)
    if field is None:
        return
    collection_id = getattr(params, field)
    if node.op in _WRITE_OPS:
        _require_writable_collection(session, user=user, collection_id=collection_id)
    else:
        _require_readable_collection(session, user=user, collection_id=collection_id)


for _op in OP_PARAMS:
    register_pipeline_node_validator(_op, _validate_node)
```

- [ ] **Step 4: Wire the side-effect import into `app.main`**

In `core/app/main.py`, add right after the existing
`harvest_dataset_validation` import (after line 15):

```python
from app.pipelines import config_validation as pipelines_config_validation  # noqa: F401
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_node_validation.py -v`
Expected: PASS (5 tests green)

- [ ] **Step 6: Run the full pipeline + configs test suite to check no regression**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py tests/test_pipeline_config_schema.py tests/test_pipeline_ops_schemas.py tests/test_configs_extension_permissions.py -v`
Expected: PASS (unchanged)

- [ ] **Step 7: Commit**

```bash
git add core/app/pipelines/config_validation.py core/app/main.py \
  core/tests/test_pipeline_node_validation.py
git commit -m "feat(core): validate pipeline node params + collection permissions at save time"
```

---

