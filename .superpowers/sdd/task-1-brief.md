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

