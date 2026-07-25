# SPDX-License-Identifier: Apache-2.0
"""Module analytique DuckDB (SP-11b, A18/A19) : agrège les données d'une
collection depuis son GeoParquet CDC (SP-11a), au lieu de fetcher les
features brutes et d'agréger côté client (aggregateRecords, supprimé côté
shell par ce plan). Réduction à l'état courant PUIS filtres PUIS group-by/
mesures, dans cet ordre — jamais l'inverse (un filtre appliqué avant
réduction pourrait retenir une ligne déjà remplacée par une version plus
récente).

Incantation bbox : le spike Task 1 a déterminé empiriquement (contre un
vrai GeoParquet sur MinIO) que DuckDB lit la colonne géométrie d'un
GeoParquet directement comme un type GEOMETRY natif — ST_GeomFromWKB(...)
n'est ni nécessaire ni correct ici (le plan présumait par défaut un WKB
brut nécessitant conversion, corrigé après coup par le spike)."""
from pydantic import BaseModel


class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None


class AggregateRequestBody(BaseModel):
    groupBy: str | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None


class UnknownAggregateField(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


def _qi(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sql_lit(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


_RANGE_OPS = {"__gte": ">=", "__lte": "<="}


def _split_filter_key(raw_name: str) -> tuple[str, str | None]:
    if raw_name.endswith("__in"):
        return raw_name[: -len("__in")], "__in"
    for suffix in _RANGE_OPS:
        if raw_name.endswith(suffix):
            return raw_name[: -len(suffix)], suffix
    return raw_name, None


def _valid_column_names(table_info) -> set[str]:
    names = {c.name for c in table_info.columns} | {table_info.pk_column}
    if table_info.geometry_column:
        names.add(table_info.geometry_column)
    return names


def _validate_fields(request: AggregateRequestBody, table_info) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    check(request.groupBy, "groupBy")
    check(request.split, "split")
    check(request.field, "field")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
    for raw_name in request.filters:
        field_name, _ = _split_filter_key(raw_name)
        check(field_name, f"filters.{raw_name}")
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")


def _agg_expr(agg: str, field: str | None) -> str:
    if agg == "count":
        return "COUNT(*)"
    if field is None:
        raise UnknownAggregateField("field", f"agg '{agg}' requires a field")
    col = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    if agg == "sum":
        return f"COALESCE(SUM({col}), 0)"
    if agg == "avg":
        return f"COALESCE(AVG({col}), 0)"
    if agg == "min":
        return f"COALESCE(MIN({col}), 0)"
    if agg == "max":
        return f"COALESCE(MAX({col}), 0)"
    raise UnknownAggregateField("agg", f"unknown agg '{agg}'")


def _measure_label(m: AggregateMeasure) -> str:
    return m.label or (f"{m.agg}_{m.field}" if m.field else m.agg)


def _measures_for(request: AggregateRequestBody) -> list[AggregateMeasure]:
    if request.measures:
        return request.measures
    return [AggregateMeasure(field=request.field, agg=request.agg, label="value")]


def _build_where(request: AggregateRequestBody, table_info) -> tuple[str, list]:
    clauses = []
    params: list = []
    for raw_name, value in request.filters.items():
        name, suffix = _split_filter_key(raw_name)
        if suffix == "__in":
            values = value.split(",")
            clauses.append(f"{_qi(name)} IN ({', '.join('?' for _ in values)})")
            params.extend(values)
        elif suffix in _RANGE_OPS:
            clauses.append(f"{_qi(name)} {_RANGE_OPS[suffix]} ?")
            params.append(value)
        else:
            clauses.append(f"{_qi(name)} = ?")
            params.append(value)
    if request.bbox is not None:
        minx, miny, maxx, maxy = request.bbox
        # Native GEOMETRY : la colonne géométrie du GeoParquet CDC est déjà
        # lue par DuckDB comme un type GEOMETRY (spike Task 1, vérifié
        # contre MinIO réel) — pas de ST_GeomFromWKB(...) ici.
        clauses.append(
            f"ST_Intersects({_qi(table_info.geometry_column)}, "
            f"ST_MakeEnvelope(?, ?, ?, ?))"
        )
        params.extend([minx, miny, maxx, maxy])
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _pivot_split(sql_rows: list[dict], *, category_key: str) -> list[dict]:
    categories: list[str] = []
    by_cat: dict[str, dict] = {}
    splits: list[str] = []
    seen_splits: set[str] = set()
    for r in sql_rows:
        cat = str(r["__cat"])
        if cat not in by_cat:
            by_cat[cat] = {category_key: cat}
            categories.append(cat)
        sv = str(r["__split"])
        if sv not in seen_splits:
            seen_splits.add(sv)
            splits.append(sv)
        by_cat[cat][sv] = r["__val"]
    for cat in categories:
        row = by_cat[cat]
        for sv in splits:
            row.setdefault(sv, 0)
    return [by_cat[c] for c in categories]


def _pivot_measures(sql_rows: list[dict], *, category_key: str, measures: list[AggregateMeasure]) -> list[dict]:
    out = []
    for r in sql_rows:
        row = {category_key: str(r["__cat"])}
        for i, m in enumerate(measures):
            row[_measure_label(m)] = r[f"m{i}"]
        out.append(row)
    return out


def _dedup_cte(table_info, base_uri: str, tenant_id: str, collection_id: str) -> str:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    pk = _qi(table_info.pk_column)
    return (
        f"WITH raw AS (SELECT * FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true)), "
        f"current AS (SELECT * FROM raw QUALIFY row_number() OVER "
        f"(PARTITION BY {pk} ORDER BY _lsn DESC) = 1), "
        f"live AS (SELECT * FROM current WHERE _op != 'delete')"
    )


def _has_any_file(conn, base_uri: str, tenant_id: str, collection_id: str) -> bool:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _fetch_rows(conn, sql: str, params: list) -> list[dict]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r)) for r in result]


def run_collection_aggregate(
    conn, *, base_uri: str, tenant_id: str, collection_id: str, table_info, request: AggregateRequestBody,
) -> tuple[str, list[dict]]:
    category_key = request.groupBy or "group"
    _validate_fields(request, table_info)

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)
    cat_expr = _qi(request.groupBy) if request.groupBy else "'Total'"

    if request.split:
        agg_sql = _agg_expr(request.agg, request.field)
        sql = (
            f"{dedup_cte} SELECT {cat_expr} AS __cat, {_qi(request.split)} AS __split, "
            f"{agg_sql} AS __val FROM live {where_sql} GROUP BY __cat, __split"
        )
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_split(sql_rows, category_key=category_key)

    measures = _measures_for(request)
    measure_cols = ", ".join(f"{_agg_expr(m.agg, m.field)} AS m{i}" for i, m in enumerate(measures))
    sql = f"{dedup_cte} SELECT {cat_expr} AS __cat, {measure_cols} FROM live {where_sql} GROUP BY __cat"
    sql_rows = _fetch_rows(conn, sql, where_params)
    return category_key, _pivot_measures(sql_rows, category_key=category_key, measures=measures)
