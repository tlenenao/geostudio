### Task 6: `GET /datasets/{id}/arcgis/export/items` (raw-entities mode, arcgis-backed)

**Files:**
- Modify: `core/app/harvest/routes.py`
- Modify: `core/tests/test_harvest_dataset_arcgis_export_routes.py` (append)

**Interfaces:**
- Consumes: `features_to_format` (Task 2), `open_spatial_connection` (Task 1), `translate_features_query`, `fetch_query`, `_parse_bbox`, `_resolve_arcgis_dataset` (already present).
- Produces: route `GET /datasets/{item_id}/arcgis/export/items?format=csv|xlsx|geojson|gpkg`.

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_harvest_dataset_arcgis_export_routes.py`:

```python
def test_export_items_geojson_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    body = resp.json()
    assert body["features"][0]["properties"]["nom"] == "X"


def test_export_items_gpkg_from_arcgis_dataset(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"},
                          "geometry": {"type": "Point", "coordinates": [1.0, 2.0]}}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_stops_paginating_on_a_short_page(client):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}],
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 200
    assert len(calls) == 1  # one page returned fewer rows than the page size — loop stops


def test_export_items_caps_at_10000_entities(client, monkeypatch):
    dataset_item_id = _create_dataset(client, client.layer_item_id)
    monkeypatch.setattr(harvest_routes, "_EXPORT_ITEMS_CAP", 1)

    def handler(request: httpx.Request) -> httpx.Response:
        # Always return a full page (limit=1000) so the loop keeps paginating
        # until the (monkeypatched) cap trips.
        return httpx.Response(200, json={
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {"nom": "X"}, "geometry": None}] * 1000,
        })

    client.app.dependency_overrides[harvest_routes.get_arcgis_http_client] = lambda: _mock_client(handler)
    resp = client.get(f"/datasets/{dataset_item_id}/arcgis/export/items?format=geojson")
    assert resp.status_code == 413
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -k items -v`
Expected: FAIL — 404 on every new test.

- [ ] **Step 3: Implement**

Add to `core/app/harvest/routes.py`, after `export_dataset_arcgis_aggregate`, and add `open_spatial_connection` to the analytics import block:

```python
from app.analytics.duckdb_conn import open_spatial_connection
```

```python
_EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}
_EXPORT_ITEMS_CAP = 10_000


@router.get("/datasets/{item_id}/arcgis/export/items")
def export_dataset_arcgis_items(
    item_id: str, request: Request, format: str = Query(...), bbox: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    client: httpx.Client = Depends(get_arcgis_http_client),
):
    if format not in _EXPORT_FORMATS_ITEMS:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}]},
        )
    parsed_bbox = _parse_bbox(bbox)
    reserved = {"limit", "offset", "bbox", "format"}
    filters = {k: v for k, v in request.query_params.items() if k not in reserved}
    external_url = _resolve_arcgis_dataset(session, item_id=item_id, user=user)

    features: list[dict] = []
    offset = 0
    limit = _MAX_LIMIT
    try:
        while True:
            params = live_query.translate_features_query(filters=filters, bbox=parsed_bbox, limit=limit, offset=offset)
            raw = live_query.fetch_query(client, external_url, params)
            page_features = raw.get("features", []) if isinstance(raw, dict) else []
            features.extend(page_features)
            if len(features) > _EXPORT_ITEMS_CAP:
                raise HTTPException(status_code=413, detail="too many entities matched, refine your filters")
            if len(page_features) < limit:
                break
            offset += limit
    except live_query.ArcgisQueryError as exc:
        raise HTTPException(
            status_code=400,
            detail={"errors": [{"field": exc.field, "code": "invalid_filter", "message": exc.message}]},
        )
    except EgressBlockedError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="arcgis service unavailable")
    finally:
        client.close()

    if format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=format)
    item = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=item_id)
    filename = export_filename(item.title if item else item_id, format=format)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="item", object_id=item_id,
                payload={"format": format, "mode": "items"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_harvest_dataset_arcgis_export_routes.py -v`
Expected: PASS (all tests in the file, both Task 5 and Task 6)

- [ ] **Step 5: Commit**

```bash
git add core/app/harvest/routes.py core/tests/test_harvest_dataset_arcgis_export_routes.py
git commit -m "feat(core): SP-16a — GET /datasets/{id}/arcgis/export/items (entités brutes, 4 formats)"
```

---

