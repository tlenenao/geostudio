# SPDX-License-Identifier: Apache-2.0
"""Famille Filtering (ARC vague 4, voie M, F8) : testFilter, sampler, neighborFinder.

Le modèle de pipeline n'a pas de ports de sortie nommés (une arête part d'un nœud, pas d'un
port) : le « passed/failed » de FME se modélise par deux nœuds `testFilter` aux mêmes tests,
l'un `output="passed"`, l'autre `output="failed"` — ils partitionnent l'entrée."""

from typing import Literal

from pydantic import BaseModel, Field

from app.pipelines.expr_validation import validate_bounded_expr
from app.sql_ident import quote_ident_duckdb as _qi


class TransformTestFilterParams(BaseModel):
    """Garde les lignes qui réussissent (`passed`) ou échouent (`failed`) à des conditions SQL
    booléennes combinées par ET/OU. Une condition NULL compte comme un échec ; avec les mêmes
    tests, `passed` et `failed` partitionnent l'entrée."""

    tests: list[str] = Field(..., min_length=1, max_length=20)
    combine: Literal["and", "or"] = "and"
    output: Literal["passed", "failed"] = "passed"


class TransformSamplerParams(BaseModel):
    """Échantillonne les lignes : les `value` premières (first), une sur `value` (everyNth) ou
    `value` lignes tirées au hasard (random, graine fixe donc reproductible)."""

    mode: Literal["first", "random", "everyNth"] = "first"
    value: int = Field(..., ge=1)
    seed: int = 42


class TransformNeighborFinderParams(BaseModel):
    """Associe à chaque ligne ses `count` plus proches voisines parmi les autres lignes de
    l'entrée (distance en unités du CRS, donc en degrés pour EPSG:4326 — reprojeter avant au
    besoin). Une ligne par couple (ligne, voisine), colonnes `source_index`, `neighbor_index`
    (rang 1-based dans l'entrée), `neighbor_distance`, `neighbor_rank` ; une ligne sans voisine
    (aucune dans `maxDistance`) est conservée avec des valeurs NULL."""

    count: int = Field(1, ge=1, le=100)
    maxDistance: float | None = Field(None, gt=0)


def execute_test_filter(conn, *, input_view: str, view_name: str, params: dict) -> None:
    p = TransformTestFilterParams.model_validate(params)
    for t in p.tests:
        validate_bounded_expr(conn, t)
    joiner = f" {p.combine.upper()} "
    cond = joiner.join(f"coalesce(({t}), false)" for t in p.tests)
    where = cond if p.output == "passed" else f"NOT ({cond})"
    conn.execute(
        f"CREATE TEMP VIEW {_qi(view_name)} AS SELECT * FROM {_qi(input_view)} WHERE {where}"
    )


def compile_sampler(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformSamplerParams.model_validate(params)
    src = _qi(input_view)
    if p.mode == "first":
        return f"SELECT * FROM {src} LIMIT {p.value}"
    if p.mode == "random":
        return f"SELECT * FROM {src} USING SAMPLE reservoir({p.value} ROWS) REPEATABLE ({p.seed})"
    return (
        f'SELECT * EXCLUDE ("__i") FROM (SELECT *, row_number() OVER () AS "__i" FROM {src}) '
        f'WHERE ("__i" - 1) % {p.value} = 0'
    )


def compile_neighbor_finder(
    params: dict, *, input_view: str, join_view: str | None = None, input_srid: int | None = None
) -> str:
    p = TransformNeighborFinderParams.model_validate(params)
    near = (
        f"AND ST_DWithin(a.geometry, c.geometry, {float(p.maxDistance)})"
        if p.maxDistance is not None
        else ""
    )
    # ponytail: produit croisé O(n²) borné par ST_DWithin quand maxDistance est posé ; index
    # spatial (R-tree) si des entrées de plusieurs dizaines de milliers de lignes l'exigent.
    return (
        f'WITH b AS (SELECT *, row_number() OVER () AS "__i" FROM {_qi(input_view)}), '
        f'pairs AS (SELECT a."__i" AS s, c."__i" AS n, ST_Distance(a.geometry, c.geometry) AS d '
        f'FROM b a JOIN b c ON a."__i" <> c."__i" {near}), '
        f"ranked AS (SELECT s, n, d, row_number() OVER (PARTITION BY s ORDER BY d, n) AS r "
        f"FROM pairs) "
        f'SELECT b.* EXCLUDE ("__i"), b."__i" AS source_index, ranked.n AS neighbor_index, '
        f"ranked.d AS neighbor_distance, ranked.r AS neighbor_rank "
        f'FROM b LEFT JOIN ranked ON ranked.s = b."__i" AND ranked.r <= {p.count}'
    )
