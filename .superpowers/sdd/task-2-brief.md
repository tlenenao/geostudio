## Task 2: Core — `geom_intersects` on the OGC API Features endpoint

**Files:**
- Modify: `core/app/features/repository.py:8-17` (no new import needed, `json` already imported), `:66-99` (`_where`), `:120-124` (`select_features`)
- Modify: `core/app/features/routes.py:5,40,91-103,124-141` (`import json`, `RESERVED_QUERY_PARAMS`, new `_parse_geom_intersects`, `list_features`)
- Test: `core/tests/test_features_repository.py` (append, postgis-marked), `core/tests/test_features_routes_read.py` (append, no docker needed)

**Interfaces:**
- Produces: `select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None)` — `geom_intersects` is a GeoJSON dict, translated to `ST_Intersects(<geom>, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(...), 4326), <srid>))`; raises `FilterError("geom_intersects", "collection has no geometry")` when the collection has none. `GET /collections/{id}/items?geom_intersects=<url-encoded GeoJSON>` parses and forwards it the same way `bbox` already does.

- [ ] **Step 1: Write the failing repository tests (postgis-marked)**

Append to `core/tests/test_features_repository.py`, right after `test_pagination_and_bbox_and_filters`. Add the import at the top first:

```python
from dataclasses import replace

import pytest
from sqlalchemy import text
```

Then the tests:

```python
def test_geom_intersects_filters_by_exact_polygon(info, pg_session_factory):
    polygon = {
        "type": "Polygon",
        "coordinates": [[[0.5, 44.5], [1.5, 44.5], [1.5, 45.5], [0.5, 45.5], [0.5, 44.5]]],
    }
    with pg_session_factory() as session, rls_scope(session, "default"):
        page = select_features(session, info, limit=10, offset=0, geom_intersects=polygon)
        assert [f["id"] for f in page.features] == [1]


def test_geom_intersects_without_geometry_column_raises(info, pg_session_factory):
    info_no_geom = replace(info, geometry_column=None)
    with pg_session_factory() as session, rls_scope(session, "default"):
        with pytest.raises(FilterError):
            select_features(session, info_no_geom, limit=10, offset=0,
                            geom_intersects={"type": "Point", "coordinates": [0, 0]})
```

- [ ] **Step 2: Run repository tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_repository.py -k geom_intersects -v -m postgis`
Expected: FAIL if docker/postgis is available (`select_features() got an unexpected keyword argument 'geom_intersects'`); SKIPPED otherwise (postgis-marked, consistent with the other 87 skipped tests — see `CLAUDE.md`). If docker isn't running in this environment, proceed to Step 3 anyway and rely on Step 4's route-level test (no docker needed) plus a later run against docker before merging.

- [ ] **Step 3: Implement the repository layer**

In `core/app/features/repository.py`, extend `_where` (currently at line 66):

```python
def _where(session: Session, info: TableInfo, bbox, geom_intersects, filters):
    clauses, params = [], {}
    if filters:
        by_name = {c.name: c for c in _property_columns(info)}
        for i, (raw_name, raw) in enumerate(sorted(filters.items())):
            name, suffix = _split_filter_key(raw_name)
            col = by_name.get(name)
            if col is None:
                raise FilterError(name, f"unknown filter property '{name}'")
            if col.type == "unsupported":
                raise FilterError(name, "property not filterable")
            ident = quote_ident(session, name)
            if suffix == "__in":
                values = raw.split(",")
                placeholders = []
                for j, value in enumerate(values):
                    key = f"f{i}_{j}"
                    params[key] = _coerce(col, value)
                    placeholders.append(f":{key}")
                clauses.append(f"{ident} IN ({', '.join(placeholders)})")
            elif suffix in _RANGE_OPS:
                clauses.append(f"{ident} {_RANGE_OPS[suffix]} :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
            else:
                clauses.append(f"{ident} = :f{i}")
                params[f"f{i}"] = _coerce(col, raw)
    if bbox is not None:
        if info.geometry_column is None:
            raise FilterError("bbox", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(f"{g} && ST_Transform(ST_MakeEnvelope(:bx0, :by0, :bx1, :by1, 4326), :bsrid)")
        params.update({"bx0": bbox[0], "by0": bbox[1], "bx1": bbox[2],
                       "by1": bbox[3], "bsrid": info.srid or 4326})
    if geom_intersects is not None:
        # SP-14n : intersection géométrique exacte (ST_Intersects), complément
        # précis du bbox && ci-dessus (chevauchement d'enveloppes uniquement).
        if info.geometry_column is None:
            raise FilterError("geom_intersects", "collection has no geometry")
        g = quote_ident(session, info.geometry_column)
        clauses.append(
            f"ST_Intersects({g}, ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:gi), 4326), :gisrid))"
        )
        params.update({"gi": json.dumps(geom_intersects), "gisrid": info.srid or 4326})
    return (" WHERE " + " AND ".join(clauses)) if clauses else "", params
```

Update `select_features` (currently at line 120):

```python
def select_features(session: Session, info: TableInfo, *, limit: int, offset: int,
                    bbox=None, geom_intersects=None, filters=None) -> FeaturePage:
    t = quote_ident(session, info.table_name)
    where, params = _where(session, info, bbox, geom_intersects, filters)
```

(the rest of the function body is unchanged — only the call to `_where` gains the new argument).

- [ ] **Step 4: Run repository tests again**

Run: `cd core && uv run pytest tests/test_features_repository.py -v -m postgis`
Expected: PASS if docker is available (all tests in the file, including the 2 new ones); SKIPPED as a block otherwise.

- [ ] **Step 5: Write the failing route-level test (no docker needed)**

Append to `core/tests/test_features_routes_read.py`. Add `import json` at the top (line 1, alongside the existing imports), and update `make_fake_repo`'s `select_features` signature to accept and record the new parameter:

```python
def make_fake_repo(matched=3):
    calls = {}

    def select_features(session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None):
        calls.update(limit=limit, offset=offset, bbox=bbox, geom_intersects=geom_intersects, filters=filters)
        if filters and "inconnu" in filters:
            raise FilterError("inconnu", "unknown filter property 'inconnu'")
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature,
                           calls=calls)
```

Then add the test, right after `test_bbox_parsing`:

```python
def test_geom_intersects_parsing(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    geom = {"type": "Point", "coordinates": [1.0, 2.0]}
    r = client.get("/collections/incidents/items", params={"geom_intersects": json.dumps(geom)})
    assert r.status_code == 200
    assert repo.calls["geom_intersects"] == geom
    r2 = client.get("/collections/incidents/items", params={"geom_intersects": "not-json"})
    assert r2.status_code == 400
    assert r2.json()["detail"]["errors"][0]["code"] == "invalid_geom_intersects"
```

- [ ] **Step 6: Run route tests to verify they fail**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: FAIL — `list_features` has no `geom_intersects` query parameter yet (unrecognized param is just ignored by FastAPI, so `repo.calls["geom_intersects"]` raises `KeyError`, and the malformed-JSON case returns 200 instead of 400).

- [ ] **Step 7: Implement the route layer**

In `core/app/features/routes.py`, add the import (line 5, alongside `os`):

```python
import json
import os
```

Extend `RESERVED_QUERY_PARAMS` (line 40):

```python
RESERVED_QUERY_PARAMS = {"limit", "offset", "bbox", "geom_intersects", "f"}
```

Add `_parse_geom_intersects` right after `_parse_bbox` (around line 91):

```python
def _parse_geom_intersects(raw: str | None):
    if raw is None:
        return None
    try:
        parsed = json.loads(raw)
    except ValueError:
        raise _validation_error(
            [{"field": "geom_intersects", "code": "invalid_geom_intersects",
              "message": "geom_intersects must be a GeoJSON geometry encoded as JSON"}])
    if not isinstance(parsed, dict) or "type" not in parsed or "coordinates" not in parsed:
        raise _validation_error(
            [{"field": "geom_intersects", "code": "invalid_geom_intersects",
              "message": "geom_intersects must be a GeoJSON geometry encoded as JSON"}])
    return parsed
```

Update `list_features` (around line 124):

```python
@router.get("/collections/{collection_id}/items")
def list_features(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None, geom_intersects: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect=Depends(get_introspector), repo=Depends(get_features_repo),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)
    info = introspect(session, col.table_name)
    limit = min(limit, MAX_LIMIT)
    parsed_bbox = _parse_bbox(bbox)
    parsed_geom_intersects = _parse_geom_intersects(geom_intersects)
    filters = _collect_filters(request)
    try:
        with rls(session, col.tenant_id):
            page = repo.select_features(session, info, limit=limit, offset=offset,
                                        bbox=parsed_bbox, geom_intersects=parsed_geom_intersects,
                                        filters=filters or None)
    except FilterError as exc:
        raise _validation_error(
            [{"field": exc.field, "code": "unknown_filter", "message": exc.message}])
    return {
        "type": "FeatureCollection",
        "features": page.features,
        "numberMatched": page.number_matched,
        "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": _page_links(request, limit=limit, offset=offset, page=page),
    }
```

- [ ] **Step 8: Run route tests to verify they pass**

Run: `cd core && uv run pytest tests/test_features_routes_read.py -v`
Expected: PASS (all tests, including the new one).

- [ ] **Step 9: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: same baseline as before (606 + however many prior tasks added) plus 3 new tests (1 route-level, 2 postgis-marked — skipped without docker), no regressions.

- [ ] **Step 10: Commit**

```bash
git add core/app/features/repository.py core/app/features/routes.py core/tests/test_features_repository.py core/tests/test_features_routes_read.py
git commit -m "feat(core): geom_intersects filter on OGC API Features (SP-14n)"
```

---

