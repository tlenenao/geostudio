# SPDX-License-Identifier: Apache-2.0
"""Profil exploratoire d'une collection (REV-117 / GAP-23, « X-rays »).

Même source et même réduction à l'état courant que `aggregate` (`_dedup_cte`),
mêmes bornes (budget de temps `statement_timeout`, mémoire/threads
`open_connection`), même masquage GAP-22 (`_valid_column_names` : une colonne
masquée n'est jamais nommée dans le SQL). L'état courant est matérialisé UNE
fois dans une table temporaire `prof` : toutes les statistiques la lisent, le
lac n'est balayé qu'une fois."""

from typing import Any

import duckdb
from pydantic import BaseModel

from app.analytics.aggregate import (
    UnknownAggregateField,
    _dedup_cte,
    _fetch_rows,
    _has_any_file,
    _run_binned_histogram,
    _valid_column_names,
)
from app.analytics.duckdb_conn import StatementTimeout, statement_timeout
from app.collections.introspection import TableInfo
from app.sql_ident import quote_ident_duckdb as _qi

MAX_PROFILE_COLUMNS = 50
PROFILE_SAMPLE_ROWS = 500_000
TOP_VALUES = 5
HISTOGRAM_BINS = 10
MAX_VALUE_CHARS = 200

_NUMERIC = ("integer", "number")
_TOP_TYPES = ("string", "enum", "boolean", "integer")
_COUNT_ONLY = ("list", "unsupported")


class TopValue(BaseModel):
    value: str
    count: int


class HistogramBin(BaseModel):
    bucketIndex: int
    bucketStart: float
    bucketEnd: float
    count: int


class ColumnProfile(BaseModel):
    name: str
    type: str
    nonNull: int
    nulls: int
    distinct: int | None = None
    min: float | str | None = None
    max: float | str | None = None
    mean: float | None = None
    p25: float | None = None
    median: float | None = None
    p75: float | None = None
    topValues: list[TopValue] | None = None
    histogram: list[HistogramBin] | None = None


class GeometryTypeCount(BaseModel):
    type: str
    count: int


class GeometryProfile(BaseModel):
    column: str
    bbox: list[float] | None = None
    types: list[GeometryTypeCount]


class CollectionProfileResponse(BaseModel):
    """Contrat de GET /collections/{id}/profile. `asOf`/`pending` : mêmes
    sémantiques que POST /aggregate (P25.10/11)."""

    rowCount: int
    sampled: bool = False
    truncatedColumns: bool = False
    columns: list[ColumnProfile]
    geometry: GeometryProfile | None = None
    asOf: str | None = None
    pending: bool = False


_ISO = "'%Y-%m-%dT%H:%M:%SZ'"


def _stat_selects(i: int, name: str, type_: str) -> list[str]:
    col = _qi(name)
    sel = [f"COUNT({col}) AS n{i}"]
    if type_ in _COUNT_ONLY:
        return sel
    sel.append(f"COUNT(DISTINCT {col}) AS d{i}")
    if type_ in _NUMERIC:
        x = f"TRY_CAST({col} AS DOUBLE)"
        sel += [
            f"MIN({x}) AS lo{i}",
            f"MAX({x}) AS hi{i}",
            f"AVG({x}) AS avg{i}",
            f"QUANTILE_CONT({x}, 0.25) AS q1_{i}",
            f"QUANTILE_CONT({x}, 0.5) AS q2_{i}",
            f"QUANTILE_CONT({x}, 0.75) AS q3_{i}",
        ]
    elif type_ in ("date", "datetime"):
        x = f"TRY_CAST({col} AS TIMESTAMPTZ) AT TIME ZONE 'UTC'"
        sel += [f"strftime(MIN({x}), {_ISO}) AS lo{i}", f"strftime(MAX({x}), {_ISO}) AS hi{i}"]
    return sel


def run_collection_profile(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    masked_fields: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    try:
        with statement_timeout(conn):
            return _profile(conn, base_uri, tenant_id, collection_id, table_info, masked_fields)
    except StatementTimeout as exc:
        raise UnknownAggregateField("query", str(exc)) from exc


def _profile(
    conn: duckdb.DuckDBPyConnection,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    masked_fields: frozenset[str],
) -> dict[str, Any]:
    empty: dict[str, Any] = {
        "rowCount": 0,
        "sampled": False,
        "truncatedColumns": False,
        "columns": [],
        "geometry": None,
    }
    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return empty
    conn.execute("SET TimeZone='UTC'")
    cte = _dedup_cte(conn, table_info, base_uri, tenant_id, collection_id)
    in_lake = {d[0] for d in conn.execute(f"{cte} SELECT * FROM live LIMIT 0").description}
    valid = _valid_column_names(table_info, masked_fields) & in_lake
    candidates = [
        c for c in table_info.columns if c.name in valid and c.name != table_info.pk_column
    ]
    columns = candidates[:MAX_PROFILE_COLUMNS]
    geom = table_info.geometry_column if table_info.geometry_column in valid else None

    total = int(_fetch_rows(conn, f"{cte} SELECT COUNT(*) AS n FROM live", [])[0]["n"])
    sampled = total > PROFILE_SAMPLE_ROWS
    names = [c.name for c in columns] + ([geom] if geom else [])
    result = {**empty, "rowCount": total, "sampled": sampled}
    result["truncatedColumns"] = len(candidates) > len(columns)
    if total == 0 or not names:
        return result

    sample = f" USING SAMPLE {int(PROFILE_SAMPLE_ROWS)} ROWS" if sampled else ""
    conn.execute(
        f"CREATE OR REPLACE TEMP TABLE prof AS {cte} "
        f"SELECT {', '.join(_qi(n) for n in names)} FROM live{sample}"
    )
    selects: list[str] = []
    for i, c in enumerate(columns):
        selects += _stat_selects(i, c.name, c.type)
    stats = _fetch_rows(conn, f"SELECT {', '.join(selects)} FROM prof", [])[0] if selects else {}
    sample_n = _fetch_rows(conn, "SELECT COUNT(*) AS n FROM prof", [])[0]["n"]

    profiles: list[dict[str, Any]] = []
    for i, c in enumerate(columns):
        non_null = int(stats[f"n{i}"])
        p: dict[str, Any] = {
            "name": c.name,
            "type": c.type,
            "nonNull": non_null,
            "nulls": int(sample_n) - non_null,
        }
        if f"d{i}" in stats:
            p["distinct"] = int(stats[f"d{i}"])
        if f"lo{i}" in stats:
            p["min"], p["max"] = stats[f"lo{i}"], stats[f"hi{i}"]
        if f"avg{i}" in stats:
            p["mean"] = stats[f"avg{i}"]
            p["p25"], p["median"], p["p75"] = stats[f"q1_{i}"], stats[f"q2_{i}"], stats[f"q3_{i}"]
            p["histogram"] = _run_binned_histogram(
                conn,
                dedup_cte="WITH live AS (SELECT * FROM prof)",
                where_sql="",
                where_params=[],
                field=c.name,
                bins=HISTOGRAM_BINS,
            )
        if c.type in _TOP_TYPES and non_null:
            v = f"LEFT(CAST({_qi(c.name)} AS VARCHAR), {MAX_VALUE_CHARS})"
            rows = _fetch_rows(
                conn,
                f"SELECT {v} AS value, COUNT(*) AS count FROM prof "
                f"WHERE {_qi(c.name)} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1 LIMIT {TOP_VALUES}",
                [],
            )
            p["topValues"] = rows
        profiles.append(p)
    result["columns"] = profiles

    if geom:
        g = _qi(geom)
        ext = _fetch_rows(
            conn,
            f"SELECT MIN(ST_XMin({g})) AS x0, MIN(ST_YMin({g})) AS y0, "
            f"MAX(ST_XMax({g})) AS x1, MAX(ST_YMax({g})) AS y1 FROM prof",
            [],
        )[0]
        types = _fetch_rows(
            conn,
            f"SELECT CAST(ST_GeometryType({g}) AS VARCHAR) AS type, COUNT(*) AS count "
            f"FROM prof WHERE {g} IS NOT NULL GROUP BY 1 ORDER BY 2 DESC, 1",
            [],
        )
        bbox = [ext["x0"], ext["y0"], ext["x1"], ext["y1"]]
        result["geometry"] = {
            "column": geom,
            "bbox": None if any(v is None for v in bbox) else bbox,
            "types": types,
        }
    return result
