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
from datetime import UTC, datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query, Request, Response
from fastapi.staticfiles import StaticFiles

from app.analytics.aggregate import (
    AggregateRequestBody,
    UnknownAggregateField,
    run_collection_aggregate,
)
from app.analytics.duckdb_conn import open_local_connection
from app.appexport.manifest import read_manifest
from app.appexport.miniserver.items import MissingGeometryColumn, get_feature, select_features

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
        {
            "rel": "items",
            "type": "application/geo+json",
            "href": f"{base}/collections/{entry.id}/items",
        },
    ]
    return body


@app.get("/collections/{collection_id}/schema")
def get_schema(collection_id: str):
    return _get_entry(collection_id).schema_json


@app.get("/collections/{collection_id}/items")
def list_items(
    collection_id: str,
    request: Request,
    limit: int = Query(100, ge=1),
    offset: int = Query(0, ge=0),
    bbox: str | None = None,
):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        try:
            page = select_features(
                conn,
                base_uri=_snapshot_base_uri(),
                tenant_id=entry.tenant_id,
                collection_id=collection_id,
                table_info=entry.table_info,
                limit=min(limit, 1000),
                offset=offset,
                bbox=_parse_bbox(bbox),
            )
        except MissingGeometryColumn as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    finally:
        conn.close()
    return {
        "type": "FeatureCollection",
        "features": page.features,
        "numberMatched": page.number_matched,
        "numberReturned": page.number_returned,
        "timeStamp": datetime.now(UTC).isoformat(),
        "links": [{"rel": "self", "type": "application/geo+json", "href": str(request.url)}],
    }


@app.get("/collections/{collection_id}/items/{fid}")
def get_single_item(collection_id: str, fid: str):
    entry = _get_entry(collection_id)
    conn = open_local_connection()
    try:
        feature = get_feature(
            conn,
            base_uri=_snapshot_base_uri(),
            tenant_id=entry.tenant_id,
            collection_id=collection_id,
            table_info=entry.table_info,
            fid=fid,
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
                conn,
                base_uri=_snapshot_base_uri(),
                tenant_id=entry.tenant_id,
                collection_id=collection_id,
                table_info=entry.table_info,
                request=body,
            )
        except UnknownAggregateField as exc:
            raise HTTPException(
                status_code=400,
                detail={
                    "errors": [
                        {"field": exc.field, "code": "unknown_field", "message": exc.message}
                    ]
                },
            ) from exc
    finally:
        conn.close()
    return {"categoryKey": category_key, "rows": rows}


# Doit rester la DERNIÈRE route enregistrée : Starlette matche dans l'ordre
# d'ajout, un mount à "/" déclaré plus tôt masquerait toutes les routes
# ci-dessus. html=True sert index.html pour "/" et pour toute route
# client-side (fallback SPA).
app.mount("/", StaticFiles(directory=str(RUNTIME_DIR), html=True), name="static")
