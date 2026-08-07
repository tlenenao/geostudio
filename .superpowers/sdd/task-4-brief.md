### Task 4: `GET /collections/{id}/export/items` (raw-entities mode, collection-backed)

**Files:**
- Modify: `core/app/features/routes.py`
- Modify: `core/tests/test_features_export_routes.py` (same file as Task 3, append)

**Interfaces:**
- Consumes: `features_to_format` (Task 2), `open_spatial_connection` (Task 1), `_parse_bbox`, `_parse_geom_intersects`, `_collect_filters`, `get_features_repo`, `get_rls_scope`, `FilterError` (all already present in this file), `MAX_LIMIT` (already present, = 1000).
- Produces: route `GET /collections/{collection_id}/export/items?format=csv|xlsx|geojson|gpkg` — used by Task 8 and by Task 12 (`DatasetEditPage`, unfiltered, all formats).

- [ ] **Step 1: Write the failing tests**

Append to `core/tests/test_features_export_routes.py`:

```python
def test_export_items_geojson_returns_a_feature_collection(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _seed(tmp_path, tenant_id, col["id"])
    # items export reads from the live PostGIS-backed collection table via
    # select_features, not the GeoParquet CDC lake used by aggregate — but
    # this fixture never wrote actual rows to the fake sqlite-backed
    # collection table, only to the CDC parquet lake (_seed). To exercise
    # the items path meaningfully, create features through the normal write
    # route first.
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=geojson")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/geo+json"
    body = resp.json()
    assert body["type"] == "FeatureCollection"
    assert len(body["features"]) == 1
    assert body["features"][0]["properties"]["region"] == "Nord"


def test_export_items_csv_flattens_properties(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 200
    assert "Nord" in resp.text
    assert "geometry" not in resp.text.splitlines()[0]


def test_export_items_gpkg_returns_a_sqlite_container(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord", "pop": 10}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=gpkg")
    assert resp.status_code == 200
    assert resp.content[:16] == b"SQLite format 3\x00"


def test_export_items_rejects_unknown_format(env):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    col = _register(app, client, admin, public=True)
    resp = client.get(f"/collections/{col['id']}/export/items?format=pdf")
    assert resp.status_code == 400


def test_export_items_caps_at_10000_entities(env, monkeypatch):
    app, client, admin, _r, tmp_path, tenant_id, _Session = env
    import app.features.routes as routes_module
    monkeypatch.setattr(routes_module, "EXPORT_ITEMS_CAP", 1)
    col = _register(app, client, admin, public=True)
    _as(app, admin)
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Nord"}, "geometry": {"type": "Point", "coordinates": [0, 0]},
    })
    client.post(f"/collections/{col['id']}/items", json={
        "properties": {"region": "Sud"}, "geometry": {"type": "Point", "coordinates": [1, 1]},
    })
    resp = client.get(f"/collections/{col['id']}/export/items?format=csv")
    assert resp.status_code == 413
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -k items -v`
Expected: FAIL — 404 on every new test.

- [ ] **Step 3: Implement the route**

Add to `core/app/features/routes.py`, after the new `export_collection_aggregate` route:

```python
EXPORT_FORMATS_ITEMS = {"csv", "xlsx", "geojson", "gpkg"}
EXPORT_ITEMS_CAP = 10_000


@router.get("/collections/{collection_id}/export/items")
def export_collection_items(
    collection_id: str, request: Request, format: str = Query(...),
    bbox: str | None = None, geom_intersects: str | None = None,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    if format not in EXPORT_FORMATS_ITEMS:
        raise _validation_error(
            [{"field": "format", "code": "unsupported_format", "message": f"unsupported format '{format}'"}])
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    parsed_bbox = _parse_bbox(bbox)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)

    features: list[dict] = []
    offset = 0
    while True:
        try:
            with rls(session, col.tenant_id):
                page = repo.select_features(session, info, limit=MAX_LIMIT, offset=offset,
                                            bbox=parsed_bbox, geom_intersects=parsed_geom_intersects,
                                            filters=filters or None)
        except FilterError as exc:
            raise _validation_error(
                [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
        features.extend(page.features)
        if len(features) > EXPORT_ITEMS_CAP:
            raise HTTPException(status_code=413, detail="too many entities matched, refine your filters")
        if page.number_returned < MAX_LIMIT:
            break
        offset += MAX_LIMIT

    if format == "gpkg":
        conn = open_spatial_connection()
        try:
            content = features_to_format(features, format=format, conn=conn)
        finally:
            conn.close()
    else:
        content = features_to_format(features, format=format)
    filename = export_filename(col.title, format=format)
    write_audit(session, tenant_id=col.tenant_id, actor_id=user.id, actor_kind="user",
                action="export.run", object_type="collection", object_id=col.id,
                payload={"format": format, "mode": "items"})
    return Response(content=content, media_type=EXPORT_MEDIA_TYPES[format],
                     headers={"Content-Disposition": f'attachment; filename="{filename}"'})
```

Add `open_spatial_connection` to the `app.analytics.duckdb_conn` import (new line, since `duckdb_conn` isn't currently imported in this file):

```python
from app.analytics.duckdb_conn import open_spatial_connection
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_export_routes.py -v`
Expected: PASS (all tests in the file, both Task 3 and Task 4)

- [ ] **Step 5: Commit**

```bash
git add core/app/features/routes.py core/tests/test_features_export_routes.py
git commit -m "feat(core): SP-16a — GET /collections/{id}/export/items (entités brutes, 4 formats)"
```

---

