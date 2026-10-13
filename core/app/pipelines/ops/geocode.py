# SPDX-License-Identifier: Apache-2.0
"""`transform.geocode` (ARC vague 4, voie M, F11) : colonnes d'adresse -> géométrie Point.

Réutilise le géocodage par lot d'ARC-03 (`app.geocoding.batch.geocode_batch` : concurrence
bornée, cadence plafonnée, jamais d'exception par ligne) et donc la garde d'egress du
géocodage (`app.geocoding.egress`, via `get_geocoder`) : aucune requête n'en sort.

Pas de port « Rejected » dans le modèle de pipeline : les lignes non géocodées sont
conservées, géométrie NULL, `geocode_status` ∈ {trouvé, non_trouvé, erreur, non_traité} — un
`transform.testFilter`/`filter` sur `geocode_status` les route ensuite."""

import time

import pandas as pd
from pydantic import BaseModel, Field

from app.geocoding.batch import MAX_BATCH, BatchBusy, BatchRow, geocode_batch
from app.geocoding.provider import get_geocoder
from app.pipelines.errors import PipelineRuntimeError
from app.sql_ident import quote_ident_duckdb as _qi

MAX_ADDRESSES = 50_000
PREVIEW_ADDRESSES = 50
_BUSY_WAIT_S = 0.5
_BUSY_TRIES = 240
# Surchargeable (tests) ; None = cadence plafonnée partagée de app.geocoding.batch.
_PER_SECOND: float | None = None
_OUT_COLUMNS = ("geometry", "geocode_label", "geocode_status")


class TransformGeocodeParams(BaseModel):
    """Géocode l'adresse formée par la concaténation (séparée par un espace) des colonnes
    `addressColumns` : ajoute une géométrie Point (EPSG:4326), `geocode_label` (libellé
    retourné par le géocodeur) et `geocode_status` (trouvé, non_trouvé, erreur). Les lignes
    non géocodées sont conservées avec une géométrie NULL."""

    addressColumns: list[str] = Field(..., min_length=1, max_length=10)


def _output_srid(params: dict, *, op: str, input_srid: int, join_srid: int | None = None) -> int:
    return 4326


def _geocode_chunk(geocoder, chunk: list[str]) -> list[BatchRow]:
    for _ in range(_BUSY_TRIES):
        try:
            return geocode_batch(geocoder, chunk, per_second=_PER_SECOND)
        except BatchBusy:  # un autre lot tourne dans ce process : on attend son tour
            time.sleep(_BUSY_WAIT_S)
    raise PipelineRuntimeError("transform.geocode: geocoding service busy, try again later")


def execute_geocode(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
) -> None:
    p = TransformGeocodeParams.model_validate(params)
    cols = [d[0] for d in conn.execute(f"DESCRIBE {_qi(input_view)}").fetchall()]
    missing = [c for c in p.addressColumns if c not in cols]
    if missing:
        raise PipelineRuntimeError(f"transform.geocode: column(s) not found: {missing}")
    clash = [c for c in _OUT_COLUMNS if c in cols]
    if clash:
        raise PipelineRuntimeError(f"transform.geocode: input already has column(s) {clash}")

    addr = "trim(concat_ws(' ', {}))".format(
        ", ".join(f"CAST({_qi(c)} AS VARCHAR)" for c in p.addressColumns)
    )
    addresses = [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT {addr} AS a FROM {_qi(input_view)} WHERE {addr} <> '' ORDER BY a"
        ).fetchall()
    ]
    if len(addresses) > MAX_ADDRESSES:
        raise PipelineRuntimeError(
            f"transform.geocode: {len(addresses)} distinct addresses exceed the {MAX_ADDRESSES} cap"
        )
    todo, skipped = (
        (addresses[:PREVIEW_ADDRESSES], addresses[PREVIEW_ADDRESSES:])
        if preview
        else (addresses, [])
    )

    results: dict[str, BatchRow] = {}
    if todo:
        geocoder = get_geocoder()
        pending = todo
        for _ in range(
            2
        ):  # reprise sur échec partiel : les lignes en erreur sont rejouées une fois
            for i in range(0, len(pending), MAX_BATCH):
                for row in _geocode_chunk(geocoder, pending[i : i + MAX_BATCH]):
                    results[row.address] = row
            pending = [a for a in pending if results[a].status == "erreur"]
            if not pending:
                break
        if pending and len(pending) == len(todo):
            raise PipelineRuntimeError(
                "transform.geocode: geocoding failed for every address "
                "(provider unreachable or egress blocked)"
            )
    frame = pd.DataFrame(
        [
            {"g_addr": a, "g_label": r.label, "g_lon": r.lon, "g_lat": r.lat, "g_status": r.status}
            for a, r in results.items()
        ]
        + [
            {"g_addr": a, "g_label": None, "g_lon": None, "g_lat": None, "g_status": "non_traité"}
            for a in skipped
        ],
        columns=["g_addr", "g_label", "g_lon", "g_lat", "g_status"],
    ).astype({"g_label": "object", "g_lon": "float64", "g_lat": "float64"})
    conn.register("_geocode_results", frame)
    try:
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT s.* EXCLUDE (g_key), "
            f"CASE WHEN r.g_lon IS NULL THEN NULL ELSE ST_Point(r.g_lon, r.g_lat) END "
            f"AS geometry, r.g_label AS geocode_label, "
            f"coalesce(r.g_status, 'non_trouvé') AS geocode_status "
            f"FROM (SELECT *, {addr} AS g_key FROM {_qi(input_view)}) s "
            f"LEFT JOIN _geocode_results r ON r.g_addr = s.g_key"
        )
    finally:
        conn.unregister("_geocode_results")
