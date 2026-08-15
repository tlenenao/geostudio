### Task 6: `app.appexport.miniserver.main` — the FastAPI mini-server

**Files:**
- Create: `core/app/appexport/miniserver/main.py`
- Create: `core/tests/test_appexport_miniserver_main.py`

**Interfaces:**
- Consumes: `read_manifest` (Task 3), `select_features`/`get_feature`
  (Task 5), `open_local_connection` (Task 2),
  `AggregateRequestBody`/`UnknownAggregateField`/`run_collection_aggregate`
  (`app.analytics.aggregate`, unchanged).
- Produces: `app` — a FastAPI instance. Routes:
  `GET /geostudio-connection.json` (dynamic, echoes `request.base_url`),
  `GET /geostudio-app-config.json` (serves the mounted config file),
  `GET /collections`, `GET /collections/{id}`, `GET /collections/{id}/schema`,
  `GET /collections/{id}/items`, `GET /collections/{id}/items/{fid}`,
  `POST /collections/{id}/aggregate`, plus a catch-all static mount at `/`
  serving the baked-in shell runtime. Reads `APPEXPORT_STANDALONE_DATA_DIR`
  (default `/data`) and `APPEXPORT_STANDALONE_RUNTIME_DIR` (default
  `/runtime`) at **import time** — deliberately not per-request (the static
  mount itself can only be configured once at startup in Starlette), so
  tests must set both env vars via `monkeypatch` **before** importing/
  reloading this module.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_appexport_miniserver_main.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import importlib
import json

from fastapi.testclient import TestClient

from app.appexport.manifest import CollectionSnapshotEntry, write_manifest
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _build_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "geostudio-app-config.json").write_text(json.dumps({"kind": "app"}))

    table_info = TableInfo(
        table_name="t_x", pk_column="id", geometry_column=None, geometry_type=None, srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )
    entry = CollectionSnapshotEntry(
        id="col1", tenant_id="t1",
        collection_json={
            "id": "col1", "title": "X", "description": "", "tableName": "t_x",
            "isPublic": True, "editable": False, "geometryType": None, "srid": 4326,
            "pkColumn": "id", "canWrite": False, "featureCount": 1, "owner": None,
        },
        schema_json={
            "collection": "t_x", "pk": "id", "geometry": None,
            "fields": [{"name": "name", "type": "string", "required": False}],
        },
        table_info=table_info,
    )
    write_manifest([entry], str(data_dir / "manifest.json"))

    parquet_dir = data_dir / "snapshot" / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(
        [ChangeRow(op="insert", lsn=0, ts=0.0, pk_column="id", pk_value=1,
                   columns={"name": "Alpha"}, geometry_column=None, geometry_wkb_hex=None)],
        srid=4326, path=str(parquet_dir / "data.parquet"),
    )
    return data_dir


def _client(tmp_path, monkeypatch):
    data_dir = _build_data_dir(tmp_path)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.html").write_text("<html><body>runtime</body></html>")
    monkeypatch.setenv("APPEXPORT_STANDALONE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("APPEXPORT_STANDALONE_RUNTIME_DIR", str(runtime_dir))

    import app.appexport.miniserver.main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_geostudio_app_config_is_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-app-config.json")
    assert response.status_code == 200
    assert response.json() == {"kind": "app"}


def test_geostudio_connection_echoes_request_origin(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-connection.json")
    assert response.status_code == 200
    assert response.json()["coreUrl"].startswith("http")


def test_list_collections_returns_manifest_entries(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections")
    assert response.status_code == 200
    assert [c["id"] for c in response.json()["collections"]] == ["col1"]


def test_get_collection_includes_links(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1")
    assert response.status_code == 200
    body = response.json()
    assert body["itemType"] == "feature"
    assert any(link["rel"] == "items" for link in body["links"])


def test_get_collection_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/ghost").status_code == 404


def test_get_schema_returns_manifest_schema(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/schema")
    assert response.status_code == 200
    assert response.json()["pk"] == "id"


def test_list_items_reads_snapshot(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["name"] == "Alpha"


def test_get_single_item(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items/1")
    assert response.status_code == 200
    assert response.json()["properties"]["name"] == "Alpha"


def test_get_single_item_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/col1/items/999").status_code == 404


def test_aggregate_counts_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/col1/aggregate", json={"agg": "count"})
    assert response.status_code == 200
    assert response.json()["rows"][0]["value"] == 1


def test_aggregate_unknown_collection_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/ghost/aggregate", json={"agg": "count"})
    assert response.status_code == 404


def test_static_runtime_is_served_at_root(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "runtime" in response.text
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_main.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.miniserver.main'`

- [ ] **Step 3: Create `main.py`**

Create `core/app/appexport/miniserver/main.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Mini-serveur read-only du mode Autoporté (SP-18c) : sert le même
sous-ensemble anonyme-capable qu'énumérait déjà l'allowlist CORS de SP-18b
(GET /collections[...], POST .../aggregate), plus le bundle statique du
shell prébâti — un seul processus, une seule origine, donc AUCUN CORS requis
(contrairement au mode Connecté, qui appelle un cœur GeoStudio distant
depuis un domaine tiers). /geostudio-connection.json répond dynamiquement
avec sa propre origine : entry.tsx (déjà livré en SP-18b) n'a besoin
d'aucun changement, il construit déjà un ItemClient "connecté" dès qu'il
voit ce fichier — ici "connecté" signifie simplement "à soi-même".

DATA_DIR/RUNTIME_DIR sont lus une fois à l'import (le mount StaticFiles ne
peut être configuré qu'au démarrage dans Starlette) — les tests rechargent
ce module après avoir positionné les variables d'environnement
(importlib.reload), jamais une lecture par requête ici."""
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from app.analytics.aggregate import AggregateRequestBody, UnknownAggregateField, run_collection_aggregate
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.manifest import read_manifest
from app.appexport.miniserver.items import get_feature, select_features

DATA_DIR = Path(os.environ.get("APPEXPORT_STANDALONE_DATA_DIR", "/data"))
RUNTIME_DIR = Path(os.environ.get("APPEXPORT_STANDALONE_RUNTIME_DIR", "/runtime"))

_MANIFEST_BY_ID = {e.id: e for e in read_manifest(str(DATA_DIR / "manifest.json"))}

app = FastAPI()


def _snapshot_base_uri() -> str:
    return str(DATA_DIR / "snapshot")


def _get_entry(collection_id: str):
    entry = _MANIFEST_BY_ID.get(collection_id)
    if entry is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return entry


def _parse_bbox(raw: str | None):
    if raw is None:
        return None
    parts = raw.split(",")
    return tuple(float(p) for p in parts) if len(parts) == 4 else None


@app.get("/geostudio-connection.json")
def geostudio_connection(request: Request):
    return {"coreUrl": str(request.base_url).rstrip("/")}


@app.get("/geostudio-app-config.json")
def geostudio_app_config():
    path = DATA_DIR / "geostudio-app-config.json"
    if not path.is_file():
        raise HTTPException(status_code=404, detail="geostudio-app-config.json not found")
    return Response(content=path.read_bytes(), media_type="application/json")


@app.get("/collections")
def list_collections():
    return {"collections": [e.collection_json for e in _MANIFEST_BY_ID.values()]}


@app.get("/collections/{collection_id}")
def get_collection(collection_id: str, request: Request):
    entry = _get_entry(collection_id)
    base = str(request.base_url).rstrip("/")
    body = dict(entry.collection_json)
    body["itemType"] = "feature"
    body["extent"] = None
    body["links"] = [
        {"rel": "self", "type": "application/json", "href": f"{base}/collections/{entry.id}"},
        {"rel": "items", "type": "application/geo+json", "href": f"{base}/collections/{entry.id}/items"},
    ]
    return body


@app.get("/collections/{collection_id}/schema")
def get_schema(collection_id: str):
    return _get_entry(collection_id).schema_json


@app.get("/collections/{collection_id}/items")
def list_items(
    collection_id: str, request: Request,
    limit: int = Query(100, ge=1), offset: int = Query(0, ge=0),
    bbox: str | None = None,
):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        page = select_features(
            conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
            collection_id=collection_id, table_info=entry.table_info,
            limit=min(limit, 1000), offset=offset, bbox=_parse_bbox(bbox),
        )
    finally:
        conn.close()
    return {
        "type": "FeatureCollection", "features": page.features,
        "numberMatched": page.number_matched, "numberReturned": page.number_returned,
        "timeStamp": datetime.now(timezone.utc).isoformat(),
        "links": [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}],
    }


@app.get("/collections/{collection_id}/items/{fid}")
def get_single_item(collection_id: str, fid: str):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
            collection_id=collection_id, table_info=entry.table_info, fid=fid,
        )
    finally:
        conn.close()
    if feature is None:
        raise HTTPException(status_code=404, detail="feature not found")
    return feature


@app.post("/collections/{collection_id}/aggregate")
def aggregate(collection_id: str, body: AggregateRequestBody):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        try:
            category_key, rows = run_collection_aggregate(
                conn, base_uri=_snapshot_base_uri(), tenant_id=entry.tenant_id,
                collection_id=collection_id, table_info=entry.table_info, request=body,
            )
        except UnknownAggregateField as exc:
            raise HTTPException(
                status_code=400,
                detail={"errors": [{"field": exc.field, "code": "unknown_field", "message": exc.message}]},
            )
    finally:
        conn.close()
    return {"categoryKey": category_key, "rows": rows}


# Doit rester la DERNIÈRE route enregistrée : Starlette matche dans l'ordre
# d'ajout, un mount à "/" déclaré plus tôt masquerait toutes les routes
# ci-dessus. html=True sert index.html pour "/" et pour toute route
# client-side (fallback SPA).
app.mount("/", StaticFiles(directory=str(RUNTIME_DIR), html=True), name="static")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_miniserver_main.py -v`
Expected: PASS (11 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/miniserver/main.py core/tests/test_appexport_miniserver_main.py
git commit -m "feat(core): standalone mini-server FastAPI app (SP-18c)"
```

---

