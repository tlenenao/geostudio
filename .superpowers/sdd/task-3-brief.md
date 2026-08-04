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

