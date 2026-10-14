# SPDX-License-Identifier: Apache-2.0
"""`reader.raster` (ARC-33, ADR 0024) : lit une bande d'un raster COG de la plateforme et la
matérialise en points (un par cellule valide : x, y, value, geometry = centre de cellule).

Mêmes contrôles que les tuiles : `can(read)` sur l'item (404 indistinguable sinon) et refus
fail-closed si l'appelant est limité géographiquement sur la collection de référence du
raster. Borné par `maxCells` : au-delà, lecture décimée (plus proche voisin, via les
overviews du COG) plutôt que de charger tout le raster en mémoire."""

import math

import numpy as np
import pandas as pd
import rasterio.transform
from pydantic import BaseModel, Field
from rasterio.enums import Resampling

from app.items import repository as items_repo
from app.pipelines.errors import PipelineRuntimeError
from app.raster import repository as raster_repo
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
    facts = items_repo.get_access_facts(session, tenant_id=tenant_id, item_id=p.itemId)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise PipelineRuntimeError(f"raster '{p.itemId}' not found")
    asset = raster_repo.get_asset(session, tenant_id=tenant_id, item_id=p.itemId)
    if asset is None:
        raise PipelineRuntimeError(f"raster '{p.itemId}' not found")
    try:
        refuse_if_raster_geo_limited(
            session,
            asset,
            resolve_geo_limits(session, tenant_id=tenant_id, user_id=user.id),
            "reader.raster",
        )
    except GeoLimitRefused as exc:
        raise PipelineRuntimeError(f"raster '{p.itemId}' is geo-limited: {exc.detail}") from exc

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
