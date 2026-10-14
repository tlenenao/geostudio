# SPDX-License-Identifier: Apache-2.0
"""`reader.raster` et `transform.zonalStats` (ARC-33, ADR 0024). `reader.raster` lit une bande
d'un raster COG de la plateforme et la matérialise en points (un par cellule valide : x, y,
value, geometry = centre de cellule) ; `transform.zonalStats` ajoute des statistiques de bande
sous chaque polygone de l'entrée.

Mêmes contrôles que les tuiles : `can(read)` sur l'item (404 indistinguable sinon) et refus
fail-closed si l'appelant est limité géographiquement sur la collection de référence du
raster. Borné par `maxCells` : au-delà, lecture décimée (plus proche voisin, via les
overviews du COG) plutôt que de charger tout le raster en mémoire."""

import json
import math
from typing import Literal

import numpy as np
import pandas as pd
import rasterio.transform
from pydantic import BaseModel, Field
from rasterio.enums import Resampling

from app.audit.writer import write_audit
from app.auth.dependency import is_raster_enabled
from app.items import repository as items_repo
from app.pipelines.errors import PipelineRuntimeError
from app.raster import repository as raster_repo
from app.raster import zonal
from app.raster.models import RasterAsset
from app.raster.service import open_asset, refuse_if_raster_geo_limited
from app.sharing.authorization import can
from app.sharing.geo_limits import GeoLimitRefused, resolve_geo_limits
from app.sql_ident import quote_ident_duckdb as _qi

MAX_CELLS = 2_000_000


class ReaderRasterParams(BaseModel):
    """Lit une bande d'un raster (item `raster`) en une ligne par cellule valide."""

    itemId: str = Field(..., min_length=1)
    band: int = Field(1, ge=1)
    maxCells: int = Field(1_000_000, ge=1, le=MAX_CELLS)


def _authorized_asset(session, tenant_id: str, user, item_id: str, op: str) -> RasterAsset:
    """Porte commune aux ops raster : `can(read)` sur l'item (absent et interdit
    indistinguables) puis refus fail-closed des limites géographiques (ADR 0024). La capacité
    est revérifiée à l'exécution (comme reader.file) : un pipeline enregistré avant
    l'extinction ne doit pas lire de raster dans le worker."""
    if not is_raster_enabled():
        raise PipelineRuntimeError(f"{op} requires CORE_RASTER_ENABLED=true")
    facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=item_id)
    if (
        facts is None
        or user is None
        or not can(session, user_id=user.id, action="read", item=facts)
    ):
        raise PipelineRuntimeError(f"raster '{item_id}' not found")
    asset = raster_repo.get_asset(session, tenant_id=tenant_id, item_id=item_id)
    if asset is None:
        raise PipelineRuntimeError(f"raster '{item_id}' not found")
    try:
        refuse_if_raster_geo_limited(
            session,
            asset,
            resolve_geo_limits(session, tenant_id=tenant_id, user_id=user.id),
            op,
        )
    except GeoLimitRefused as exc:
        raise PipelineRuntimeError(f"raster '{item_id}' is geo-limited: {exc.detail}") from exc
    return asset


def read_raster(
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
    """Signature uniforme des READERS ; retourne le SRID de la géométrie produite."""
    p = ReaderRasterParams.model_validate(params)
    asset = _authorized_asset(session, tenant_id, user, p.itemId, "reader.raster")
    with open_asset(asset) as ds:
        if p.band not in ds.indexes:
            raise PipelineRuntimeError(f"reader.raster: band {p.band} not found")
        scale = max(1.0, math.sqrt(ds.width * ds.height / p.maxCells))
        h, w = max(1, int(ds.height / scale)), max(1, int(ds.width / scale))
        data = ds.read(p.band, out_shape=(h, w), masked=True, resampling=Resampling.nearest)
        transform = ds.transform * ds.transform.scale(ds.width / w, ds.height / h)
    rows, cols = np.nonzero(~np.ma.getmaskarray(data))
    xs, ys = rasterio.transform.xy(transform, rows, cols)
    frame = pd.DataFrame({"x": xs, "y": ys, "value": np.ma.getdata(data)[rows, cols]})
    conn.register("_raster_tmp", frame)
    try:
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            "SELECT x, y, value, ST_Point(x, y) AS geometry FROM _raster_tmp"
        )
    finally:
        conn.unregister("_raster_tmp")
    return asset.srid


ZonalStatName = Literal["count", "min", "max", "mean", "sum", "std"]


class TransformZonalStatsParams(BaseModel):
    """Statistiques d'une bande raster (item `raster`) sous chaque polygone de l'entrée : ajoute
    une colonne `zonal_<stat>` par statistique (géométries non polygonales : NULL). Mêmes
    contrôles et plafonds que POST /v1/raster/{item}/zonal-stats (1 000 polygones, budget de
    pixels et de durée)."""

    itemId: str = Field(..., min_length=1)
    band: int = Field(1, ge=1)
    stats: list[ZonalStatName] = Field(
        default_factory=lambda: ["count", "mean", "min", "max"], min_length=1, max_length=6
    )


def execute_zonal_stats(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
    input_srid: int | None = None,
) -> None:
    p = TransformZonalStatsParams.model_validate(params)
    stats = list(dict.fromkeys(p.stats))
    session = getattr(secret_resolver, "session", None)
    user = getattr(secret_resolver, "user", None)
    if session is None or user is None:
        raise PipelineRuntimeError("transform.zonalStats: aucun acteur pour lire le raster")
    asset = _authorized_asset(session, user.tenant_id, user, p.itemId, "transform.zonalStats")
    cols = [d[0] for d in conn.execute(f"DESCRIBE {_qi(input_view)}").fetchall()]
    if "geometry" not in cols:
        raise PipelineRuntimeError("transform.zonalStats: input has no 'geometry' column")
    out_cols = [f"zonal_{s}" for s in stats]
    clash = [c for c in out_cols if c in cols]
    if clash:
        raise PipelineRuntimeError(f"transform.zonalStats: input already has column(s) {clash}")
    rows = conn.execute(
        f"SELECT row_number() OVER () AS rn, ST_AsGeoJSON(geometry) FROM {_qi(input_view)} "
        f"LIMIT {zonal.MAX_POLYGONS + 1}"
    ).fetchall()
    if len(rows) > zonal.MAX_POLYGONS:
        raise PipelineRuntimeError(
            f"transform.zonalStats: more than {zonal.MAX_POLYGONS} rows (cap of zonal statistics)"
        )
    polys = []
    for rn, gj in rows:
        g = json.loads(gj) if gj else None
        if g and g.get("type") in ("Polygon", "MultiPolygon"):
            polys.append((rn, g))
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="raster.zonal_stats",
        object_type="item",
        object_id=p.itemId,
        payload={"polygons": len(polys), "band": p.band, "op": "transform.zonalStats"},
    )
    session.commit()
    try:
        with open_asset(asset) as ds:
            results = zonal.zonal_stats(
                ds,
                [g for _, g in polys],
                band=p.band,
                stats=stats,
                src_crs=f"EPSG:{input_srid or 4326}",
            )
    except zonal.ZonalError as exc:
        raise PipelineRuntimeError(f"transform.zonalStats: {exc}") from exc
    frame = pd.DataFrame(
        [
            {"rn": rn, **{f"zonal_{k}": v for k, v in r.items()}}
            for (rn, _), r in zip(polys, results, strict=True)
        ],
        columns=["rn", *out_cols],
    ).astype({c: "float64" for c in out_cols})
    conn.register("_zonal_results", frame)
    try:
        sel = "".join(f", r.{_qi(c)}" for c in out_cols)
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT s.* EXCLUDE (_rn){sel} "
            f"FROM (SELECT *, row_number() OVER () AS _rn FROM {_qi(input_view)}) s "
            "LEFT JOIN _zonal_results r ON r.rn = s._rn ORDER BY s._rn"
        )
    finally:
        conn.unregister("_zonal_results")
