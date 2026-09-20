# SPDX-License-Identifier: Apache-2.0
"""Écriture GeoParquet 1.0 pour les lots de changements CDC (SP-11a §Format
de sortie) : append-only change log, jamais un état fusionné. Une ligne
"delete" est une tombstone — seules la PK et _op sont renseignées (REPLICA
IDENTITY par défaut n'expose que la PK sur delete, pas besoin de REPLICA
IDENTITY FULL). Pas de reprojection : le SRID source (Collection.srid) est
passé tel quel par l'appelant et posé comme CRS de sortie.

build_geodataframe_from_relation/write_geoparquet_from_relation (design
docs/superpowers/specs/2026-09-16-ipc-echange-duckdb-arrow-design.md) :
chemin de repli GeoParquet consommé par app.pipelines.exchange.
to_geoparquet_file, pour une relation DuckDB arbitraire — jamais un
ChangeRow, dont les colonnes de plomberie CDC (_op/_lsn/_seq/_ts,
tombstones) n'ont pas de sens pour une relation de pipeline générique et
casseraient l'identité de schéma attendue par un round-trip GeoParquet
(cf. plan, section "Décision prise en amont"). Les deux chemins convergent
malgré tout sur UNE seule primitive d'écriture réelle (_write_gdf) :
jamais un writer Parquet réinventé."""

from dataclasses import dataclass
from typing import TYPE_CHECKING

import geopandas as gpd
import shapely.wkb
from shapely.geometry.base import BaseGeometry

from app.sql_ident import quote_ident_duckdb as _qi

if TYPE_CHECKING:
    import duckdb


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
    # Ordre d'ajout réel au buffer CDC (CdcBufferManager.add(), monotone,
    # affecté APRÈS construction — cf. app.cdc.buffer). Départage un `_lsn`
    # ex-aequo (app.cdc.consumer:54-70 : le settle peut tagger deux
    # transactions distinctes avec la même LSN) dans app.analytics.aggregate
    # ._dedup_cte. 0 par défaut pour les chemins qui n'écrivent jamais deux
    # versions de la même PK (ex. app.appexport.snapshot, un seul insert par
    # PK) : aucun ex-aequo possible là, donc aucun besoin de départage.
    seq: int = 0


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
        record["_seq"] = row.seq
        record["_ts"] = row.ts
        records.append(record)
        geometries.append(_decode_geometry(row.geometry_wkb_hex))
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def _write_gdf(gdf: gpd.GeoDataFrame, path: str) -> None:
    # Seul endroit du fichier qui appelle GeoDataFrame.to_parquet — les deux
    # chemins publics (write_geoparquet CDC, write_geoparquet_from_relation
    # générique) convergent ici, jamais un writer dupliqué.
    gdf.to_parquet(path)


def write_geoparquet(rows: list[ChangeRow], *, srid: int, path: str) -> None:
    gdf = build_geodataframe(rows, srid=srid)
    _write_gdf(gdf, path)


def build_geodataframe_from_relation(
    relation: "duckdb.DuckDBPyRelation", *, srid: int, geometry_column: str
) -> gpd.GeoDataFrame:
    """Même sortie que build_geodataframe (une gpd.GeoDataFrame) mais lue
    directement depuis une relation DuckDB plutôt qu'un tampon ChangeRow —
    geometry_column est déjà résolue par l'appelant (détection par type
    DuckDB GEOMETRY, cf. app.pipelines.exchange._geometry_column), jamais
    redevinée ici. Décodage WKB brut (pas hex) : ST_AsWKB renvoie des bytes
    Python directement exploitables par shapely.wkb.loads, contrairement au
    chemin CDC qui transporte du hex EWKB (_decode_geometry) — deux
    encodages légitimement différents, pas une divergence à unifier."""
    other_cols = [c for c in relation.columns if c != geometry_column]
    select_list = ", ".join(
        [_qi(c) for c in other_cols] + [f"ST_AsWKB({_qi(geometry_column)}) AS {_qi('__wkb')}"]
    )
    rows = relation.select(select_list).fetchall()
    records = []
    geometries = []
    for row in rows:
        values = dict(zip(other_cols, row[:-1], strict=True))
        wkb = row[-1]
        records.append(values)
        geometries.append(shapely.wkb.loads(bytes(wkb)) if wkb is not None else None)
    crs = f"EPSG:{srid}" if srid else None
    return gpd.GeoDataFrame(records, geometry=geometries, crs=crs)


def write_geoparquet_from_relation(
    relation: "duckdb.DuckDBPyRelation", *, srid: int, geometry_column: str, path: str
) -> None:
    gdf = build_geodataframe_from_relation(relation, srid=srid, geometry_column=geometry_column)
    _write_gdf(gdf, path)
