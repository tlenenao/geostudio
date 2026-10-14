# SPDX-License-Identifier: Apache-2.0
"""`transform.isochrone` et `transform.route` (ARC-34, ADR 0025) : analyse de réseau par ligne
via le client Valhalla du cœur (`app.routing.client` : garde d'egress, plafonds, 503 si service
absent). L'origine d'une ligne = centroïde de sa géométrie (EPSG:4326 attendu : Valhalla ne
parle que WGS84 et l'op ne reçoit pas le SRID d'entrée).

Une ligne sans solution (point hors réseau, pas d'itinéraire) est conservée, géométrie NULL et
`routing_status` = non_trouvé ; service absent/injoignable = le run échoue (jamais de crash
silencieux). Au plus MAX_ROWS lignes par nœud (appels séquentiels : la borne protège Valhalla) ;
l'aperçu n'en traite que PREVIEW_ROWS."""

import functools
import json
import threading
from typing import Literal

import pandas as pd
from pydantic import BaseModel, Field

from app.audit.writer import write_audit
from app.pipelines.errors import PipelineRuntimeError
from app.routing.client import (
    RateLimited,
    RoutingError,
    RoutingUnavailable,
    Valhalla,
    get_routing,
    rate_window,
)
from app.routing.gate import can_route
from app.sql_ident import quote_ident_duckdb as _qi

MAX_ROWS = 500  # lignes par nœud ; avec <= 4 contours : <= 2000 lignes de sortie par nœud
PREVIEW_ROWS = 5
RATE_WAIT_S = 600.0  # un run attend un créneau du budget partagé (100/min/utilisateur)
# Concurrence plafonnée : au plus 4 nœuds de routage simultanés par processus worker.
_SLOTS = threading.BoundedSemaphore(4)


def _slotted(fn):
    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        with _SLOTS:
            return fn(*args, **kwargs)

    return wrapper


CostingName = Literal["auto", "bicycle", "pedestrian", "truck", "bus", "motor_scooter"]


class TransformIsochroneParams(BaseModel):
    """Remplace chaque ligne (origine = centroïde de sa géométrie) par un polygone d'accessibilité
    par durée de trajet : une ligne par contour, colonne `contour_minutes`. Pas de solution =
    ligne conservée, géométrie NULL, `routing_status` non_trouvé."""

    minutes: list[float] = Field(..., min_length=1, max_length=4)
    costing: CostingName = "auto"


class TransformRouteParams(BaseModel):
    """Calcule l'itinéraire de l'origine (centroïde de la géométrie) vers la destination donnée
    par deux colonnes lon/lat : la géométrie devient la LineString, avec `route_distance_km` et
    `route_duration_s`. Pas d'itinéraire = géométrie NULL, `routing_status` non_trouvé."""

    destLonColumn: str = Field(..., min_length=1)
    destLatColumn: str = Field(..., min_length=1)
    costing: CostingName = "auto"


def _output_srid(params: dict, *, op: str, input_srid: int, join_srid: int | None = None) -> int:
    return 4326


def _origins(conn, input_view: str, extra: list[str], preview: bool) -> list[tuple]:
    cols = [d[0] for d in conn.execute(f"DESCRIBE {_qi(input_view)}").fetchall()]
    if "geometry" not in cols:
        raise PipelineRuntimeError("transform: input has no 'geometry' column")
    missing = [c for c in extra if c not in cols]
    if missing:
        raise PipelineRuntimeError(f"transform: column(s) not found: {missing}")
    sel = "".join(f", {_qi(c)}" for c in extra)
    # L'aperçu tronque AVANT le plafond : il ne traite que ses PREVIEW_ROWS premières lignes.
    limit = f" LIMIT {PREVIEW_ROWS}" if preview else f" LIMIT {MAX_ROWS + 1}"
    rows = conn.execute(
        f"SELECT row_number() OVER () AS rn, ST_X(ST_Centroid(geometry)), "
        f"ST_Y(ST_Centroid(geometry)){sel} FROM {_qi(input_view)}{limit}"
    ).fetchall()
    if len(rows) > MAX_ROWS:
        raise PipelineRuntimeError(
            f"transform: more than {MAX_ROWS} rows exceed the cap of a routing node"
        )
    return rows


def _authorized_routing(secret_resolver, *, op: str, costing: str, calls: int) -> Valhalla:
    """Même porte que REST/MCP (`can_route`, analytics.view) sur l'acteur du run, une ligne
    d'audit par nœud (commitée avant les appels amont), et chaque requête amont consomme le
    budget partagé `rate_window` (le run attend un créneau plutôt que de saturer Valhalla)."""
    session = getattr(secret_resolver, "session", None)
    user = getattr(secret_resolver, "user", None)
    if session is None or not can_route(session, user):
        raise PipelineRuntimeError(f"{op}: privilège 'analytics.view' requis pour le routage")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="routing.pipeline_op",
        object_type="routing",
        object_id=op,
        payload={"op": op, "costing": costing, "calls": calls},
    )
    session.commit()
    return get_routing(lambda: rate_window.acquire(user.id, RATE_WAIT_S))


def row_dest(row: tuple) -> tuple:
    return row[3], row[4]


def _origin(row: tuple) -> dict | None:
    return None if row[1] is None or row[2] is None else {"lon": row[1], "lat": row[2]}


def _materialize(
    conn,
    *,
    input_view: str,
    view_name: str,
    results: list[dict],
    extra_cols: list[str],
    inner_join: bool,
) -> None:
    clash = [c for c in (*extra_cols, "routing_status") if c in _columns(conn, input_view)]
    if clash:
        raise PipelineRuntimeError(f"transform: input already has column(s) {clash}")
    frame = pd.DataFrame(results, columns=["rn", "geom", "routing_status", *extra_cols])
    conn.register("_routing_results", frame)
    try:
        extra_sql = "".join(f", r.{_qi(c)}" for c in extra_cols)
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT s.* EXCLUDE (geometry, _rn), ST_GeomFromGeoJSON(r.geom) AS geometry, "
            f"r.routing_status{extra_sql} "
            f"FROM (SELECT *, row_number() OVER () AS _rn FROM {_qi(input_view)}) s "
            f"{'JOIN' if inner_join else 'LEFT JOIN'} _routing_results r ON r.rn = s._rn"
        )
    finally:
        conn.unregister("_routing_results")


def _columns(conn, view: str) -> list[str]:
    return [d[0] for d in conn.execute(f"DESCRIBE {_qi(view)}").fetchall()]


@_slotted
def execute_isochrone(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
    input_srid: int | None = None,
) -> None:
    p = TransformIsochroneParams.model_validate(params)
    rows = _origins(conn, input_view, [], preview)
    results: list[dict] = []
    try:
        routing = _authorized_routing(
            secret_resolver,
            op="transform.isochrone",
            costing=p.costing,
            calls=sum(1 for r in rows if _origin(r) is not None),
        )
        for row in rows:
            origin = _origin(row)
            features = []
            if origin is not None:
                try:
                    features = routing.isochrone(origin, p.minutes, p.costing)["features"]
                except (RoutingError, ValueError):
                    pass
            for f in features:
                results.append(
                    {
                        "rn": row[0],
                        "geom": json.dumps(f["geometry"]),
                        "routing_status": "ok",
                        "contour_minutes": f["properties"]["contour_minutes"],
                    }
                )
            if not features:
                results.append(
                    {
                        "rn": row[0],
                        "geom": None,
                        "routing_status": "non_trouvé",
                        "contour_minutes": None,
                    }
                )
    except RoutingUnavailable as exc:
        raise PipelineRuntimeError(f"transform.isochrone: {exc}") from exc
    except RateLimited as exc:
        raise PipelineRuntimeError("transform.isochrone: budget de routage épuisé") from exc
    _materialize(
        conn,
        input_view=input_view,
        view_name=view_name,
        results=results,
        extra_cols=["contour_minutes"],
        inner_join=preview,
    )


@_slotted
def execute_route(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
    input_srid: int | None = None,
) -> None:
    p = TransformRouteParams.model_validate(params)
    rows = _origins(conn, input_view, [p.destLonColumn, p.destLatColumn], preview)
    results: list[dict] = []
    try:
        routing = _authorized_routing(
            secret_resolver,
            op="transform.route",
            costing=p.costing,
            calls=sum(1 for r in rows if _origin(r) is not None and None not in row_dest(r)),
        )
        for row in rows:
            origin = _origin(row)
            res = None
            if origin is not None and row[3] is not None and row[4] is not None:
                try:
                    res = routing.route([origin, {"lon": row[3], "lat": row[4]}], p.costing)
                except (RoutingError, ValueError):
                    pass
            results.append(
                {
                    "rn": row[0],
                    "geom": json.dumps(res["geometry"]) if res else None,
                    "routing_status": "ok" if res else "non_trouvé",
                    "route_distance_km": res["distance_km"] if res else None,
                    "route_duration_s": res["duration_s"] if res else None,
                }
            )
    except RoutingUnavailable as exc:
        raise PipelineRuntimeError(f"transform.route: {exc}") from exc
    except RateLimited as exc:
        raise PipelineRuntimeError("transform.route: budget de routage épuisé") from exc
    _materialize(
        conn,
        input_view=input_view,
        view_name=view_name,
        results=results,
        extra_cols=["route_distance_km", "route_duration_s"],
        inner_join=preview,
    )
