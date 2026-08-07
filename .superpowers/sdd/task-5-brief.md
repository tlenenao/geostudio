### Task 5: `POST /datasets/{id}/arcgis/export` (aggregate mode, arcgis-backed)

**Files:**
- Modify: `core/app/harvest/routes.py`
- Test: `core/tests/test_harvest_dataset_arcgis_export_routes.py` (new)

**Interfaces:**
- Consumes: `rows_to_format`, `EXPORT_MEDIA_TYPES`, `export_filename` (Task 2); `_resolve_arcgis_dataset`, `_groupby_fields`, `_measure_label`, `live_query` (all already present in this file).
- Produces: route `POST /datasets/{item_id}/arcgis/export?format=csv|xlsx`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_harvest_dataset_arcgis_export_routes.py`, mirroring `core/tests/test_harvest_dataset_arcgis_routes.py`'s fixture:

```python
# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from fastapi.testclient import TestClient

from app import db
from app.audit.models import AuditLog
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


def test_export_aggregate_csv_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "features": [{"attributes": {"region": "Nord", "m0": 3}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv",
                        json={"groupBy": "region", "agg": "count"})
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "text/csv; charset=utf-8"
    assert "Nord" in resp.text


def test_export_aggregate_rejects_unknown_format(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    resp = client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=pdf", json={"groupBy": "region"})
    assert resp.status_code == 400


def test_export_aggregate_writes_an_audit_log_row(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"features": [{"attributes": {"region": "Nord", "m0": 3}}]})

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    client.post(f"/datasets/{dataset_item_id}/arcgis/export?format=csv", json={"groupBy": "region", "agg": "count"})
    with client.session_factory() as s:
        rows = s.query(AuditLog).filter_by(action="export.run").all()
    assert len(rows) == 1
    assert rows[0].payload == {"format": "csv", "mode": "aggregate"}
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: FAIL — 404 on every test.

- [ ] **Step 3: Implement**

Edit `core/app/harvest/routes.py`. Add `Response` to the fastapi import and add the export imports:

```python
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
```

```python
from app.analytics.aggregate import AggregateMeasure, AggregateRequestBody
from app.analytics.export import EXPORT_MEDIA_TYPES, export_filename, features_to_format, rows_to_format
```

Add the route after `get_dataset_arcgis_aggregate`'s closing `return {"categoryKey": category_key, "rows": rows}`:

```python
_EXPORT_FORMATS_AGGREGATE = {"csv", "xlsx"}


@router.post("/datasets/{item_id}/arcgis/export")
def export_dataset_arcgis_aggregate(
    item_id: str, body: AggregateRequestBody, format: str = Query(...),
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if format not in _EXPORT_FORMATS_AGGREGATE:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}]},
        )
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
    _category_key, rows = live_query.aggregate_response(raw, group_by=group_by, measures=measures)
    content = rows_to_format(rows, format=format)
    item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    filename = export_filename(item.title if item else item_id, format=format)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="item", object_id=item_id,
                payload={"format": format, "mode": "aggregate"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/routes.py core/tests/test_harvest_dataset_arcgis_export_routes.py
git commit -m "feat(core): SP-16a — POST /datasets/{id}/arcgis/export (mode agrégé CSV/XLSX)"
```

---

