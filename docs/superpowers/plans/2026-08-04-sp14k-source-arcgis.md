# SP-14k — Source `arcgis` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a shared `Dataset` reference a live ArcGIS Feature Service layer (already harvested in reference mode by SP-12d) as its source, querying it in real time instead of copying it into a local collection.

**Architecture:** `DatasetPayload` gains `source: "arcgis"` alongside the existing `"collection"`. A new core module `app/harvest/live_query.py` translates the generic filter/bbox/groupBy vocabulary already used by `/collections/{id}/items|aggregate` into ArcGIS REST query params, fetches through the existing SP-12d egress guard, and reshapes the response into the exact same JSON contracts. Two new dataset-scoped routes (`/datasets/{itemId}/arcgis/items|aggregate`) expose this; the shell branches `featuresUrl`/`queryDataSource` to them when a resolved dataset's source is `"arcgis"`. Nothing in `/collections/*` or `/features/*` changes.

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy (core), httpx (egress-guarded), React/TypeScript/React Query (shell), pytest, Vitest, Playwright.

## Global Constraints

- Additive only: no existing `DatasetPayload`/`DatasetConfig` config loses a field or changes meaning; every config with `source: "collection"` (the only value before this plan) behaves byte-identically.
- `bucket`/`split`/`bins` on `POST /datasets/{itemId}/arcgis/aggregate` → HTTP 400, never silently ignored.
- ArcGIS auth stays public-services-only (no token/OAuth) — same posture as the SP-12d connector.
- All outbound HTTP to the ArcGIS service goes through `app.harvest.egress.build_guarded_client()` (or a client built the same way) — no new unguarded egress path.
- New Python files start with `# SPDX-License-Identifier: Apache-2.0`.
- `core/pyproject.toml`'s `[tool.importlinter]` layered-architecture contract must stay green (`app.harvest` may import `app.features`/`app.collections`/`app.configs`/`app.items`/`app.sharing`/`app.users`; those may never import `app.harvest`).
- Shell UI strings in French; identifiers in English.
- Commits: conventional, suffixed `(SP-14k)`.
- The 82+ existing Playwright specs and the full unit suites (core `pytest`, shell `vitest`) stay green throughout — run them at the end of every task, not just once at the end of the plan.

---

### Task 1: Core — `DatasetPayload` gains `source: "arcgis"` + validator registry becomes per-source

**Files:**
- Modify: `core/app/configs/schemas.py`
- Modify: `core/app/configs/dataset_validation.py`
- Modify: `core/app/collections/dataset_validation.py`
- Create: `core/app/harvest/dataset_validation.py`
- Modify: `core/app/main.py`
- Test: `core/tests/test_dataset_config_schema.py`
- Test: `core/tests/test_create_dataset_arcgis.py` (new)

**Interfaces:**
- Produces: `DatasetPayload.source: Literal["collection", "arcgis"]`, `DatasetPayload.arcgisItemId: str | None`, `DatasetPayload.collectionId: str | None` (now optional). `register_dataset_validator(source: str, validator) -> None` (signature changed — now keyed by source). Later tasks (4, 5) call `harvest_repo.get_feature_layer_record` which Task 2 produces; this task only needs it to exist as an import target once Task 2 lands, so Task 1 must run its own tests against a `HarvestRecord` created directly via `harvest_repo.create_record` (already available) rather than via the not-yet-written `get_feature_layer_record`.

- [ ] **Step 1: Write failing pydantic-level tests for the extended `DatasetPayload`**

Append to `core/tests/test_dataset_config_schema.py`:

```python
def test_dataset_config_arcgis_source_valide():
    body = {
        "version": 1, "kind": "dataset",
        "dataset": {"source": "arcgis", "arcgisItemId": "item-1", "columns": {}},
    }
    config = BuilderConfig.model_validate(body)
    assert config.dataset.source == "arcgis"
    assert config.dataset.arcgisItemId == "item-1"
    assert config.dataset.collectionId is None


def test_dataset_config_collection_source_sans_collection_id_rejete():
    body = {"version": 1, "kind": "dataset", "dataset": {"source": "collection", "columns": {}}}
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_dataset_config_arcgis_source_sans_arcgis_item_id_rejete():
    body = {"version": 1, "kind": "dataset", "dataset": {"source": "arcgis", "columns": {}}}
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)


def test_dataset_config_arcgis_source_avec_collection_id_rejete():
    body = {
        "version": 1, "kind": "dataset",
        "dataset": {"source": "arcgis", "arcgisItemId": "item-1", "collectionId": "parcs", "columns": {}},
    }
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(body)
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: the 4 new tests FAIL (`source` doesn't accept `"arcgis"` yet, `collectionId` is still required unconditionally).

- [ ] **Step 3: Extend `DatasetPayload` in `core/app/configs/schemas.py`**

Replace:

```python
class DatasetPayload(BaseModel):
    source: Literal["collection"]  # seul type supporté en SP-14a
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte (SP-14b)
```

with:

```python
class DatasetPayload(BaseModel):
    source: Literal["collection", "arcgis"]
    collectionId: str | None = None    # requis si source == "collection"
    arcgisItemId: str | None = None    # requis si source == "arcgis" (SP-14k) : item "external"
                                        # moissonné en mode référence (SP-12d)
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
    timeField: str | None = None       # colonne consommée par le contexte temporel (SP-14b)
    reactsToExtent: bool = False       # A29 : refetch auto sur déplacement carte (SP-14b)

    @model_validator(mode="after")
    def _require_source_id(self) -> "DatasetPayload":
        if self.source == "collection" and self.collectionId is None:
            raise ValueError("collection source requires collectionId")
        if self.source == "arcgis" and self.arcgisItemId is None:
            raise ValueError("arcgis source requires arcgisItemId")
        if self.source == "collection" and self.arcgisItemId is not None:
            raise ValueError("collection source must not set arcgisItemId")
        if self.source == "arcgis" and self.collectionId is not None:
            raise ValueError("arcgis source must not set collectionId")
        return self
```

`model_validator` is already imported at the top of the file (used by `BuilderConfig._require_kind_payload`).

- [ ] **Step 4: Run to verify pydantic tests pass**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: all tests PASS, including the 8 pre-existing ones (unaffected — they all use `source: "collection"` with `collectionId` set).

- [ ] **Step 5: Make the validator registry per-source**

Replace the full content of `core/app/configs/dataset_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registry hook so app.configs can validate kind="dataset" payloads without
importing app.collections or app.harvest (forbidden by the layered-architecture
contract: both sit above app.configs). Validators are registered per
`DatasetPayload.source` by the modules that own each source's semantics
(app.collections for "collection", app.harvest for "arcgis" — SP-14k);
app.main wires both imports together at startup.
"""
from collections.abc import Callable

from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User

DatasetValidator = Callable[[Session, BuilderConfig, User], None]

_validators: dict[str, DatasetValidator] = {}


def register_dataset_validator(source: str, validator: DatasetValidator) -> None:
    _validators[source] = validator


def validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    payload = config.dataset
    assert payload is not None
    validator = _validators.get(payload.source)
    assert validator is not None, f"no dataset validator registered for source={payload.source!r}"
    validator(session, config, user)
```

- [ ] **Step 6: Update the `"collection"` registration site**

In `core/app/collections/dataset_validation.py`, change the last line:

```python
register_dataset_validator(_validate_dataset_payload)
```

to:

```python
register_dataset_validator("collection", _validate_dataset_payload)
```

- [ ] **Step 7: Run the existing collection-dataset tests to verify nothing broke**

Run: `cd core && uv run pytest tests/test_create_dataset.py -v`
Expected: all 4 pre-existing tests still PASS (registry now keyed by `"collection"`, same validator).

- [ ] **Step 8: Add the `"arcgis"` validator**

Create `core/app/harvest/dataset_validation.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Registers the kind="dataset" validator for source="arcgis" payloads
(SP-14k). Same registry indirection as app.collections.dataset_validation
(see app.configs.dataset_validation for why) — app.main imports this module
for its side effect, alongside app.collections's registration."""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.dataset_validation import register_dataset_validator
from app.configs.schemas import BuilderConfig
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User


def _validate_arcgis_dataset_payload(session: Session, config: BuilderConfig, user: User) -> None:
    payload = config.dataset
    assert payload is not None
    assert payload.arcgisItemId is not None
    record = harvest_repo.get_feature_layer_record(
        session, tenant_id=user.tenant_id, item_id=payload.arcgisItemId,
    )
    if record is None or record.external_url is None:
        raise HTTPException(status_code=422, detail="arcgis layer not found")
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=payload.arcgisItemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        # Même message que la branche introuvable : ne pas révéler l'existence de l'item.
        raise HTTPException(status_code=422, detail="arcgis layer not found")


register_dataset_validator("arcgis", _validate_arcgis_dataset_payload)
```

This imports `harvest_repo.get_feature_layer_record`, written in Task 2. It's fine for this file to exist before that function does — nothing calls `_validate_arcgis_dataset_payload` until Task 1's own new test (Step 10) exercises it, by which point Task 2 must already be merged. **Do Task 2 before running Step 10's test** (or write `get_feature_layer_record` inline now and let Task 2 be a no-op re-verification — the plan assumes Task 2 runs first; if executing strictly in order, come back to Step 10 after Task 2).

- [ ] **Step 9: Wire the import in `app/main.py`**

In `core/app/main.py`, next to:

```python
from app.collections import dataset_validation as collections_dataset_validation  # noqa: F401
```

add:

```python
from app.harvest import dataset_validation as harvest_dataset_validation  # noqa: F401
```

- [ ] **Step 10: Write the HTTP-level test for the arcgis dataset validator**

Create `core/tests/test_create_dataset_arcgis.py` (mirrors `test_create_dataset.py`):

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        alice = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="alice@example.com", first_name="Alice", last_name="Doe",
        )
        bob = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-2",
            username="bob", email="bob@example.com", first_name="Bob", last_name="Doe",
        )
        source = harvest_repo.create_source(
            setup_session, tenant_id=tenant.id, owner_id=alice.id, type="arcgis",
            url="https://gis.example.com/FeatureServer", mode="reference",
            enabled=True, interval_minutes=None,
        )
        visible_item = items_repo.create_item(
            setup_session, tenant_id=tenant.id, owner_id=alice.id,
            resource_type="external", title="Bâtiments",
        )
        harvest_repo.create_record(
            setup_session, tenant_id=tenant.id, source_id=source.id, external_id="layer-0",
            item_id=visible_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
        )
        hidden_item = items_repo.create_item(
            setup_session, tenant_id=tenant.id, owner_id=bob.id,
            resource_type="external", title="Couche privée de Bob",
        )
        harvest_repo.create_record(
            setup_session, tenant_id=tenant.id, source_id=source.id, external_id="layer-1",
            item_id=hidden_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/FeatureServer/1", layer_kind="feature",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.visible_item_id = visible_item.id  # type: ignore[attr-defined]
    test_client.hidden_item_id = hidden_item.id  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _dataset_body(arcgis_item_id: str, title: str = "Bâtiments (live)") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1, "kind": "dataset",
            "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
        },
    }


def test_create_dataset_arcgis_avec_couche_moissonnee_visible(client):
    res = client.post("/configs", json=_dataset_body(client.visible_item_id))
    assert res.status_code == 201, res.text
    item = client.get(f"/items/{res.json()['itemId']}").json()
    assert item["resourceType"] == "dataset"


def test_create_dataset_arcgis_item_inexistant_rejete(client):
    res = client.post("/configs", json=_dataset_body("no-such-item"))
    assert res.status_code == 422
    assert res.json()["detail"] == "arcgis layer not found"


def test_create_dataset_arcgis_couche_non_lisible_rejete_avec_meme_message(client):
    # visible_item appartient à alice, hidden_item à bob (non public, non
    # partagé) : alice ne doit pas pouvoir distinguer "inexistant" de "pas à
    # elle" dans le message d'erreur.
    res = client.post("/configs", json=_dataset_body(client.hidden_item_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "arcgis layer not found"
```

- [ ] **Step 11: Run to verify it fails on the missing repo function**

Run: `cd core && uv run pytest tests/test_create_dataset_arcgis.py -v`
Expected: FAIL with `AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'` — this is expected; Task 2 adds it.

- [ ] **Step 12: Commit (test will go green once Task 2 lands)**

```bash
cd core
git add app/configs/schemas.py app/configs/dataset_validation.py \
  app/collections/dataset_validation.py app/harvest/dataset_validation.py app/main.py \
  tests/test_dataset_config_schema.py tests/test_create_dataset_arcgis.py
git commit -m "feat(core): DatasetPayload gains source=arcgis, per-source validator registry (SP-14k)"
```

---

### Task 2: Core — `harvest_repo.get_feature_layer_record` + `list_feature_layer_records`

**Files:**
- Modify: `core/app/harvest/repository.py`
- Test: `core/tests/test_harvest_repository.py`

**Interfaces:**
- Consumes: `HarvestRecord` model (existing, `core/app/harvest/models.py`).
- Produces: `get_feature_layer_record(session, *, tenant_id: str, item_id: str) -> HarvestRecord | None` (used by Task 1's validator and Task 5's routes). `list_feature_layer_records(session, *, tenant_id: str, q: str | None = None) -> list[Row]` where each row is `(item_id, title, external_url)` (used by Task 3's route).

- [ ] **Step 1: Write failing tests**

Append to `core/tests/test_harvest_repository.py` (open it first to match its existing fixture style — it already has `session`/`tenant` fixtures for this module; use the same pattern as the surrounding tests for `create_record`/`list_layer_records`):

```python
def test_get_feature_layer_record_returns_feature_kind_only(session, tenant):
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id="u1", type="arcgis",
        url="https://gis.example.com/FeatureServer", mode="reference",
        enabled=True, interval_minutes=None,
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="a",
        item_id="item-feature", collection_id=None, content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="b",
        item_id="item-raster", collection_id=None, content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x", layer_kind="raster",
    )
    found = harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="item-feature")
    assert found is not None
    assert found.external_url == "https://gis.example.com/FeatureServer/0"
    assert harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="item-raster") is None
    assert harvest_repo.get_feature_layer_record(session, tenant_id=tenant.id, item_id="no-such-item") is None


def test_list_feature_layer_records_excludes_raster_and_filters_by_q(session, tenant):
    from app.items import repository as items_repo

    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id="u1", type="arcgis",
        url="https://gis.example.com/FeatureServer", mode="reference",
        enabled=True, interval_minutes=None,
    )
    feature_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id="u1", resource_type="external", title="Bâtiments",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="a",
        item_id=feature_item.id, collection_id=None, content_hash=None,
        external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
    )
    raster_item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id="u1", resource_type="external", title="Ortho",
    )
    harvest_repo.create_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="b",
        item_id=raster_item.id, collection_id=None, content_hash=None,
        tiles_url="https://ows.example.com/wms?layer=x", layer_kind="raster",
    )
    session.commit()

    rows = harvest_repo.list_feature_layer_records(session, tenant_id=tenant.id)
    ids = {r[0] for r in rows}
    assert feature_item.id in ids
    assert raster_item.id not in ids

    filtered = harvest_repo.list_feature_layer_records(session, tenant_id=tenant.id, q="zzz-nomatch")
    assert filtered == []
```

If `core/tests/test_harvest_repository.py` does not already have `session`/`tenant` fixtures with those exact names, adapt the two tests above to whatever fixture names the file already uses for an in-memory SQLite session and a seeded tenant (read the file first — do not guess).

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_repository.py -v -k "feature_layer"`
Expected: FAIL with `AttributeError: module 'app.harvest.repository' has no attribute 'get_feature_layer_record'`.

- [ ] **Step 3: Implement both functions**

In `core/app/harvest/repository.py`, add after `list_layer_records`:

```python
def get_feature_layer_record(
    session: Session, *, tenant_id: str, item_id: str,
) -> HarvestRecord | None:
    return session.scalar(
        select(HarvestRecord).where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.item_id == item_id,
            HarvestRecord.layer_kind == "feature",
        )
    )


def list_feature_layer_records(session: Session, *, tenant_id: str, q: str | None = None):
    stmt = (
        select(HarvestRecord.item_id, Item.title, HarvestRecord.external_url)
        .join(Item, Item.id == HarvestRecord.item_id)
        .where(
            HarvestRecord.tenant_id == tenant_id,
            HarvestRecord.layer_kind == "feature",
        )
    )
    if q:
        stmt = stmt.where(Item.title.ilike(f"%{q}%"))
    return list(session.execute(stmt).all())
```

- [ ] **Step 4: Run to verify these tests pass, then re-run Task 1's blocked test**

Run: `cd core && uv run pytest tests/test_harvest_repository.py tests/test_create_dataset_arcgis.py -v`
Expected: all PASS now (Task 1's `test_create_dataset_arcgis.py` was blocked only on `get_feature_layer_record` existing).

- [ ] **Step 5: Run the full core suite to catch regressions**

Run: `cd core && uv run pytest`
Expected: same pass count as before this task, plus the new tests; no `postgis`-marked test count changes (still skipped without Docker).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/repository.py tests/test_harvest_repository.py tests/test_create_dataset_arcgis.py
git commit -m "feat(core): harvest repo gains get/list_feature_layer_record (SP-14k)"
```

---

### Task 3: Core — `GET /harvest/feature-layers`

**Files:**
- Modify: `core/app/harvest/routes.py`
- Test: `core/tests/test_harvest_feature_layers_endpoint.py` (new)

**Interfaces:**
- Consumes: `repo.list_feature_layer_records` (Task 2), `items_repo.get_access_facts`, `can` (both already imported in `routes.py`).
- Produces: `GET /harvest/feature-layers?q=` → `{"layers": [{"id": str, "title": str}]}`. Consumed by the shell in Task 7.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_harvest_feature_layers_endpoint.py` (mirrors `test_harvest_layers_endpoint.py` exactly, swapping raster for feature):

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.users.repository import get_or_create_user


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        from app.tenants.repository import get_or_create_default_tenant
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="r", username="regular",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


class _Seed:
    pass


@pytest.fixture()
def seed(env):
    app, client, Session, admin, regular = env
    seed = _Seed()
    seed.app = app
    seed.client = client

    with Session() as s:
        source = harvest_repo.create_source(
            s, tenant_id=admin.tenant_id, owner_id=admin.id, type="arcgis",
            url="https://gis.example.com/FeatureServer", mode="reference",
            enabled=True, interval_minutes=None,
        )

        visible_item = items_repo.create_item(
            s, tenant_id=admin.tenant_id, owner_id=admin.id,
            resource_type="external", title="Bâtiments visibles",
        )
        harvest_repo.create_record(
            s, tenant_id=admin.tenant_id, source_id=source.id, external_id="a",
            item_id=visible_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/FeatureServer/0", layer_kind="feature",
        )
        seed.visible_feature_item_id = visible_item.id

        raster_item = items_repo.create_item(
            s, tenant_id=admin.tenant_id, owner_id=admin.id,
            resource_type="external", title="Ortho",
        )
        harvest_repo.create_record(
            s, tenant_id=admin.tenant_id, source_id=source.id, external_id="b",
            item_id=raster_item.id, collection_id=None, content_hash=None,
            tiles_url="https://ows.example.com/wms?layer=x", layer_kind="raster",
        )
        seed.raster_item_id = raster_item.id

        hidden_item = items_repo.create_item(
            s, tenant_id=admin.tenant_id, owner_id=regular.id,
            resource_type="external", title="Couche cachée",
        )
        harvest_repo.create_record(
            s, tenant_id=admin.tenant_id, source_id=source.id, external_id="c",
            item_id=hidden_item.id, collection_id=None, content_hash=None,
            external_url="https://gis.example.com/FeatureServer/1", layer_kind="feature",
        )
        seed.hidden_feature_item_id = hidden_item.id

        s.commit()

    _as(app, admin)
    return seed


def test_feature_layers_returns_only_feature_records_of_visible_items(seed):
    resp = seed.client.get("/harvest/feature-layers")
    assert resp.status_code == 200
    layers = resp.json()["layers"]
    ids = {layer["id"] for layer in layers}
    assert seed.visible_feature_item_id in ids
    assert seed.raster_item_id not in ids
    assert seed.hidden_feature_item_id not in ids
    layer = next(layer for layer in layers if layer["id"] == seed.visible_feature_item_id)
    assert layer["title"] == "Bâtiments visibles"
    assert "url" not in layer and "externalUrl" not in layer  # jamais exposé au client


def test_feature_layers_filters_by_q(seed):
    resp = seed.client.get("/harvest/feature-layers", params={"q": "zzz-nomatch"})
    assert resp.status_code == 200
    assert resp.json()["layers"] == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_feature_layers_endpoint.py -v`
Expected: FAIL with 404 (route doesn't exist yet).

- [ ] **Step 3: Add the route**

In `core/app/harvest/routes.py`, add after `list_layers`:

```python
@router.get("/harvest/feature-layers")
def list_feature_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_feature_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, _external_url in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title})
    return {"layers": layers}
```

Note the response deliberately omits `external_url` — the shell picker only needs `id`/`title` to set `arcgisItemId`; the URL stays server-side (never exposed to the browser).

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_feature_layers_endpoint.py -v`
Expected: both tests PASS.

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/routes.py tests/test_harvest_feature_layers_endpoint.py
git commit -m "feat(core): GET /harvest/feature-layers for the SP-14k dataset picker"
```

---

### Task 4: Core — `app/harvest/live_query.py` (pure translation + cache, no HTTP routes yet)

**Files:**
- Create: `core/app/harvest/live_query.py`
- Test: `core/tests/test_harvest_live_query.py` (new)

**Interfaces:**
- Produces (consumed by Task 5):
  - `class ArcgisQueryError(Exception)` with `.field: str`, `.message: str`.
  - `translate_features_query(*, filters: dict[str, str], bbox: tuple[float,float,float,float] | None, limit: int, offset: int) -> dict[str, str]`
  - `translate_aggregate_query(*, group_by: list[str], measures: list[tuple[str, str | None, str]], filters: dict[str, str], bbox: tuple[float,float,float,float] | None) -> dict[str, str]` — `measures` is `(agg, field, label)` triples; raises `ArcgisQueryError` for an unknown `agg` or a non-`count` agg with no field.
  - `fetch_query(client: httpx.Client, external_url: str, params: dict[str, str]) -> dict` — TTL-cached (20s), keyed by `external_url` + sorted params.
  - `aggregate_response(raw: dict, *, group_by: list[str], measures: list[tuple[str, str | None, str]]) -> tuple[str | list[str], list[dict]]`

- [ ] **Step 1: Write the failing unit tests**

Create `core/tests/test_harvest_live_query.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest

from app.harvest import live_query


@pytest.fixture(autouse=True)
def _clear_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def test_translate_features_query_builds_where_from_filters():
    params = live_query.translate_features_query(
        filters={"statut": "actif", "annee__gte": "2020", "annee__lte": "2024", "type__in": "a,b"},
        bbox=None, limit=50, offset=10,
    )
    assert "statut = 'actif'" in params["where"]
    assert "annee >= '2020'" in params["where"]
    assert "annee <= '2024'" in params["where"]
    assert "type IN ('a', 'b')" in params["where"]
    assert params["resultRecordCount"] == "50"
    assert params["resultOffset"] == "10"
    assert params["f"] == "geojson"
    assert params["outFields"] == "*"
    assert "geometry" not in params


def test_translate_features_query_no_filters_is_1_equals_1():
    params = live_query.translate_features_query(filters={}, bbox=None, limit=100, offset=0)
    assert params["where"] == "1=1"


def test_translate_features_query_bbox_adds_envelope_params():
    params = live_query.translate_features_query(
        filters={}, bbox=(1.0, 2.0, 3.0, 4.0), limit=100, offset=0,
    )
    assert params["geometry"] == "1.0,2.0,3.0,4.0"
    assert params["geometryType"] == "esriGeometryEnvelope"
    assert params["inSR"] == "4326"
    assert params["spatialRel"] == "esriSpatialRelIntersects"


def test_translate_features_query_escapes_single_quotes():
    params = live_query.translate_features_query(
        filters={"nom": "l'école"}, bbox=None, limit=10, offset=0,
    )
    assert "l''école" in params["where"]


def test_translate_aggregate_query_count_no_groupby():
    params = live_query.translate_aggregate_query(
        group_by=[], measures=[("count", None, "total")], filters={}, bbox=None,
    )
    assert params["f"] == "json"
    assert "groupByFieldsForStatistics" not in params
    stats = params["outStatistics"]
    assert '"statisticType": "count"' in stats or "'statisticType': 'count'" in stats or "statisticType" in stats


def test_translate_aggregate_query_groupby_single_field():
    params = live_query.translate_aggregate_query(
        group_by=["commune"], measures=[("sum", "population", "total_pop")], filters={}, bbox=None,
    )
    assert params["groupByFieldsForStatistics"] == "commune"


def test_translate_aggregate_query_groupby_multi_field():
    params = live_query.translate_aggregate_query(
        group_by=["commune", "annee"], measures=[("count", None, "n")], filters={}, bbox=None,
    )
    assert params["groupByFieldsForStatistics"] == "commune,annee"


def test_translate_aggregate_query_unknown_agg_raises():
    with pytest.raises(live_query.ArcgisQueryError):
        live_query.translate_aggregate_query(
            group_by=[], measures=[("median", "x", "m")], filters={}, bbox=None,
        )


def test_translate_aggregate_query_non_count_without_field_raises():
    with pytest.raises(live_query.ArcgisQueryError):
        live_query.translate_aggregate_query(
            group_by=[], measures=[("sum", None, "m")], filters={}, bbox=None,
        )


def test_fetch_query_returns_parsed_json():
    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith("https://gis.example.com/FeatureServer/0/query")
        return httpx.Response(200, json={"features": [{"attributes": {"a": 1}}]})
    client = httpx.Client(transport=httpx.MockTransport(handler))
    data = live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert data == {"features": [{"attributes": {"a": 1}}]}


def test_fetch_query_caches_within_ttl(monkeypatch):
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        return httpx.Response(200, json={"features": []})

    client = httpx.Client(transport=httpx.MockTransport(handler))
    clock = {"t": 1000.0}
    monkeypatch.setattr(live_query.time, "monotonic", lambda: clock["t"])

    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert calls["n"] == 1  # deuxième appel servi par le cache

    clock["t"] += live_query._CACHE_TTL_SECONDS + 1
    live_query.fetch_query(client, "https://gis.example.com/FeatureServer/0", {"where": "1=1"})
    assert calls["n"] == 2  # TTL expiré, nouvel appel réseau


def test_aggregate_response_no_groupby_single_row():
    raw = {"features": [{"attributes": {"m0": 42}}]}
    key, rows = live_query.aggregate_response(raw, group_by=[], measures=[("count", None, "total")])
    assert key == "group"
    assert rows == [{"group": "Total", "total": 42}]


def test_aggregate_response_single_groupby_field():
    raw = {"features": [
        {"attributes": {"commune": "Metz", "m0": 3}},
        {"attributes": {"commune": "Nancy", "m0": 7}},
    ]}
    key, rows = live_query.aggregate_response(
        raw, group_by=["commune"], measures=[("count", None, "n")],
    )
    assert key == "commune"
    assert rows == [{"commune": "Metz", "n": 3}, {"commune": "Nancy", "n": 7}]


def test_aggregate_response_multi_groupby_fields():
    raw = {"features": [{"attributes": {"commune": "Metz", "annee": 2020, "m0": 3}}]}
    key, rows = live_query.aggregate_response(
        raw, group_by=["commune", "annee"], measures=[("count", None, "n")],
    )
    assert key == ["commune", "annee"]
    assert rows == [{"commune": "Metz", "annee": 2020, "n": 3}]


def test_aggregate_response_no_features_empty_rows():
    key, rows = live_query.aggregate_response({"features": []}, group_by=[], measures=[("count", None, "n")])
    assert key == "group"
    assert rows == []
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.harvest.live_query'`.

- [ ] **Step 3: Implement `core/app/harvest/live_query.py`**

```python
# SPDX-License-Identifier: Apache-2.0
"""Traduction de requêtes génériques (filtres __gte/__lte/__in, bbox,
pagination, groupBy/mesures) vers l'API REST ArcGIS Feature Service, pour un
dataset source="arcgis" (SP-14k) — lecture live, sans copie locale. Les
requêtes sortantes utilisent le client HTTP injecté par la route appelante
(gardé par le même egress guard que le moissonnage, SP-12d, egress.py)."""
import json
import time
from urllib.parse import urlencode

import httpx

_CACHE_TTL_SECONDS = 20.0
_RANGE_OPS = {"__gte": ">=", "__lte": "<="}
_STAT_TYPES = {"count", "sum", "avg", "min", "max"}

_cache: dict[str, tuple[float, dict]] = {}


class ArcgisQueryError(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _build_where(filters: dict[str, str]) -> str:
    clauses = []
    for raw_name, value in sorted(filters.items()):
        name, suffix = _split_filter_key(raw_name)
        if suffix == "__in":
            values = value.split(",")
            clauses.append(f"{name} IN ({', '.join(_sql_lit(v) for v in values)})")
        elif suffix in _RANGE_OPS:
            clauses.append(f"{name} {_RANGE_OPS[suffix]} {_sql_lit(value)}")
        else:
            clauses.append(f"{name} = {_sql_lit(value)}")
    return " AND ".join(clauses) if clauses else "1=1"


def _bbox_params(bbox: tuple[float, float, float, float] | None) -> dict[str, str]:
    if bbox is None:
        return {}
    minx, miny, maxx, maxy = bbox
    return {
        "geometry": f"{minx},{miny},{maxx},{maxy}",
        "geometryType": "esriGeometryEnvelope",
        "inSR": "4326",
        "spatialRel": "esriSpatialRelIntersects",
    }


def translate_features_query(
    *, filters: dict[str, str], bbox: tuple[float, float, float, float] | None,
    limit: int, offset: int,
) -> dict[str, str]:
    return {
        "where": _build_where(filters),
        "outFields": "*",
        "f": "geojson",
        "resultRecordCount": str(limit),
        "resultOffset": str(offset),
        **_bbox_params(bbox),
    }


def translate_aggregate_query(
    *, group_by: list[str], measures: list[tuple[str, str | None, str]],
    filters: dict[str, str], bbox: tuple[float, float, float, float] | None,
) -> dict[str, str]:
    out_statistics = []
    for i, (agg, field, _label) in enumerate(measures):
        if agg not in _STAT_TYPES:
            raise ArcgisQueryError("agg", f"unknown agg '{agg}'")
        if agg != "count" and field is None:
            raise ArcgisQueryError("field", f"agg '{agg}' requires a field")
        out_statistics.append({
            "statisticType": agg,
            "onStatisticField": field or "1",
            "outStatisticFieldName": f"m{i}",
        })
    params: dict[str, str] = {
        "where": _build_where(filters),
        "outStatistics": json.dumps(out_statistics),
        "f": "json",
        **_bbox_params(bbox),
    }
    if group_by:
        params["groupByFieldsForStatistics"] = ",".join(group_by)
    return params


def _cache_key(external_url: str, params: dict[str, str]) -> str:
    return f"{external_url}?{urlencode(sorted(params.items()))}"


def fetch_query(client: httpx.Client, external_url: str, params: dict[str, str]) -> dict:
    key = _cache_key(external_url, params)
    cached = _cache.get(key)
    if cached is not None:
        expires_at, value = cached
        if time.monotonic() < expires_at:
            return value
        del _cache[key]
    response = client.get(f"{external_url}/query", params=params)
    response.raise_for_status()
    data = response.json()
    _cache[key] = (time.monotonic() + _CACHE_TTL_SECONDS, data)
    return data


def aggregate_response(
    raw: dict, *, group_by: list[str], measures: list[tuple[str, str | None, str]],
) -> tuple[str | list[str], list[dict]]:
    features = raw.get("features", [])
    if not group_by:
        if not features:
            return "group", []
        attrs = features[0].get("attributes", {})
        row = {"group": "Total"}
        for i, (_agg, _field, label) in enumerate(measures):
            row[label] = attrs.get(f"m{i}")
        return "group", [row]
    if len(group_by) == 1:
        field = group_by[0]
        rows = []
        for feat in features:
            attrs = feat.get("attributes", {})
            row: dict = {field: str(attrs.get(field))}
            for i, (_agg, _field, label) in enumerate(measures):
                row[label] = attrs.get(f"m{i}")
            rows.append(row)
        return field, rows
    rows = []
    for feat in features:
        attrs = feat.get("attributes", {})
        row = {f: attrs.get(f) for f in group_by}
        for i, (_agg, _field, label) in enumerate(measures):
            row[label] = attrs.get(f"m{i}")
        rows.append(row)
    return group_by, rows
```

- [ ] **Step 4: Run to verify all tests pass**

Run: `cd core && uv run pytest tests/test_harvest_live_query.py -v`
Expected: all PASS.

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest`
Expected: no regressions.

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/live_query.py tests/test_harvest_live_query.py
git commit -m "feat(core): live_query translates filters/bbox/groupBy to ArcGIS REST (SP-14k)"
```

---

### Task 5: Core — `GET/POST /datasets/{itemId}/arcgis/items|aggregate`

**Files:**
- Modify: `core/app/harvest/routes.py`
- Test: `core/tests/test_harvest_dataset_arcgis_routes.py` (new)

**Interfaces:**
- Consumes: `live_query.translate_features_query`/`translate_aggregate_query`/`fetch_query`/`aggregate_response`/`ArcgisQueryError` (Task 4), `harvest_repo.get_feature_layer_record` (Task 2), `app.configs.repository.get_config_by_item`, `app.analytics.aggregate.AggregateRequestBody`/`AggregateMeasure`, `app.harvest.egress.build_guarded_client`/`EgressBlockedError`.
- Produces: `GET /datasets/{item_id}/arcgis/items` → `{"type": "FeatureCollection", "features": [...], "numberMatched": int, "numberReturned": int, "links": []}`. `POST /datasets/{item_id}/arcgis/aggregate` → `{"categoryKey": str | list[str], "rows": [...]}`. Both consumed by the shell in Task 6.

Deliberate scope note vs. the design doc's exact wording: `numberMatched` is computed as `offset + numberReturned` (no second "count-only" ArcGIS request) rather than a true total. No current shell consumer reads `numberMatched` (`queryDataSource` only reads `.features`) — a second remote round-trip for an unused field would violate YAGNI. `links` is always `[]` for the same reason. If a future sub-part needs real pagination totals for `arcgis` datasets, add the second request then.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_harvest_dataset_arcgis_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import live_query, routes as harvest_routes
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer/0"


@pytest.fixture(autouse=True)
def _clear_cache():
    live_query._cache.clear()
    yield
    live_query._cache.clear()


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="a@example.com", first_name="Alice", last_name="Doe",
        )
        source = harvest_repo.create_source(
            s, tenant_id=tenant.id, owner_id=alice.id, type="arcgis",
            url="https://gis.example.com/arcgis/rest/services/Foo/FeatureServer",
            mode="reference", enabled=True, interval_minutes=None,
        )
        layer_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=alice.id, resource_type="external", title="Bâtiments",
        )
        harvest_repo.create_record(
            s, tenant_id=tenant.id, source_id=source.id, external_id="layer-0",
            item_id=layer_item.id, collection_id=None, content_hash=None,
            external_url=SERVICE, layer_kind="feature",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.layer_item_id = layer_item.id  # type: ignore[attr-defined]
    test_client.alice_id = alice.id  # type: ignore[attr-defined]
    test_client.tenant_id = tenant.id  # type: ignore[attr-defined]
    test_client.session_factory = Session  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_dataset(client, arcgis_item_id: str) -> str:
    res = client.post("/configs", json={
        "title": "Bâtiments (live)",
        "config": {
            "version": 1, "kind": "dataset",
            "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
        },
    })
    assert res.status_code == 201, res.text
    return res.json()["itemId"]


def test_get_items_proxies_to_arcgis_and_reshapes_response(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).startswith(f"{SERVICE}/query")
        assert "where=1%3D1" in str(request.url) or "where=1=1" in str(request.url)
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "id": 1, "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"] == [{"type": "Feature", "id": 1, "properties": {"nom": "X"}, "geometry": None}]
    assert body["numberReturned"] == 1
    assert body["numberMatched"] == 1


def test_get_items_forwards_filters_and_bbox(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        return httpx.Response(200, json={"features": []})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(
        f"/datasets/{dataset_item_id}/arcgis/items",
        params={"statut": "actif", "bbox": "1,2,3,4", "limit": "5", "offset": "0"},
    )
    assert resp.status_code == 200
    assert "statut" in seen["url"]
    assert "geometryType=esriGeometryEnvelope" in seen["url"]
    assert "resultRecordCount=5" in seen["url"]


def test_get_items_unknown_dataset_item_404s(client):
    resp = client.get("/datasets/no-such-item/arcgis/items")
    assert resp.status_code == 404


def test_get_items_egress_blocked_returns_502(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def raising_client():
        from app.harvest.egress import EgressBlockedError

        class _RaisingClient:
            def get(self, *args, **kwargs):
                raise EgressBlockedError("cible interne bloquée")
            def close(self):
                pass
        return _RaisingClient()

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = raising_client
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/items")
    assert resp.status_code == 502


def test_post_aggregate_no_groupby_count(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        assert "outStatistics" in str(request.url)
        return httpx.Response(200, json={"features": [{"attributes": {"m0": 12}}]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/aggregate", json={"agg": "count"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoryKey"] == "group"
    assert body["rows"] == [{"group": "Total", "value": 12}]


def test_post_aggregate_groupby_and_measure(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [
            {"attributes": {"commune": "Metz", "m0": 3}},
            {"attributes": {"commune": "Nancy", "m0": 7}},
        ]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/aggregate", json={
        "groupBy": "commune", "agg": "count",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["categoryKey"] == "commune"
    assert body["rows"] == [{"commune": "Metz", "value": 3}, {"commune": "Nancy", "value": 7}]


def test_post_aggregate_bucket_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/aggregate", json={
        "groupBy": "annee", "bucket": "month",
    })
    assert resp.status_code == 400


def test_post_aggregate_split_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/aggregate", json={
        "groupBy": "annee", "split": "commune",
    })
    assert resp.status_code == 400


def test_post_aggregate_bins_rejected(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/aggregate", json={
        "field": "population", "bins": 10,
    })
    assert resp.status_code == 400


def test_get_items_on_collection_dataset_404s(client):
    # Seed a real, readable collection so the dataset actually gets created
    # (a collection-sourced dataset needs a valid collectionId to pass
    # validation — Task 1) — only then is the arcgis-route rejection real.
    from app.collections.models import Collection

    with client.session_factory() as s:
        s.add(Collection(
            id="parcs", tenant_id=client.tenant_id, owner_id=client.alice_id,
            table_name="parcs", title="Parcs", pk_column="id", is_public=True, editable=True,
        ))
        s.commit()

    res = client.post("/configs", json={
        "title": "Dataset collection",
        "config": {
            "version": 1, "kind": "dataset",
            "dataset": {"source": "collection", "collectionId": "parcs", "columns": {}},
        },
    })
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    resp = client.get(f"/datasets/{item_id}/arcgis/items")
    assert resp.status_code == 404
```

- [ ] **Step 2: Run to verify failure**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_routes.py -v`
Expected: FAIL — `AttributeError: module 'app.harvest.routes' has no attribute 'get_arcgis_http_client'` and 404s (routes don't exist).

- [ ] **Step 3: Add the routes**

In `core/app/harvest/routes.py`, add these imports at the top (alongside the existing ones):

```python
from datetime import datetime, timezone

from fastapi import Query, Request

import httpx

from app.analytics.aggregate import AggregateMeasure, AggregateRequestBody
from app.configs import repository as configs_repo
from app.harvest import live_query
from app.harvest.egress import EgressBlockedError, build_guarded_client
```

Add module constants and the dependency factory near `get_task_deferrer`:

```python
_MAX_LIMIT = 1000


def get_arcgis_http_client():  # overridé en test
    return build_guarded_client()
```

Add the bbox parser and dataset-resolution helper (near `_require_admin`):

```python
def _parse_bbox(raw: str | None) -> tuple[float, float, float, float] | None:
    if raw is None:
        return None
    parts = raw.split(",")
    if len(parts) != 4:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")
    try:
        return tuple(float(p) for p in parts)  # type: ignore[return-value]
    except ValueError:
        raise HTTPException(status_code=400, detail="bbox must be minx,miny,maxx,maxy")


def _resolve_arcgis_dataset(session: Session, *, item_id: str, user: User) -> str:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="dataset not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if (
        config is None or config.kind != "dataset" or config.config.dataset is None
        or config.config.dataset.source != "arcgis"
    ):
        raise HTTPException(status_code=404, detail="dataset not found")
    arcgis_item_id = config.config.dataset.arcgisItemId
    assert arcgis_item_id is not None
    record = repo.get_feature_layer_record(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if record is None or record.external_url is None:
        raise HTTPException(status_code=404, detail="arcgis layer not found")
    layer_facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=arcgis_item_id)
    if layer_facts is None or not can(session, user_id=user.id, action="read", item=layer_facts):
        raise HTTPException(status_code=404, detail="arcgis layer not found")
    return record.external_url


def _groupby_fields(raw: str | list[str] | None) -> list[str]:
    if not raw:
        return []
    return raw if isinstance(raw, list) else [raw]


def _measure_label(m: AggregateMeasure) -> str:
    return m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)
```

Add the two routes at the end of the file:

```python
@router.get("/datasets/{item_id}/arcgis/items")
def get_dataset_arcgis_items(
    item_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0), bbox: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    limit = min(limit, _MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    reserved = {"limit", "offset", "bbox"}
    filters = {k: v for k, v in request.query_params.items() if k not in reserved}
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    params = live_query.translate_features_query(
        filters=filters, bbox=parsed_bbox, limit=limit, offset=offset,
    )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    features = raw.get("features", []) if isinstance(raw, dict) else []
    return {
        "type": "FeatureCollection",
        "features": features,
        "numberMatched": offset + len(features),
        "numberReturned": len(features),
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": [],
    }


@router.post("/datasets/{item_id}/arcgis/aggregate")
def get_dataset_arcgis_aggregate(
    item_id: str, body: AggregateRequestBody,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if body.bucket is not None or body.split is not None or body.bins is not None:
        raise HTTPException(
            status_code=400,
            detail="bucket/split/bins are not supported for arcgis-sourced datasets",
        )
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)
    group_by = _groupby_fields(body.groupBy)
    measures_in = body.measures or [AggregateMeasure(field=body.field, agg=body.agg, label="value")]
    measures = [(m.agg, m.field, _measure_label(m)) for m in measures_in]
    try:
        params = live_query.translate_aggregate_query(
            group_by=group_by, measures=measures, filters=body.filters, bbox=body.bbox,
        )
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_aggregate", "message": exc.message}]},
        )
    try:
        raw = live_query.fetch_query(client, external_url, params)
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()
    category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
    return {"categoryKey": category_key, "rows": rows}
```

Note the top-of-file `import httpx` line — check `core/app/harvest/routes.py` doesn't already import `httpx` under a different alias before adding; if it does, reuse it instead of adding a duplicate import.

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_routes.py -v`
Expected: all tests PASS.

- [ ] **Step 5: Run the full core suite + import-linter**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: full suite green, import-linter reports no broken contracts (`app.harvest` importing `app.configs`/`app.analytics`/`app.features`-adjacent modules is allowed per the layer order).

- [ ] **Step 6: Commit**

```bash
cd core
git add app/harvest/routes.py tests/test_harvest_dataset_arcgis_routes.py
git commit -m "feat(core): GET/POST /datasets/{itemId}/arcgis/items|aggregate live proxy (SP-14k)"
```

---

### Task 6: Shell — types + `itemClient.ts` (dataset source branching)

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Produces: `DatasetConfig` becomes a discriminated union (`source: "collection" | "arcgis"`). `CreateDatasetInput` new discriminated union type. `ItemClient.createDatasetItem(input: CreateDatasetInput)`, `ItemClient.listFeatureLayers(params?: {q?: string}): Promise<FeatureLayerSource[]>` (new), `featuresUrl`/`queryDataSource` transparently route arcgis-backed sources to `/datasets/{arcgisItemId}/arcgis/items|aggregate`. Consumed by Task 7 (hooks/NewItemButton) and Task 8 (DataContext).

- [ ] **Step 1: Write the failing shell tests**

Open `shell/src/api/itemClient.test.ts`, find `makeClient()` at the top (reuse it as-is), and add these tests near the existing `featuresUrl`/`queryDataSource` dataset tests (around line 412-446):

```ts
test("featuresUrl routes an arcgis-sourced dataset to /datasets/{arcgisItemId}/arcgis/items", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-1", () =>
      HttpResponse.json({
        id: "cfg-arc1", itemId: "ds-arcgis-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-9", columns: {} } },
      }),
    ),
  );
  const client = makeClient();
  await client.getDatasetConfig("ds-arcgis-1"); // warms the cache
  expect(
    client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-arcgis-1", query: {} }),
  ).toBe("https://core.test/datasets/layer-9/arcgis/items");
});

test("queryDataSource fetches features from the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-2", () =>
      HttpResponse.json({
        id: "cfg-arc2", itemId: "ds-arcgis-2", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-10", columns: {} } },
      }),
    ),
    http.get("https://core.test/datasets/layer-10/arcgis/items", () =>
      HttpResponse.json({ type: "FeatureCollection", features: [{ id: 1, properties: { nom: "Bât" } }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-arcgis-2", query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Bât" }, geometry: undefined }]);
});

test("queryDataSource posts aggregate queries to the arcgis proxy for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-3", () =>
      HttpResponse.json({
        id: "cfg-arc3", itemId: "ds-arcgis-3", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-11", columns: {} } },
      }),
    ),
    http.post("https://core.test/datasets/layer-11/arcgis/aggregate", () =>
      HttpResponse.json({ categoryKey: "group", rows: [{ group: "Total", value: 4 }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "statistics", service: "core", layer: "", datasetId: "ds-arcgis-3", query: { agg: "count" },
  });
  expect(records).toEqual([{ id: "Total", properties: { group: "Total", value: 4 } }]);
});

test("getDatasetConfig returns an arcgis-shaped DatasetConfig for an arcgis-sourced dataset", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-arcgis-4", () =>
      HttpResponse.json({
        id: "cfg-arc4", itemId: "ds-arcgis-4", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-12", columns: {} } },
      }),
    ),
  );
  const config = await makeClient().getDatasetConfig("ds-arcgis-4");
  expect(config).toMatchObject({ source: "arcgis", arcgisItemId: "layer-12" });
});

test("createDatasetItem with source=arcgis posts an arcgis dataset payload", async () => {
  let postBody: Record<string, unknown> | null = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      postBody = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json({ id: "cfg-9", kind: "dataset", itemId: "ds-9" });
    }),
  );
  const item = await makeClient().createDatasetItem({
    title: "Bâtiments (live)", owner: "alice", source: "arcgis", arcgisItemId: "layer-13",
  });
  expect(item.pk).toBe("ds-9");
  const config = postBody!.config as Record<string, unknown>;
  expect(config.dataset).toEqual({ source: "arcgis", arcgisItemId: "layer-13", columns: {} });
});

test("listFeatureLayers fetches /harvest/feature-layers", async () => {
  server.use(
    http.get("https://core.test/harvest/feature-layers", () =>
      HttpResponse.json({ layers: [{ id: "layer-1", title: "Bâtiments" }] }),
    ),
  );
  const layers = await makeClient().listFeatureLayers();
  expect(layers).toEqual([{ id: "layer-1", title: "Bâtiments" }]);
});
```

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `DatasetConfig`/`createDatasetItem` don't accept `source: "arcgis"` yet, `listFeatureLayers` doesn't exist, `featuresUrl`/`queryDataSource` don't branch.

- [ ] **Step 3: Update `shell/src/api/types.ts`**

Replace:

```ts
export type DatasetConfig = {
  source: "collection";
  collectionId: string;
  columns: Record<string, DatasetColumnMeta>;
  timeField?: string | null;
  reactsToExtent?: boolean;
};
```

with:

```ts
export type DatasetConfig =
  | {
      source: "collection";
      collectionId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
    }
  | {
      source: "arcgis";
      arcgisItemId: string;
      columns: Record<string, DatasetColumnMeta>;
      timeField?: string | null;
      reactsToExtent?: boolean;
    };

export type FeatureLayerSource = { id: string; title: string };

export type CreateDatasetInput =
  | { title: string; owner: string; source: "collection"; collectionId: string }
  | { title: string; owner: string; source: "arcgis"; arcgisItemId: string };
```

In the `ItemClient` interface, replace:

```ts
  createDatasetItem(input: { title: string; owner: string; collectionId: string }): Promise<Item>;
```

with:

```ts
  createDatasetItem(input: CreateDatasetInput): Promise<Item>;
  listFeatureLayers(params?: { q?: string }): Promise<FeatureLayerSource[]>;
```

- [ ] **Step 4: Update `shell/src/api/itemClient.ts`**

Replace the `ResolvedDataset` type and `resolveDataset` function:

```ts
  type ResolvedDataset = {
    source: "collection"; collectionId: string; columns: Record<string, DatasetColumnMeta>;
    timeField: string | null; reactsToExtent: boolean;
  };
```

with:

```ts
  type ResolvedDataset = {
    source: "collection" | "arcgis";
    collectionId: string | null;
    arcgisItemId: string | null;
    columns: Record<string, DatasetColumnMeta>;
    timeField: string | null;
    reactsToExtent: boolean;
  };
```

Replace the body of `resolveDataset`:

```ts
  async function resolveDataset(pk: string): Promise<ResolvedDataset> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: {
        dataset?: {
          source: "collection" | "arcgis";
          collectionId?: string | null; arcgisItemId?: string | null;
          columns?: Record<string, DatasetColumnMeta>;
          timeField?: string | null; reactsToExtent?: boolean;
        } | null;
      };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved: ResolvedDataset = {
      source: dataset.source,
      collectionId: dataset.collectionId ?? null,
      arcgisItemId: dataset.arcgisItemId ?? null,
      columns: dataset.columns ?? {}, timeField: dataset.timeField ?? null,
      reactsToExtent: dataset.reactsToExtent ?? false,
    };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

Replace `buildFeaturesUrl` (module-level, above `createItemClient`) with a shared query-string helper plus two URL builders:

```ts
function _queryParams(query: Record<string, unknown>): string {
  const params = new URLSearchParams();
  for (const [k, v] of Object.entries(query).sort(([a], [b]) => a.localeCompare(b))) {
    if (STAT_KEYS.has(k)) continue;
    if (v === null || v === undefined || v === "") continue;
    if (typeof v === "string" || typeof v === "number" || typeof v === "boolean") {
      params.set(k, String(v));
    }
  }
  return params.toString();
}

function buildFeaturesUrl(coreUrl: string, source: DataSource): string {
  const base = `${coreUrl}/collections/${source.layer}/items`;
  const qs = _queryParams(source.query);
  return qs ? `${base}?${qs}` : base;
}

function buildArcgisItemsUrl(coreUrl: string, arcgisItemId: string, query: Record<string, unknown>): string {
  const base = `${coreUrl}/datasets/${arcgisItemId}/arcgis/items`;
  const qs = _queryParams(query);
  return qs ? `${base}?${qs}` : base;
}
```

Inside `createItemClient`, add a shared feature-fetch helper next to `resolveDataset` (needs `getToken` from the enclosing closure):

```ts
  async function _fetchGeoJsonFeatures(url: string): Promise<DataRecord[]> {
    const token = getToken();
    const res = await fetch(url, { headers: token ? { Authorization: `Bearer ${token}` } : {} });
    if (!res.ok) throw new Error(`Request failed: ${res.status} features`);
    const data = (await res.json()) as {
      features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
    };
    return (data.features ?? []).map((f, i) => ({ id: f.id ?? i, properties: f.properties ?? {}, geometry: f.geometry }));
  }
```

Replace `featuresUrl` in the returned object:

```ts
    featuresUrl(source: DataSource): string {
      if (source.datasetId) {
        const cached = datasetCache.get(source.datasetId);
        if (cached?.source === "arcgis" && cached.arcgisItemId) {
          return buildArcgisItemsUrl(coreUrl, cached.arcgisItemId, source.query);
        }
        return buildFeaturesUrl(coreUrl, { ...source, layer: cached?.collectionId ?? source.layer });
      }
      return buildFeaturesUrl(coreUrl, source);
    },
```

Replace `queryDataSource`:

```ts
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      const cachedDataset = source.datasetId ? await resolveDataset(source.datasetId) : null;
      if (cachedDataset?.source === "arcgis" && cachedDataset.arcgisItemId) {
        if (source.type === "statistics") {
          const body = buildAggregateBody(source.query);
          const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
            "POST", `/datasets/${cachedDataset.arcgisItemId}/arcgis/aggregate`, body,
          );
          return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
        }
        return _fetchGeoJsonFeatures(buildArcgisItemsUrl(coreUrl, cachedDataset.arcgisItemId, source.query));
      }
      const resolved = source.datasetId
        ? { ...source, layer: cachedDataset?.collectionId ?? source.layer }
        : source;
      if (resolved.type === "static") {
        return (resolved.query.records as DataRecord[] | undefined) ?? [];
      }
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{ categoryKey: string | string[]; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${resolved.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: statRowId(row, data.categoryKey), properties: row }));
      }
      return _fetchGeoJsonFeatures(buildFeaturesUrl(coreUrl, resolved));
    },
```

Replace `createDatasetItem`:

```ts
    async createDatasetItem(input: CreateDatasetInput): Promise<Item> {
      const dataset: DatasetConfig =
        input.source === "arcgis"
          ? { source: "arcgis", arcgisItemId: input.arcgisItemId, columns: {} }
          : { source: "collection", collectionId: input.collectionId, columns: {} };
      const config = { version: 1, kind: "dataset", dataset };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createDatasetItem: core returned no itemId");
      datasetCache.set(String(data.itemId), {
        source: dataset.source,
        collectionId: dataset.source === "collection" ? dataset.collectionId : null,
        arcgisItemId: dataset.source === "arcgis" ? dataset.arcgisItemId : null,
        columns: {}, timeField: null, reactsToExtent: false,
      });
      return {
        pk: String(data.itemId), resourceType: "dataset", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },
```

Replace `getDatasetConfig`/`saveDatasetConfig`:

```ts
    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      if (resolved.source === "arcgis" && resolved.arcgisItemId) {
        return {
          source: "arcgis", arcgisItemId: resolved.arcgisItemId, columns: resolved.columns,
          timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
        };
      }
      return {
        source: "collection", collectionId: resolved.collectionId ?? "", columns: resolved.columns,
        timeField: resolved.timeField, reactsToExtent: resolved.reactsToExtent,
      };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, {
        source: config.source,
        collectionId: config.source === "collection" ? config.collectionId : null,
        arcgisItemId: config.source === "arcgis" ? config.arcgisItemId : null,
        columns: config.columns, timeField: config.timeField ?? null,
        reactsToExtent: config.reactsToExtent ?? false,
      });
    },
```

Add `listFeatureLayers` near `listLayerSources`/`fetchExternalRasterSources`:

```ts
    async listFeatureLayers(params: { q?: string } = {}): Promise<FeatureLayerSource[]> {
      const token = getToken();
      const query = params.q ? `?q=${encodeURIComponent(params.q)}` : "";
      const res = await fetch(`${coreUrl}/harvest/feature-layers${query}`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} /harvest/feature-layers`);
      const data = (await res.json()) as { layers?: FeatureLayerSource[] };
      return data.layers ?? [];
    },
```

Update the import line at the top of the file to add `CreateDatasetInput` and `FeatureLayerSource` to the destructured type import from `"./types"`.

- [ ] **Step 5: Run to verify tests pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: all tests PASS, including the pre-existing collection-dataset ones (unaffected — same behavior, just routed through the now-shared `_queryParams`/`_fetchGeoJsonFeatures` helpers).

- [ ] **Step 6: Typecheck and run the full unit suite**

Run: `cd shell && npm run build && npx vitest run`
Expected: `tsc --noEmit` clean, full Vitest suite green (398+ tests, some new).

- [ ] **Step 7: Commit**

```bash
cd shell
git add src/api/types.ts src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient routes arcgis-sourced datasets to the live proxy (SP-14k)"
```

---

### Task 7: Shell — `useFeatureLayers` hook + `NewItemButton` arcgis creation flow

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx`

**Interfaces:**
- Consumes: `client.listFeatureLayers` (Task 6), `client.createDatasetItem` (Task 6, now takes `CreateDatasetInput`).
- Produces: `useFeatureLayers(options?: {enabled?: boolean; q?: string})` React Query hook.

- [ ] **Step 1: Add `useFeatureLayers` and widen `useCreateDataset`'s input type**

In `shell/src/api/hooks.ts`, add near `useLayerSources`:

```ts
export function useFeatureLayers(options?: { enabled?: boolean; q?: string }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["feature-layers", options?.q ?? ""],
    queryFn: () => client.listFeatureLayers({ q: options?.q }),
    enabled: options?.enabled ?? true,
  });
}
```

Replace `useCreateDataset`'s `mutationFn` type — since `client.createDatasetItem` now takes `CreateDatasetInput` (Task 6), the hook needs no signature change beyond letting TypeScript infer it; open the file and confirm `mutationFn: (input: { title: string; owner: string; collectionId: string }) => client.createDatasetItem(input)` — replace that explicit input type with `CreateDatasetInput` (import it from `../api/types` at the top of the file):

```ts
export function useCreateDataset() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateDatasetInput) => client.createDatasetItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
```

- [ ] **Step 2: Write the failing `NewItemButton` test**

Open `shell/src/shell/NewItemButton.test.tsx` to see the existing mock-client pattern for `kind: "dataset"` creation (it exists already, since collection-dataset creation is tested there). Add a test that mirrors it for the arcgis path — the exact mock-client shape depends on what's already in the file; add:

```tsx
test("creates an arcgis-sourced dataset from a feature-layer picker", async () => {
  const client = makeMockClient({
    listFeatureLayers: vi.fn().mockResolvedValue([{ id: "layer-1", title: "Bâtiments" }]),
    createDatasetItem: vi.fn().mockResolvedValue({
      pk: "ds-1", resourceType: "dataset", title: "Bâtiments (live)", abstract: "",
      owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-1", isPublished: false,
    }),
  });
  renderWithClient(<NewItemButton />, client);

  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await userEvent.selectOptions(screen.getByLabelText("Type de source"), "arcgis");
  await userEvent.selectOptions(await screen.findByLabelText("Couche ArcGIS"), "layer-1");
  await userEvent.type(screen.getByLabelText("Titre"), "Bâtiments (live)");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));

  expect(client.createDatasetItem).toHaveBeenCalledWith({
    title: "Bâtiments (live)", owner: "alice", source: "arcgis", arcgisItemId: "layer-1",
  });
});
```

Adapt `makeMockClient`/`renderWithClient`/import names to whatever helpers the existing file already defines or imports (read the file first — do not guess the harness).

- [ ] **Step 3: Run to verify failure**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: FAIL — no "Type de source"/"Couche ArcGIS" controls exist yet.

- [ ] **Step 4: Update `NewItemButton.tsx`**

Add imports: `useFeatureLayers` from `"../api/hooks"`, `CreateDatasetInput` type isn't needed directly (inferred).

Add state:

```ts
  const [datasetSource, setDatasetSource] = useState<"collection" | "arcgis">("collection");
  const [arcgisItemId, setArcgisItemId] = useState("");
```

Update `collectionsQuery` to also gate on `datasetSource === "collection"`, and add a parallel query:

```ts
  const collectionsQuery = useCollectionsAdmin({ enabled: open && kind === "dataset" && datasetSource === "collection" });
  const featureLayersQuery = useFeatureLayers({ enabled: open && kind === "dataset" && datasetSource === "arcgis" });
```

Update `close()` to also reset the new state:

```ts
    setCollectionId("");
    setDatasetSource("collection");
    setArcgisItemId("");
```

Update the dataset-creation branch in `submit`:

```ts
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : kind === "dataset"
            ? await createDataset.mutateAsync(
                datasetSource === "arcgis"
                  ? { title: clean, owner: username ?? "", source: "arcgis", arcgisItemId }
                  : { title: clean, owner: username ?? "", source: "collection", collectionId },
              )
            : await create.mutateAsync({
                kind,
                title: clean,
                owner: username ?? "",
                templateId: templateId || undefined,
                slug: kind === "site" ? slug : undefined,
              });
```

Update the submit guard:

```ts
    if (kind === "dataset" && datasetSource === "collection" && !collectionId) return;
    if (kind === "dataset" && datasetSource === "arcgis" && !arcgisItemId) return;
```

(replacing the old `if (kind === "dataset" && !collectionId) return;`)

Replace the `{kind === "dataset" && (...)}` collection-picker block with a source-type selector plus both pickers:

```tsx
          {kind === "dataset" && (
            <label className="flex flex-col gap-1 text-sm">
              Type de source
              <select
                aria-label="Type de source"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={datasetSource}
                onChange={(e) => setDatasetSource(e.target.value as "collection" | "arcgis")}
              >
                <option value="collection">Collection</option>
                <option value="arcgis">ArcGIS Feature Service</option>
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "collection" && (
            <label className="flex flex-col gap-1 text-sm">
              Collection source
              <select
                aria-label="Collection source"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={collectionId}
                onChange={(e) => setCollectionId(e.target.value)}
              >
                <option value="">Choisir…</option>
                {(collectionsQuery.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.title}</option>
                ))}
              </select>
            </label>
          )}
          {kind === "dataset" && datasetSource === "arcgis" && (
            <label className="flex flex-col gap-1 text-sm">
              Couche ArcGIS
              <select
                aria-label="Couche ArcGIS"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={arcgisItemId}
                onChange={(e) => setArcgisItemId(e.target.value)}
              >
                <option value="">Choisir…</option>
                {(featureLayersQuery.data ?? []).map((l) => (
                  <option key={l.id} value={l.id}>{l.title}</option>
                ))}
              </select>
              {featureLayersQuery.data?.length === 0 && (
                <span className="text-xs text-slate-500">
                  Aucune couche moissonnée. Configurez une source de moissonnage ArcGIS
                  (mode référence) dans l'administration.
                </span>
              )}
            </label>
          )}
```

Update the submit-button `disabled` expression:

```ts
              disabled={
                create.isPending || createMap.isPending || createDataset.isPending ||
                (kind === "site" && !isValidSlug(slug)) ||
                (kind === "dataset" && datasetSource === "collection" && !collectionId) ||
                (kind === "dataset" && datasetSource === "arcgis" && !arcgisItemId)
              }
```

- [ ] **Step 5: Run to verify tests pass**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: all tests PASS, including pre-existing ones (the collection path is unchanged in behavior, just gated by `datasetSource === "collection"` which defaults to `"collection"`).

- [ ] **Step 6: Full unit suite + typecheck**

Run: `cd shell && npm run build && npx vitest run`
Expected: green.

- [ ] **Step 7: Commit**

```bash
cd shell
git add src/api/hooks.ts src/shell/NewItemButton.tsx src/shell/NewItemButton.test.tsx
git commit -m "feat(shell): create arcgis-sourced datasets from a harvested feature-layer picker (SP-14k)"
```

---

### Task 8: Shell — `DataContext.tsx` pk resolution stays safe for arcgis-sourced datasets

**Files:**
- Modify: `shell/src/builder/DataContext.tsx`
- Test: `shell/src/builder/DataContext.test.tsx`

**Interfaces:**
- Consumes: `DatasetConfig` discriminated union (Task 6).
- Produces: no new exports; `pkColumn` on `DataSourceState` is `undefined` for arcgis-sourced datasets instead of the provider crashing.

Why this task exists: `DataProvider` currently does `client.getCollectionSchema(dataset.collectionId)` for every distinct `dataset.collectionId` across all datasets referenced by the app's sources (`core/../DataContext.tsx:39-47` before this change). `DatasetConfig.collectionId` is only present when `source === "collection"`; for an arcgis-sourced dataset it's absent, which would either crash the schema fetch or (worse) silently pass `undefined` as a collection id. Fixed by deriving `collectionIds` only from collection-sourced datasets. This means table-row cross-filter-by-pk (SP-14b) does not extend to arcgis-sourced datasets in this plan — only chart-category cross-filter and the time/bbox context (which don't need a pk) do. That's a deliberate, disclosed scope line, not a bug: nothing in the SP-14k spec's E2E acceptance (table display + aggregate widget) requires row-click cross-filter.

- [ ] **Step 1: Write the failing test**

Open `shell/src/builder/DataContext.test.tsx` to find its existing mock-client/render harness (it must already test the `pkByCollection` derivation for collection-sourced datasets — mirror that setup). Add:

```tsx
test("does not crash and leaves pkColumn undefined for an arcgis-sourced dataset", async () => {
  const client = makeMockClient({
    getDatasetConfig: vi.fn().mockResolvedValue({ source: "arcgis", arcgisItemId: "layer-1", columns: {} }),
    getCollectionSchema: vi.fn(), // ne doit jamais être appelé pour ce dataset
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "X" } }]),
  });
  const sources = [{ id: "s1", type: "features" as const, service: "core", layer: "", datasetId: "ds-arcgis", query: {} }];
  const states = await renderDataProvider(sources, client); // adapte au harness existant du fichier

  expect(client.getCollectionSchema).not.toHaveBeenCalled();
  expect(states["s1"].pkColumn).toBeUndefined();
  expect(states["s1"].records).toEqual([{ id: 1, properties: { nom: "X" } }]);
});
```

Adapt the mock/render helper names to whatever the existing file already provides — read it first.

- [ ] **Step 2: Run to verify failure**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: FAIL (`getCollectionSchema` called with `undefined`, or a thrown error, depending on the mock client's strictness).

- [ ] **Step 3: Fix the derivation**

In `shell/src/builder/DataContext.tsx`, replace:

```ts
  const collectionIds = [...new Set(Object.values(datasets).map((d) => d.collectionId))];
```

with:

```ts
  const collectionIds = [...new Set(
    Object.values(datasets)
      .filter((d): d is Extract<DatasetConfig, { source: "collection" }> => d.source === "collection")
      .map((d) => d.collectionId),
  )];
```

And replace the `pkColumn` line in the `states` construction:

```ts
      pkColumn: dataset ? pkByCollection[dataset.collectionId] : undefined,
```

with:

```ts
      pkColumn: dataset && dataset.source === "collection" ? pkByCollection[dataset.collectionId] : undefined,
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/DataContext.test.tsx`
Expected: all PASS, including pre-existing collection-sourced tests.

- [ ] **Step 5: Full unit suite + typecheck**

Run: `cd shell && npm run build && npx vitest run`
Expected: green.

- [ ] **Step 6: Commit**

```bash
cd shell
git add src/builder/DataContext.tsx src/builder/DataContext.test.tsx
git commit -m "fix(shell): DataContext skips collection-schema fetch for arcgis-sourced datasets (SP-14k)"
```

---

### Task 9: E2E — create an arcgis dataset from a harvested layer, consume it in an app

**Files:**
- Create: `shell/e2e/dataset-arcgis.spec.ts`

**Interfaces:**
- Consumes: everything from Tasks 1-8. Like every other spec in `shell/e2e/`, this mocks the **core HTTP API** via `page.route()` (see `mockCore` in `shell/e2e/mocks.ts`) — it never talks to a real core process or a real ArcGIS service. It proves the shell wiring (Task 6/7/8), not the Python routes (already covered by Task 5's `pytest` suite).

This test reuses two established idioms from `shell/e2e/datasets-shared.spec.ts` and `shell/e2e/analytics-context.spec.ts`: (1) override `**/configs` POST with a body-sniffing handler that `route.fallback()`s to `mockCore`'s default for anything that isn't the payload this test cares about; (2) `DataSourceSelect`'s "Datasets partagés" `<optgroup>` (`shell/src/builder/DataSourceSelect.tsx`) is how a widget binds to an *existing* shared dataset — reading `**/items*` filtered to `type=dataset` in JS (not in the route glob: Playwright glob `?` is a single-character wildcard, not a literal query-string separator, so `**/items?type=dataset*` would NOT reliably match — parse `route.request().url()` instead, matching the pattern `harvest-arcgis.spec.ts` already uses for `https://core.test/items*`).

- [ ] **Step 1: Write the spec**

Create `shell/e2e/dataset-arcgis.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create an arcgis-sourced dataset from a harvested layer, consume it live in an app", async ({ page }) => {
  await mockCore(page);

  await page.route("**/harvest/feature-layers*", async (route) => {
    await route.fulfill({ json: { layers: [{ id: "layer-1", title: "Bâtiments" }] } });
  });

  let datasetCreated: Record<string, unknown> | null = null;
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      datasetCreated = body.config.dataset;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    return route.fallback();
  });

  await page.route("**/configs/by-item/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "arcgis", arcgisItemId: "layer-1", columns: {} } },
      },
    });
  });

  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: {
        pk: "dataset-1", resourceType: "dataset", title: "Bâtiments (live)", abstract: "",
        owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset",
        isPublished: false, keywords: [],
      },
    });
  });

  // DataSourceSelect liste les datasets partagés via useItems({type:"dataset"}) :
  // on sniffe le query param en JS plutôt que dans le glob (le "?" d'un glob
  // Playwright est un joker un-caractère, pas le séparateur littéral "?query").
  await page.route("**/items*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "dataset") return route.fallback();
    await route.fulfill({
      json: {
        items: [{
          pk: "dataset-1", resourceType: "dataset", title: "Bâtiments (live)", abstract: "",
          owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset",
          isPublished: false,
        }],
        total: 1, page: 1, pageSize: 100,
      },
    });
  });

  await page.route("**/datasets/layer-1/arcgis/items*", async (route) => {
    await route.fulfill({
      json: {
        type: "FeatureCollection",
        features: [{ type: "Feature", id: 1, properties: { nom: "Bâtiment A" }, geometry: null }],
        numberMatched: 1, numberReturned: 1, links: [],
      },
    });
  });

  await page.route("**/datasets/layer-1/arcgis/aggregate", async (route) => {
    await route.fulfill({ json: { categoryKey: "group", rows: [{ group: "Total", value: 1 }] } });
  });

  // 1. Créer le dataset partagé "arcgis" depuis le catalogue, à partir de la
  //    couche déjà moissonnée en mode référence (layer-1, mockée ci-dessus —
  //    le flux de moissonnage lui-même est couvert par harvest-arcgis.spec.ts).
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Type de source").selectOption("arcgis");
  await dialog.getByLabel("Couche ArcGIS").selectOption("layer-1");
  await dialog.getByLabel("Titre").fill("Bâtiments (live)");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  expect(datasetCreated).toEqual({ source: "arcgis", arcgisItemId: "layer-1", columns: {} });

  // 2. Construire une app : Table + Indicateur, tous deux liés au dataset
  //    partagé existant via l'optgroup "Datasets partagés" de DataSourceSelect
  //    — jamais en saisissant une collection, il n'y en a pas pour ce dataset.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Bâtiments live");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Table" }).click();
  await page.getByLabel("Source de données").selectOption("dataset:dataset-1");

  await page.getByRole("button", { name: "Indicateur" }).click();
  // Le dataset est déjà lié (via la Table) : il apparaît désormais comme une
  // source existante (index 1), plus dans l'optgroup "Datasets partagés".
  await page.getByLabel("Source de données").last().selectOption({ index: 1 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 3. Runtime : la table affiche les entités live, l'indicateur l'agrégat live
  //    — tous deux via le proxy /datasets/layer-1/arcgis/*, jamais /collections/*.
  await page.goto("/apps/9");
  await expect(page.getByRole("cell", { name: "Bâtiment A" })).toBeVisible();
  await expect(page.getByText("1")).toBeVisible();
});
```

- [ ] **Step 2: Run it in isolation**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test e2e/dataset-arcgis.spec.ts`
Expected: PASS. If the "Source de données" `.last()` selection or the dialog re-use trips up (e.g. because `NewItemButton`'s dialog closes/reopens and Playwright needs a fresh locator), adjust to match exactly how `datasets-shared.spec.ts` and `analytics-context.spec.ts` re-open the same dialog across two creations in one test — don't invent a different pattern.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npm run e2e`
Expected: all specs green (82 existing + 1 new = 83), no regressions. If anything flakes, re-run once (per SP-14j's precedent in `.superpowers/sdd/progress.md`) before treating it as a real failure.

- [ ] **Step 4: Commit**

```bash
cd shell
git add e2e/dataset-arcgis.spec.ts
git commit -m "test(e2e): couvre le flux dataset arcgis — picker, table, indicateur live (SP-14k)"
```

---

## Final Checklist (run once, after Task 9)

- [ ] `cd core && uv run pytest` — full suite green.
- [ ] `cd core && uv run lint-imports` — layered-architecture contract green.
- [ ] `cd shell && npm run build` — `tsc --noEmit` + vite build clean.
- [ ] `cd shell && npx vitest run` — full unit suite green.
- [ ] `cd shell && npm run e2e` — full Playwright suite green (run twice if anything flakes, per SP-14j's precedent, before concluding it's a real regression).
- [ ] Update `.superpowers/sdd/progress.md` per this repo's established ledger convention (see the SP-14j entry for the expected shape) once all tasks are reviewed.
