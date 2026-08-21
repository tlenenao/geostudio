# SPDX-License-Identifier: Apache-2.0
"""Lecture des features via DuckDB contre un instantané GeoParquet local
(SP-18c) — mirroir de app.features.repository (mêmes noms de fonctions, même
forme de sortie FeatureCollection-ready), mais via SQL DuckDB au lieu de
SQL Postgres paramétré : app.features.repository est Postgres-only,
inutilisable dans le mini-serveur (pas de driver Postgres dans cette
image). Même glob hive-partitionné que app.analytics.aggregate (tenant_id=/
collection_id=/dt=*/*.parquet) — Task 4's write_snapshot écrit exactement
cette disposition."""

import json
from dataclasses import dataclass

from app.collections.introspection import TableInfo


class MissingGeometryColumn(Exception):
    """Raised when a spatial filter (bbox, geom_intersects) is requested
    on a collection with no geometry column."""

    pass


@dataclass(frozen=True)
class FeaturePage:
    features: list[dict]
    number_matched: int
    number_returned: int


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def _glob(base_uri: str, tenant_id: str, collection_id: str) -> str:
    return f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"


def _has_any_file(conn, base_uri: str, tenant_id: str, collection_id: str) -> bool:
    glob = _glob(base_uri, tenant_id, collection_id)
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _property_columns(info: TableInfo) -> list:
    return [
        c for c in info.columns if c.name not in (info.pk_column, "tenant_id", info.geometry_column)
    ]


def _select_list(info: TableInfo) -> str:
    cols = [_qi(info.pk_column)]
    cols += [_qi(c.name) for c in _property_columns(info)]
    if info.geometry_column:
        cols.append(f"ST_AsGeoJSON({_qi(info.geometry_column)}) AS __geo")
    return ", ".join(cols)


def _row_to_feature(info: TableInfo, row: dict) -> dict:
    props = {c.name: row[c.name] for c in _property_columns(info)}
    geometry = None
    if info.geometry_column and row.get("__geo"):
        geometry = json.loads(row["__geo"])
    return {"type": "Feature", "id": row[info.pk_column], "geometry": geometry, "properties": props}


def _fetch_rows(conn, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r, strict=True)) for r in result]


def _build_where(table_info: TableInfo, bbox, geom_intersects) -> tuple[str, list]:
    clauses: list[str] = []
    params: list = []
    if (bbox is not None or geom_intersects is not None) and table_info.geometry_column is None:
        raise MissingGeometryColumn("collection has no geometry column")
    if bbox is not None:
        minx, miny, maxx, maxy = bbox
        clauses.append(
            f"ST_Intersects({_qi(table_info.geometry_column)}, ST_MakeEnvelope(?, ?, ?, ?))"
        )
        params.extend([minx, miny, maxx, maxy])
    if geom_intersects is not None:
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_GeomFromGeoJSON(?))")
        params.append(json.dumps(geom_intersects))
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _coerce_fid(table_info: TableInfo, fid: str):
    pk = next((c for c in table_info.columns if c.name == table_info.pk_column), None)
    if pk is not None and pk.type == "integer":
        try:
            return int(fid)
        except ValueError:
            return None
    return fid


def select_features(
    conn,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    limit: int,
    offset: int,
    bbox=None,
    geom_intersects=None,
) -> FeaturePage:
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return FeaturePage(features=[], number_matched=0, number_returned=0)
    glob = _glob(base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(table_info, bbox, geom_intersects)
    count_sql = (
        f"SELECT COUNT(*) FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) {where_sql}"
    )
    matched = conn.execute(count_sql, where_params).fetchone()[0]
    sql = (
        f"SELECT {_select_list(table_info)} "
        f"FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"{where_sql} ORDER BY {_qi(table_info.pk_column)} LIMIT ? OFFSET ?"
    )
    rows = _fetch_rows(conn, sql, [*where_params, limit, offset])
    features = [_row_to_feature(table_info, r) for r in rows]
    return FeaturePage(features=features, number_matched=matched, number_returned=len(features))


def get_feature(
    conn,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    fid: str,
) -> dict | None:
    value = _coerce_fid(table_info, fid)
    if value is None or not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return None
    glob = _glob(base_uri, tenant_id, collection_id)
    sql = (
        f"SELECT {_select_list(table_info)} "
        f"FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true) "
        f"WHERE {_qi(table_info.pk_column)} = ?"
    )
    rows = _fetch_rows(conn, sql, [value])
    return _row_to_feature(table_info, rows[0]) if rows else None
