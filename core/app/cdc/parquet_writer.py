# SPDX-License-Identifier: Apache-2.0
"""Écriture GeoParquet 1.0 pour les lots de changements CDC (SP-11a §Format
de sortie) : append-only change log, jamais un état fusionné. Une ligne
"delete" est une tombstone — seules la PK et _op sont renseignées (REPLICA
IDENTITY par défaut n'expose que la PK sur delete, pas besoin de REPLICA
IDENTITY FULL). Pas de reprojection : le SRID source (Collection.srid) est
passé tel quel par l'appelant et posé comme CRS de sortie."""

from dataclasses import dataclass

import geopandas as gpd
import shapely.wkb
from shapely.geometry.base import BaseGeometry


@dataclass
class ChangeRow:
    op: str  # "insert" | "update" | "delete"
    lsn: int
    ts: float  # horloge murale d'écriture du FLUSH (pas l'horodatage wal2json)
    pk_column: str
    pk_value: object
    columns: dict  # colonnes métier ; {pk_column: pk_value} seulement si op == "delete"
    geometry_column: str | None
    geometry_wkb_hex: str | None  # hex EWKB ; None pour une tombstone ou une table sans géométrie


def _decode_geometry(wkb_hex: str | None) -> BaseGeometry | None:
    if wkb_hex is None:
        return None
    return shapely.wkb.loads(bytes.fromhex(wkb_hex))


def build_geodataframe(rows: list[ChangeRow], *, srid: int) -> gpd.GeoDataFrame:
    records = []
    geometries = []
    for row in rows:
        record = dict(row.columns)
        record[row.pk_column] = row.pk_value
        record["_op"] = row.op
        record["_lsn"] = row.lsn
        record["_ts"] = row.ts
        records.append(record)
        geometries.append(_decode_geometry(row.geometry_wkb_hex))
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def write_geoparquet(rows: list[ChangeRow], *, srid: int, path: str) -> None:
    gdf = build_geodataframe(rows, srid=srid)
    gdf.to_parquet(path)
