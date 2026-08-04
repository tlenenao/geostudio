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

