# SPDX-License-Identifier: Apache-2.0
"""`reader.wfs` (ARC vague 4, voie M, F7) : lit une couche d'un service WFS distant.

Les formats vectoriels fichier (SHP/GPKG/GeoJSON/KML/GML) sont déjà lus par `reader.file`
(`ST_Read`, gardé par CORE_PIPELINE_FILE_IO_ENABLED, VRT refusés à l'import) et par l'import
de fichiers (ARC-23) ; seul le WFS manquait. GetFeature en GeoJSON, parsé en Python (jamais
`ST_Read` sur une URL : la connexion DuckDB n'a pas à sortir sur le réseau), requête émise par
la session gardée de `app.pipelines.egress` (SSRF, épinglage DNS, plages internes refusées).

Pas d'authentification (services publics) : un secret lié à un `baseUrl` viendra avec un
besoin réel. Axe des coordonnées : on demande `srsName=EPSG:<srid>` ; certains serveurs
renvoient lat/lon pour l'EPSG:4326 — vérifier l'aperçu sur un service inconnu."""

import json
import time
from typing import Literal

import pandas as pd
import requests
import shapely.geometry
import shapely.wkb
from pydantic import BaseModel, Field

from app.pipelines.egress import EgressBlockedError, build_guarded_session
from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi

MAX_RESPONSE_BYTES = 100 * 1024 * 1024
# Budget global de téléchargement : le délai de lecture seul ne borne pas un goutte-à-goutte.
DEADLINE_S = 120.0
_CHUNK = 64 * 1024


class ReaderWfsParams(BaseModel):
    """Lit les entités d'une couche d'un service WFS (GetFeature, sortie GeoJSON) : adresse du
    service, nom de la couche (typeName), plafond d'entités et CRS demandé."""

    url: str = Field(..., min_length=1)
    typeName: str = Field(..., min_length=1)
    version: Literal["1.1.0", "2.0.0"] = "2.0.0"
    maxFeatures: int = Field(10_000, ge=1, le=100_000)
    srid: int = Field(4326, ge=1)


def _download(url: str, query: dict) -> bytes:
    """GET en flux : lecture par blocs, abandon au dépassement de taille ou de temps."""
    deadline = time.monotonic() + DEADLINE_S
    response = None
    try:
        response = build_guarded_session().get(url, params=query, stream=True)
        response.raise_for_status()
        chunks: list[bytes] = []
        total = 0
        for chunk in response.iter_content(_CHUNK):
            total += len(chunk)
            if total > MAX_RESPONSE_BYTES:
                raise PipelineRuntimeError("reader.wfs: response too large")
            if time.monotonic() > deadline:
                raise PipelineRuntimeError("reader.wfs: download exceeded the time limit")
            chunks.append(chunk)
        return b"".join(chunks)
    except EgressBlockedError as exc:
        raise PipelineRuntimeError(f"reader.wfs: egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        cause = exc.__cause__ or exc.__context__
        if isinstance(cause, EgressBlockedError):
            raise PipelineRuntimeError(f"reader.wfs: egress blocked: {cause}") from exc
        raise PipelineRuntimeError(f"reader.wfs: request failed: {exc}") from exc
    finally:
        if response is not None:
            response.close()


def read_wfs(
    conn,
    *,
    session,
    tenant_id: str,
    node_id: str,
    params: dict,
    view_name: str,
    user,
    base_uri: str,
) -> int:
    """Signature uniforme des READERS ; session/tenant/user/base_uri ignorés (aucune
    collection, aucun secret)."""
    p = ReaderWfsParams.model_validate(params)
    query = {
        "service": "WFS",
        "version": p.version,
        "request": "GetFeature",
        "outputFormat": "application/json",
        "srsName": f"EPSG:{p.srid}",
    }
    if p.version == "2.0.0":
        query.update(typeNames=p.typeName, count=p.maxFeatures)
    else:
        query.update(typeName=p.typeName, maxFeatures=p.maxFeatures)
    body = _download(p.url, query)
    try:
        features = json.loads(body)["features"]
    except (ValueError, KeyError, TypeError) as exc:
        raise PipelineRuntimeError(
            "reader.wfs: response is not a GeoJSON FeatureCollection "
            "(does the service support outputFormat=application/json?)"
        ) from exc

    rows: list[dict] = []
    for f in features:
        props = {
            k: json.dumps(v) if isinstance(v, (dict, list)) else v
            for k, v in (f.get("properties") or {}).items()
        }
        if any(k.lower() == "geometry" for k in props):
            raise PipelineRuntimeError(
                "reader.wfs: a property is named 'geometry', which would collide with the "
                "geometry column"
            )
        geom = f.get("geometry")
        rows.append(
            {**props, "geometry": shapely.wkb.dumps(shapely.geometry.shape(geom)) if geom else None}
        )
    frame = pd.DataFrame(rows, columns=None if rows else ["geometry"])
    conn.register("_wfs_tmp", frame)
    try:
        select = ", ".join(
            f"ST_GeomFromWKB(CAST({_qi(c)} AS BLOB)) AS geometry" if c == "geometry" else _qi(c)
            for c in frame.columns
        )
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT {select} FROM _wfs_tmp")
    finally:
        conn.unregister("_wfs_tmp")
    return p.srid
