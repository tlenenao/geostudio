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

import json
from typing import Any, Literal

import duckdb
from pydantic import BaseModel

from app.collections.introspection import TableInfo
from app.sql_ident import quote_ident_duckdb as _qi


class AggregateMeasure(BaseModel):
    field: str | None = None
    agg: str = "count"
    label: str | None = None
    # Centile demandé, en POURCENTAGE (0 < p < 100), pas en fraction.
    # Obligatoire pour agg="percentile", refusé pour tout autre agg
    # (_validate_p ci-dessous). La division par 100 se fait dans _agg_expr.
    p: float | None = None


class AggregateRequestBody(BaseModel):
    groupBy: str | list[str] | None = None
    split: str | None = None
    agg: str = "count"
    field: str | None = None
    p: float | None = None
    measures: list[AggregateMeasure] | None = None
    filters: dict[str, str] = {}
    bbox: tuple[float, float, float, float] | None = None
    geomIntersects: dict[str, Any] | None = None
    bucket: Literal["hour", "day", "week", "month", "quarter", "year"] | None = None
    bins: int | None = None
    sample: int | None = None


class UnknownAggregateField(Exception):
    def __init__(self, field: str, message: str):
        self.field = field
        self.message = message
        super().__init__(message)


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


# REV-014 : app.features.tiles::_EXCLUDED_PROPERTIES exclut déjà "tenant_id"
# (colonne interne, jamais un champ métier) — même exclusion ici, mais
# redéfinie localement plutôt qu'importée : `app.analytics` est au plus bas
# du contrat de couches (pyproject.toml), `app.features` est placé au-dessus,
# un import irait donc dans le mauvais sens.
_EXCLUDED_PROPERTIES = frozenset({"tenant_id"})


def _valid_column_names(table_info: TableInfo) -> set[str]:
    names = {c.name for c in table_info.columns} | {table_info.pk_column}
    if table_info.geometry_column:
        names.add(table_info.geometry_column)
    return names - _EXCLUDED_PROPERTIES


def _groupby_fields(request: AggregateRequestBody) -> list[str]:
    if not request.groupBy:
        return []
    return request.groupBy if isinstance(request.groupBy, list) else [request.groupBy]


def _validate_p(agg: str, p: float | None, label: str) -> None:
    if agg == "percentile":
        if p is None:
            raise UnknownAggregateField(label, "agg 'percentile' requires p")
        if not (0 < p < 100):
            raise UnknownAggregateField(label, "p must be strictly between 0 and 100")
    elif p is not None:
        raise UnknownAggregateField(label, f"agg '{agg}' does not accept p")


def _validate_fields(request: AggregateRequestBody, table_info: TableInfo) -> None:
    valid = _valid_column_names(table_info)

    def check(name: str | None, label: str) -> None:
        if name is not None and name not in valid:
            raise UnknownAggregateField(label, f"unknown field '{name}'")

    fields = _groupby_fields(request)
    if len(fields) != len(set(fields)):
        raise UnknownAggregateField("groupBy", "duplicate field in groupBy")
    for f in fields:
        check(f, "groupBy")

    if request.bucket is not None and len(fields) != 1:
        raise UnknownAggregateField("bucket", "bucket requires a single-field groupBy")
    if request.split and len(fields) > 1:
        raise UnknownAggregateField("split", "split cannot combine with a multi-field groupBy")

    check(request.split, "split")
    check(request.field, "field")
    # request.agg/request.field/request.p restent utilisés même quand
    # `measures` est renseigné : le chemin `split` de
    # run_collection_aggregate les lit directement. Les deux niveaux se
    # valident donc toujours, pas l'un ou l'autre.
    _validate_p(request.agg, request.p, "p")
    for i, m in enumerate(request.measures or []):
        check(m.field, f"measures[{i}].field")
        _validate_p(m.agg, m.p, f"measures[{i}].p")
    for raw_name in request.filters:
        field_name, _ = _split_filter_key(raw_name)
        check(field_name, f"filters.{raw_name}")
    if request.bbox is not None and not table_info.geometry_column:
        raise UnknownAggregateField("bbox", "collection has no geometry")
    if request.geomIntersects is not None and not table_info.geometry_column:
        raise UnknownAggregateField("geomIntersects", "collection has no geometry")

    if request.bins is not None:
        if request.field is None:
            raise UnknownAggregateField("bins", "bins requires a field")
        if fields:
            raise UnknownAggregateField("bins", "bins cannot combine with groupBy")
        if not (1 <= request.bins <= 100):
            raise UnknownAggregateField("bins", "bins must be between 1 and 100")

    if request.sample is not None:
        if request.field is None:
            raise UnknownAggregateField("sample", "sample requires a field")
        if fields:
            raise UnknownAggregateField("sample", "sample cannot combine with groupBy")
        if request.bins is not None:
            raise UnknownAggregateField("sample", "sample cannot combine with bins")
        if not (1 <= request.sample <= 2000):
            raise UnknownAggregateField("sample", "sample must be between 1 and 2000")


def _agg_expr(agg: str, field: str | None, p: float | None = None) -> str:
    if agg == "count":
        return "COUNT(*)"
    if field is None:
        raise UnknownAggregateField("field", f"agg '{agg}' requires a field")
    if agg == "countDistinct":
        # Pas de TRY_CAST ici, contrairement aux agrégats numériques :
        # compter des valeurs textuelles distinctes est légitime, et un cast
        # en DOUBLE les fusionnerait toutes sur NULL (donc 0 distinct).
        return f"COALESCE(COUNT(DISTINCT {_qi(field)}), 0)"
    col = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    # Indéfini n'est PAS zéro (design §3.1) : pas de COALESCE sur sum/avg/
    # min/max non plus — un groupe sans aucune valeur castable (filtre vide,
    # champ texte) doit rendre null comme median/percentile/stddev
    # ci-dessous, sur le même fondement (« renvoyer 0 produirait un
    # graphique faux plutôt qu'un trou »), pas 0 (valeur réelle possible,
    # indistinguable d'une absence de donnée pour un consommateur — légende
    # de symbologie classée min/max, graphique sur un sous-ensemble vide).
    if agg == "sum":
        return f"SUM({col})"
    if agg == "avg":
        return f"AVG({col})"
    if agg == "min":
        return f"MIN({col})"
    if agg == "max":
        return f"MAX({col})"
    if agg == "median":
        return f"QUANTILE_CONT({col}, 0.5)"
    if agg == "percentile":
        # _validate_p a déjà garanti la présence et les bornes de p
        # (appelé par _validate_fields, avant tout appel à _agg_expr).
        assert p is not None
        return f"QUANTILE_CONT({col}, {p / 100.0!r})"
    if agg == "stddev":
        # SAMP (n-1) et non POP : parité visée avec le statisticType
        # "stddev" d'ArcGIS (cf. spec §3.1, parité affirmée non mesurée).
        return f"STDDEV_SAMP({col})"
    raise UnknownAggregateField("agg", f"unknown agg '{agg}'")


def _measure_label(m: AggregateMeasure) -> str:
    """Libellé de colonne d'une mesure, dérivé quand l'auteur n'en donne pas.

    `p` fait partie de l'identité d'une mesure `percentile` : sans lui dans le
    libellé, deux centiles du même champ collisionnent et le pivot en perd un
    silencieusement (revue finale SP-23, I1). Les huit autres agrégats gardent
    le libellé historique `{agg}_{field}`.

    Site unique : `app.harvest.routes` et `app.mcp.tools` importent cette
    fonction plutôt que de redériver le libellé, pour que les trois surfaces
    d'agrégat produisent exactement la même clé de ligne.
    """
    if m.label:
        return m.label
    agg = f"{m.agg}{m.p:g}" if m.agg == "percentile" and m.p is not None else m.agg
    return f"{agg}_{m.field}" if m.field else agg


def _measures_for(request: AggregateRequestBody) -> list[AggregateMeasure]:
    if request.measures:
        return request.measures
    return [AggregateMeasure(field=request.field, agg=request.agg, label="value", p=request.p)]


def _build_where(request: AggregateRequestBody, table_info: TableInfo) -> tuple[str, list[Any]]:
    clauses = []
    params: list[Any] = []
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
        # _validate_fields refuse déjà bbox sans colonne géométrie (appelé
        # avant _build_where par le seul appelant, run_collection_aggregate)
        # — narrowing explicite, pas une nouvelle règle.
        assert table_info.geometry_column is not None
        # Native GEOMETRY : la colonne géométrie du GeoParquet CDC est déjà
        # lue par DuckDB comme un type GEOMETRY (spike Task 1, vérifié
        # contre MinIO réel) — pas de ST_GeomFromWKB(...) ici.
        clauses.append(
            f"ST_Intersects({_qi(table_info.geometry_column)}, ST_MakeEnvelope(?, ?, ?, ?))"
        )
        params.extend([minx, miny, maxx, maxy])
    if request.geomIntersects is not None:
        # Même invariant que ci-dessus, pour geomIntersects.
        assert table_info.geometry_column is not None
        # SP-14n : intersection géométrique exacte, complément précis du bbox
        # ci-dessus (rectangle). Même colonne, même opérateur ST_Intersects —
        # seule la forme du second argument change (GeoJSON arbitraire, pas
        # une enveloppe rectangulaire).
        clauses.append(f"ST_Intersects({_qi(table_info.geometry_column)}, ST_GeomFromGeoJSON(?))")
        params.append(json.dumps(request.geomIntersects))
    return (f"WHERE {' AND '.join(clauses)}" if clauses else ""), params


def _pivot_split(sql_rows: list[dict[str, Any]], *, category_key: str) -> list[dict[str, Any]]:
    categories: list[str] = []
    by_cat: dict[str, dict[str, Any]] = {}
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


def _pivot_measures(
    sql_rows: list[dict[str, Any]], *, category_key: str, measures: list[AggregateMeasure]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in sql_rows:
        row: dict[str, Any] = {category_key: str(r["__cat"])}
        for i, m in enumerate(measures):
            row[_measure_label(m)] = r[f"m{i}"]
        out.append(row)
    return out


def _pivot_multi_measures(
    sql_rows: list[dict[str, Any]], *, fields: list[str], measures: list[AggregateMeasure]
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for r in sql_rows:
        row: dict[str, Any] = {f: r[f] for f in fields}
        for i, m in enumerate(measures):
            row[_measure_label(m)] = r[f"m{i}"]
        out.append(row)
    return out


def _run_binned_histogram(
    conn: duckdb.DuckDBPyConnection,
    *,
    dedup_cte: str,
    where_sql: str,
    where_params: list[Any],
    field: str,
    bins: int,
) -> list[dict[str, Any]]:
    field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    minmax_sql = (
        f"{dedup_cte} SELECT MIN({field_expr}) AS lo, MAX({field_expr}) AS hi FROM live {where_sql}"
    )
    minmax_rows = _fetch_rows(conn, minmax_sql, where_params)
    lo = minmax_rows[0]["lo"] if minmax_rows else None
    hi = minmax_rows[0]["hi"] if minmax_rows else None
    if lo is None or hi is None:
        return []

    not_null_clause = f"{field_expr} IS NOT NULL"
    full_where = f"{where_sql} AND {not_null_clause}" if where_sql else f"WHERE {not_null_clause}"

    if lo == hi:
        sql = f"{dedup_cte} SELECT COUNT(*) AS __val FROM live {full_where}"
        rows = _fetch_rows(conn, sql, where_params)
        return [{"bucketIndex": 0, "bucketStart": lo, "bucketEnd": hi, "count": rows[0]["__val"]}]

    width = (hi - lo) / bins
    bucket_expr = f"LEAST(? - 1, CAST(FLOOR(({field_expr} - ?) / ?) AS INTEGER))"
    sql = (
        f"{dedup_cte} SELECT {bucket_expr} AS __bucket, COUNT(*) AS __val "
        f"FROM live {full_where} GROUP BY __bucket ORDER BY __bucket"
    )
    params = [bins, lo, width, *where_params]
    rows = _fetch_rows(conn, sql, params)
    return [
        {
            "bucketIndex": int(r["__bucket"]),
            "bucketStart": lo + r["__bucket"] * width,
            "bucketEnd": lo + (r["__bucket"] + 1) * width,
            "count": r["__val"],
        }
        for r in rows
    ]


def _run_sample(
    conn: duckdb.DuckDBPyConnection,
    *,
    dedup_cte: str,
    where_sql: str,
    where_params: list[Any],
    field: str,
    sample: int,
) -> list[dict[str, Any]]:
    field_expr = f"TRY_CAST({_qi(field)} AS DOUBLE)"
    # NOTE: The NOT NULL filter below excludes rows where TRY_CAST fails (returns NULL),
    # e.g. if a column contains non-numeric text. This path is currently untested because
    # test fixtures (geopandas/pyarrow) cannot create parquet files with mixed numeric
    # and non-numeric values in the same typed column. The filter is proven by code review
    # and is functionally correct, but lacks empirical test coverage. (See the renamed test
    # test_sample_returns_everything_when_more_requested_than_available for context.)
    not_null_clause = f"{field_expr} IS NOT NULL"
    full_where = f"{where_sql} AND {not_null_clause}" if where_sql else f"WHERE {not_null_clause}"
    sql = (
        f"{dedup_cte} SELECT {field_expr} AS value FROM live {full_where} "
        f"USING SAMPLE {int(sample)} ROWS"
    )
    return _fetch_rows(conn, sql, where_params)


def _has_seq_column(conn: duckdb.DuckDBPyConnection, glob: str, *, union_by_name: bool) -> bool:
    """Un GeoParquet écrit avant l'ajout de la colonne `_seq` (tie-break de
    _dedup_cte ci-dessous) ne l'a pas. Si AUCUN fichier du glob ne la porte
    (collection restée inactive depuis avant ce correctif), union_by_name=true
    ne suffit pas : la colonne est alors absente du schéma tout court, et y
    référer dans la CTE échouerait à la liaison (BinderException), pas
    seulement renvoyer NULL. Vérifié à l'exécution plutôt que supposé."""
    cols = conn.execute(
        f"SELECT * FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true, "
        f"union_by_name={str(union_by_name).lower()}) LIMIT 0"
    ).description
    return any(c[0] == "_seq" for c in cols)


def _dedup_cte(
    conn: duckdb.DuckDBPyConnection,
    table_info: TableInfo,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
) -> str:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    pk = _qi(table_info.pk_column)
    # `_seq` départage un `_lsn` ex-aequo par l'ORDRE D'AJOUT réel au buffer
    # CDC (cf. app.cdc.consumer:54-70, app.cdc.buffer.CdcBufferManager.add) :
    # le settle CDC peut tagger deux transactions distinctes avec la même
    # LSN, et sans ce départage row_number() résolvait l'ex-aequo à la
    # première ligne rencontrée par DuckDB — pas nécessairement la plus
    # récente — servant silencieusement une valeur périmée. union_by_name=true
    # tolère un mélange de fichiers écrits avant/après l'ajout de `_seq` dans
    # la même collection (sans lui, un glob à schémas hétérogènes échoue
    # purement et simplement) ; COALESCE(_seq, -1) traite une ligne sans
    # `_seq` comme la plus ancienne possible, jamais pire que l'arbitraire
    # d'avant ce correctif. Si AUCUN fichier de la collection ne porte encore
    # `_seq` (collection inactive depuis avant ce correctif), la colonne est
    # absente du schéma tout court : retomber sur `_lsn` seul plutôt que de
    # référencer une colonne qui n'existe nulle part (échouerait à la liaison).
    has_seq = _has_seq_column(conn, glob, union_by_name=True)
    order_by = "_lsn DESC, COALESCE(_seq, -1) DESC" if has_seq else "_lsn DESC"
    return (
        f"WITH raw AS (SELECT * FROM read_parquet({_sql_lit(glob)}, hive_partitioning=true, "
        f"union_by_name=true)), "
        f"current AS (SELECT * FROM raw QUALIFY row_number() OVER "
        f"(PARTITION BY {pk} ORDER BY {order_by}) = 1), "
        f"live AS (SELECT * FROM current WHERE _op != 'delete')"
    )


def _has_any_file(
    conn: duckdb.DuckDBPyConnection, base_uri: str, tenant_id: str, collection_id: str
) -> bool:
    glob = f"{base_uri}/tenant_id={tenant_id}/collection_id={collection_id}/dt=*/*.parquet"
    matched = conn.execute(f"SELECT file FROM glob({_sql_lit(glob)})").fetchall()
    return len(matched) > 0


def _fetch_rows(
    conn: duckdb.DuckDBPyConnection, sql: str, params: list[Any]
) -> list[dict[str, Any]]:
    result = conn.execute(sql, params).fetchall()
    cols = [d[0] for d in conn.description]
    return [dict(zip(cols, r, strict=True)) for r in result]


def run_collection_aggregate(
    conn: duckdb.DuckDBPyConnection,
    *,
    base_uri: str,
    tenant_id: str,
    collection_id: str,
    table_info: TableInfo,
    request: AggregateRequestBody,
) -> tuple[str | list[str], list[dict[str, Any]]]:
    fields = _groupby_fields(request)
    _validate_fields(request, table_info)

    # Déterminer le category_key à retourner en cas de collection vide.
    # Ce choix doit refléter le chemin d'exécution choisi par la validation.
    if request.sample is not None:
        category_key: str | list[str] = "value"
    elif request.bins is not None:
        category_key = "bucketIndex"
    else:
        category_key = fields if len(fields) > 1 else (fields[0] if fields else "group")

    if not _has_any_file(conn, base_uri, tenant_id, collection_id):
        return category_key, []

    dedup_cte = _dedup_cte(conn, table_info, base_uri, tenant_id, collection_id)
    where_sql, where_params = _build_where(request, table_info)

    if request.bins is not None:
        # _validate_fields a déjà refusé bins sans field (voir plus haut) —
        # narrowing explicite pour le vérificateur de types, pas une
        # nouvelle règle.
        assert request.field is not None
        rows = _run_binned_histogram(
            conn,
            dedup_cte=dedup_cte,
            where_sql=where_sql,
            where_params=where_params,
            field=request.field,
            bins=request.bins,
        )
        return "bucketIndex", rows

    if request.sample is not None:
        assert request.field is not None
        rows = _run_sample(
            conn,
            dedup_cte=dedup_cte,
            where_sql=where_sql,
            where_params=where_params,
            field=request.field,
            sample=request.sample,
        )
        return "value", rows

    if len(fields) > 1:
        measures = _measures_for(request)
        measure_cols = ", ".join(
            f"{_agg_expr(m.agg, m.field, m.p)} AS m{i}" for i, m in enumerate(measures)
        )
        group_cols = ", ".join(_qi(f) for f in fields)
        sql = (
            f"{dedup_cte} SELECT {group_cols}, {measure_cols} "
            f"FROM live {where_sql} GROUP BY {group_cols}"
        )
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_multi_measures(sql_rows, fields=fields, measures=measures)

    single_field = fields[0] if fields else None
    if request.bucket:
        # _validate_fields exige déjà exactement un groupBy quand bucket est
        # posé (voir plus haut) — narrowing explicite, pas une nouvelle règle.
        assert single_field is not None
        # TRY_CAST(... AS TIMESTAMP) (naïf) jetterait silencieusement l'offset
        # d'une chaîne TIMESTAMPTZ-like (vérifié empiriquement contre duckdb
        # 1.5.5 : trois offsets différents produisent la même valeur naïve) —
        # deux lignes représentant le même instant réel avec des offsets
        # différents (backfill._pg_timestamp_str / wal2json écrivent
        # l'offset natif Postgres) finiraient dans deux buckets distincts.
        # Cast en TIMESTAMPTZ (qui interprète l'offset) puis normalisation
        # explicite en UTC avant DATE_TRUNC. Le TimeZone GUC de session pilote
        # l'interprétation d'une chaîne SANS offset (une colonne TIMESTAMP
        # nue) lors de ce cast — DuckDB l'assume par défaut au fuseau LOCAL de
        # la machine serveur (vérifié empiriquement : Europe/Paris ici),
        # jamais UTC ; sans le fixer explicitement, le bucket d'une colonne
        # TIMESTAMP nue dépendrait silencieusement du fuseau du serveur qui
        # exécute la requête. Fixé à UTC pour que ce cast soit un no-op sur
        # une chaîne sans offset (comportement inchangé) et normalise
        # correctement une chaîne avec offset (le correctif visé).
        conn.execute("SET TimeZone='UTC'")
        cat_expr = (
            f"DATE_TRUNC({_sql_lit(request.bucket)}, "
            f"TRY_CAST({_qi(single_field)} AS TIMESTAMPTZ) AT TIME ZONE 'UTC')"
        )
    else:
        cat_expr = _qi(single_field) if single_field else "'Total'"

    if request.split:
        agg_sql = _agg_expr(request.agg, request.field, request.p)
        sql = (
            f"{dedup_cte} SELECT {cat_expr} AS __cat, {_qi(request.split)} AS __split, "
            f"{agg_sql} AS __val FROM live {where_sql} GROUP BY __cat, __split"
        )
        sql_rows = _fetch_rows(conn, sql, where_params)
        return category_key, _pivot_split(sql_rows, category_key=str(category_key))

    measures = _measures_for(request)
    measure_cols = ", ".join(
        f"{_agg_expr(m.agg, m.field, m.p)} AS m{i}" for i, m in enumerate(measures)
    )
    sql = (
        f"{dedup_cte} SELECT {cat_expr} AS __cat, {measure_cols} "
        f"FROM live {where_sql} GROUP BY __cat"
    )
    sql_rows = _fetch_rows(conn, sql, where_params)
    return category_key, _pivot_measures(
        sql_rows, category_key=str(category_key), measures=measures
    )
