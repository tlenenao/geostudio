# SPDX-License-Identifier: Apache-2.0
"""Couche partagée REST / MCP / pipeline : ouverture d'un COG depuis S3 et lecture des
polygones d'une requête GeoJSON. Aucune URL fournie par l'appelant n'est jamais ouverte."""

import json
import os
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

import rasterio
from sqlalchemy.orm import Session

from app.collections.models import Collection
from app.raster.models import RasterAsset
from app.sharing.geo_limits import GeoLimitRefused, GeoLimits, refuse_if_geo_limited

MAX_GEOJSON_BYTES = 2_000_000


def raster_bucket() -> str:
    return os.environ.get("S3_RASTER_BUCKET", "geostudio-raster")


@contextmanager
def open_asset(asset: RasterAsset, *, bucket: str | None = None) -> Iterator[Any]:
    """Ouvre le COG du raster via /vsis3/ (GDAL) avec les identifiants S3 du cœur."""
    endpoint = os.environ["S3_ENDPOINT_URL"]
    with rasterio.Env(
        AWS_S3_ENDPOINT=endpoint.split("://", 1)[-1].rstrip("/"),
        AWS_HTTPS="YES" if endpoint.startswith("https") else "NO",
        AWS_VIRTUAL_HOSTING="FALSE",
        AWS_ACCESS_KEY_ID=os.environ["S3_ACCESS_KEY"],
        AWS_SECRET_ACCESS_KEY=os.environ["S3_SECRET_KEY"],
        GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
    ):
        with rasterio.open(f"/vsis3/{bucket or raster_bucket()}/{asset.source_key}") as ds:
            yield ds


def polygons_from_geojson(geojson: dict) -> list[tuple[str | int | None, dict]]:
    """Polygones (id, géométrie) d'un FeatureCollection/Feature/géométrie GeoJSON ; ValueError
    si autre chose qu'un Polygon/MultiPolygon."""
    if len(json.dumps(geojson)) > MAX_GEOJSON_BYTES:
        raise ValueError(f"geojson trop volumineux (> {MAX_GEOJSON_BYTES} octets)")
    t = geojson.get("type")
    if t == "FeatureCollection":
        feats = geojson.get("features")
        if not isinstance(feats, list):
            raise ValueError("invalid FeatureCollection")
        items = [(f.get("id"), f.get("geometry")) for f in feats if isinstance(f, dict)]
    elif t == "Feature":
        items = [(geojson.get("id"), geojson.get("geometry"))]
    else:
        items = [(None, geojson)]
    for _, g in items:
        if not isinstance(g, dict) or g.get("type") not in ("Polygon", "MultiPolygon"):
            raise ValueError("only Polygon/MultiPolygon are supported")
    return items


def refuse_if_raster_geo_limited(
    session: Session, asset: RasterAsset, limits: GeoLimits | None, path: str
) -> None:
    """Un raster ne sait pas être découpé : refus (403) si l'appelant est limité sur la collection
    de référence du raster ; FAIL-CLOSED si le raster n'est rattaché à aucune collection et que
    l'appelant porte au moins une limite active."""
    if not limits:
        return
    col = session.get(Collection, asset.limit_collection_id) if asset.limit_collection_id else None
    if col is None:
        raise GeoLimitRefused(path)
    refuse_if_geo_limited(limits, col.table_name, path=path)
