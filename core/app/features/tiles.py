# SPDX-License-Identifier: Apache-2.0
"""Tuiles vectorielles MVT servies par le cœur (spec SP-24 §3.1).

Pourquoi ici et pas Martin : Martin se connecte en propriétaire des tables,
donc hors RLS, et n'a aucune notion de collection ni de `can()`. Servir le MVT
depuis le cœur donne les trois d'un coup — autorisation, isolation tenant, et
un `collectionId` sur la couche.

Ce module est volontairement coupé en deux : des helpers purs (testés sans
base) et une route mince qui les assemble."""

import functools
import hashlib
import logging
import math
import os
from collections.abc import Callable
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import TableInfo, TableNotFound, hide_sensitive_columns
from app.collections.routes import get_collection_for_read, get_introspector
from app.collections.sensitive import unmask_for_owner
from app.configs.guest_access import GuestActor, get_share_link_actor
from app.db import get_session
from app.features.routes import get_masked_for_user, get_rls_scope
from app.sharing.geo_limits import geo_source
from app.sql_ident import quote_ident

MVT_EXTENT = 4096
MVT_BUFFER = 64
MAX_TILE_ZOOM = 24
MVT_MEDIA_TYPE = "application/vnd.mapbox-vector-tile"
# Bornes de coût d'UNE tuile. La route est atteignable anonymement sur une
# collection publique et n'écrit aucun audit (décision de spec §3.1) : sans
# ces deux bornes, un seul GET .../tiles/0/0/0.mvt sur une collection dense
# scanne et agrège toute la table en une tuile en mémoire, sans trace. Même
# classe de garde que le sandbox SQL analyste (app/analytics/sql_sandbox.py :
# ROW_CAP + STATEMENT_TIMEOUT_S), transposée à Postgres.
#
# 5000 plutôt que les 100 de GET /items (routes.py) : une tuile porte
# légitimement des milliers d'entités là qu'une page de liste en montre
# quelques dizaines ; au-delà, le rendu client décroche de toute façon.
MAX_TILE_FEATURES = 5000
TILE_STATEMENT_TIMEOUT_MS = 10_000
# REV-283a : l'agrégation par cellules lit TOUTES les lignes de l'enveloppe (pas
# de LIMIT, c'est son but) et la route est atteignable anonymement : budget
# dédié, plus court que celui d'une tuile normale. Expiration => 503 +
# Retry-After (une tuile tronquée tromperait : l'agrégat ne se dégrade pas
# en lecture partielle, et le client réessaie).
TILE_AGG_STATEMENT_TIMEOUT_MS = 3_000

logger = logging.getLogger(__name__)

router = APIRouter()

# tenant_id est une colonne réelle de toute table de collection (ddl.py) et
# TableInfo.columns la contient : elle ne doit jamais partir dans une tuile.
_EXCLUDED_PROPERTIES = frozenset({"tenant_id"})


class InvalidTileCoords(Exception):
    pass


def validate_tile_coords(z: int, x: int, y: int) -> None:
    if z < 0 or z > MAX_TILE_ZOOM:
        raise InvalidTileCoords(f"z must be within [0, {MAX_TILE_ZOOM}]")
    limit = 1 << z
    if not (0 <= x < limit) or not (0 <= y < limit):
        raise InvalidTileCoords(f"x and y must be within [0, {limit - 1}] at z={z}")


def mvt_property_columns(info: TableInfo) -> list[str]:
    """TableInfo.columns exclut déjà la colonne de géométrie (introspection_pg)
    mais inclut tenant_id et la PK."""
    return [c.name for c in info.columns if c.name not in _EXCLUDED_PROPERTIES]


def mvt_feature_id_column(info: TableInfo) -> str | None:
    """ST_AsMVT n'accepte un feature_id que sur une colonne entière. On ne le
    passe donc que dans ce cas — le shell retombe sinon sur la propriété de PK."""
    for c in info.columns:
        if c.name == info.pk_column:
            return info.pk_column if c.type == "integer" else None
    return None


def build_mvt_sql(quote: Callable[[str], str], info: TableInfo, src: str | None = None) -> str:
    assert info.geometry_column is not None, "build_mvt_sql exige une géométrie"
    # `src` : élément FROM aliasé `t` fourni par geo_source (géométrie découpée si limité)
    table = src or f"public.{quote(info.table_name)} t"
    geom = f"t.{quote(info.geometry_column)}"
    by_name = {c.name: c for c in info.columns}

    def _projection(name: str) -> str:
        # ST_AsMVT n'accepte que des propriétés scalaires : une colonne "list"
        # (text[]/int[]... introspecté) doit être sérialisée en JSON plutôt que
        # projetée en array brut, que ST_AsMVT ne sait pas encoder.
        ident = quote(name)
        col = by_name.get(name)
        if col is not None and col.type == "list":
            return f"to_jsonb(t.{ident})::text AS {ident}"
        return f"t.{ident} AS {ident}"

    names = mvt_property_columns(info)
    props = ", ".join(_projection(name) for name in names)
    props_clause = f", {props}" if props else ""
    outer_props = "".join(f", raw.{quote(n)}" for n in names)
    # P29.08/09 : LIMIT max+1 DANS la lecture brute, tri déterministe sur la PK
    # (sinon les entités gardées suivent l'ordre physique et changent après un
    # VACUUM/UPDATE). La ligne en trop ne part jamais dans la tuile (LIMIT max externe) :
    # elle sert seulement à prouver qu'il y a eu une vraie omission, donc une
    # collection d'exactement `max` entités n'est plus déclarée tronquée.
    order = f"ORDER BY t.{quote(info.pk_column)}" if info.pk_column else ""
    return (
        "WITH raw AS ("
        f"SELECT ST_AsMVTGeom(ST_Transform({geom}, 3857), "
        "ST_TileEnvelope(:z, :x, :y), :extent, :buffer, true) AS geom"
        f"{props_clause} "
        f"FROM {table} "
        # Le filtre porte sur la géométrie brute pour rester indexable par le
        # GiST posé par apply_collection_ddl : ST_Transform à gauche du && le
        # rendrait inutilisable.
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid) "
        # Plafond DANS la lecture brute : c'est le nombre de lignes lues et
        # transformées qu'il faut borner, pas la sortie de l'agrégat.
        f"{order} LIMIT :max_features + 1"
        ") SELECT (SELECT ST_AsMVT(tile, :layer, :extent, 'geom', :fid) FROM ("
        f"SELECT raw.geom{outer_props} FROM (SELECT * FROM raw LIMIT :max_features) raw "
        "WHERE raw.geom IS NOT NULL"
        ") AS tile), (SELECT count(*) FROM raw)"
    )


def agg_cell_size(z: int) -> float:
    # ponytail: grille de 16 cellules par tuile ; réglable si le rendu est trop grossier
    return 40075016.685578488 / (2**z) / 16


def tile_agg_max_zoom() -> int:
    """REV-283a : zoom max (inclus) sous lequel une tuile dense est agrégée ; 0 désactive.
    Valeur invalide (non entière, négative) : 7 + avertissement, jamais un 500."""
    raw = os.environ.get("CORE_TILE_AGG_MAX_ZOOM", "7")
    try:
        value = int(raw)
        if value >= 0:
            return value
    except ValueError:
        pass
    logger.warning("CORE_TILE_AGG_MAX_ZOOM=%r invalide, repli sur 7", raw)
    return 7


def build_probe_sql(quote: Callable[[str], str], info: TableInfo, src: str | None = None) -> str:
    """Sonde bornée (LIMIT max+1, aucune colonne lue) : « l'enveloppe dépasse-t-elle
    le plafond ? » sans lire ni sérialiser les 5001 lignes de la tuile normale."""
    assert info.geometry_column is not None, "build_probe_sql exige une géométrie"
    geom = f"t.{quote(info.geometry_column)}"
    return (
        f"SELECT count(*) FROM (SELECT 1 FROM {src or f'public.{quote(info.table_name)} t'} "
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid) "
        "LIMIT :max_features + 1) s"
    )


_MERC_R = 6378137.0
_MERC_PER_DEG = 20037508.342789244 / 180
_PI4 = 0.7853981633974483
_AGG_CELLS_TO_MVT = (
    "SELECT point_count, ST_AsMVTGeom("
    "ST_SetSRID(ST_MakePoint((cx + 0.5) * :cell, (cy + 0.5) * :cell), 3857), "
    "ST_TileEnvelope(:z, :x, :y), :extent, :buffer, true) AS geom FROM cells"
)


def build_agg_mvt_sql(quote: Callable[[str], str], info: TableInfo, src: str | None = None) -> str:
    """Cellules `count(*)` d'une tuile dense. Ne projette AUCUNE colonne de
    données (ni valeur masquée GAP-22) : seulement la géométrie et un compte,
    lus sous la même `rls_scope` que la tuile normale (RLS avant agrégation).

    Coût : lit toutes les lignes de l'enveloppe (index GiST, un seul passage),
    d'où le timeout dédié `TILE_AGG_STATEMENT_TIMEOUT_MS`. La cellule émise est
    son CENTRE (floor(x/c)*c + c/2) : une cellule n'appartient qu'à une tuile,
    pas de nœud de grille partagé entre deux voisines."""
    assert info.geometry_column is not None, "build_agg_mvt_sql exige une géométrie"
    table = src or f"public.{quote(info.table_name)} t"
    geom = f"t.{quote(info.geometry_column)}"
    if info.srid == 4326 and info.geometry_type == "Point":
        # REV-283 (E-bis-3) : points WGS84 — la cellule se calcule en Mercator par
        # formule (x linéaire en lon, y = R·ln tan(π/4+φ/2)), sans ST_Transform ni
        # ST_PointOnSurface par ligne ; les centres de cellule sont déjà en 3857.
        return (
            "WITH cells AS ("
            f"SELECT floor(ST_X({geom}) * {_MERC_PER_DEG} / :cell) AS cx, "
            f"floor({_MERC_R} * ln(tan({_PI4} + radians(ST_Y({geom})) / 2)) / :cell) AS cy, "
            "count(*) AS point_count "
            f"FROM {table} "
            f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid) "
            "GROUP BY 1, 2"
            f"), q AS ({_AGG_CELLS_TO_MVT})"
            " SELECT ST_AsMVT(q, :layer, :extent, 'geom') FROM q WHERE q.geom IS NOT NULL"
        )
    return (
        "WITH pts AS ("
        f"SELECT ST_PointOnSurface(ST_Transform({geom}, 3857)) AS p "
        f"FROM {table} "
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)"
        "), cells AS ("
        "SELECT floor(ST_X(p) / :cell) AS cx, floor(ST_Y(p) / :cell) AS cy, "
        "count(*) AS point_count FROM pts GROUP BY 1, 2"
        f"), q AS ({_AGG_CELLS_TO_MVT})"
        " SELECT ST_AsMVT(q, :layer, :extent, 'geom') FROM q WHERE q.geom IS NOT NULL"
    )


# ARC-22 : binning explicite (`?bin=square|hex`), distinct de l'agrégation
# automatique de REV-283a. Il N'ALTÈRE PAS le plafond MAX_TILE_FEATURES (qui borne
# les entités brutes servies) : une tuile binnée ne porte jamais d'entité brute,
# seulement des cellules {point_count, value}, et lit toutes les lignes de
# l'enveloppe sous le budget TILE_AGG_STATEMENT_TIMEOUT_MS (503 si dépassé).
BIN_SHAPES = ("square", "hex")
BIN_STATS = ("count", "sum", "avg")
BIN_NUMERIC_TYPES = ("integer", "number")
_MERC_MAX_LAT = 85.0511287798066
# Hexagone « pointy-top » de rayon 1 (WKT constant, mis à l'échelle en SQL).
_HEX_WKT = (
    "POLYGON(("
    + ",".join(
        f"{math.cos(math.radians(30 + 60 * k)):.12f} {math.sin(math.radians(30 + 60 * k)):.12f}"
        for k in (0, 1, 2, 3, 4, 5, 0)
    )
    + "))"
)


def bin_cell_size(z: int, bins: int) -> float:
    """Côté (carré) ou rayon (hexagone) de cellule : une tuile fait `bins` cellules de large."""
    return 40075016.685578488 / (2**z) / bins


# Bornes de propriété d'une tuile, semi-ouvertes ; les tuiles de bord du monde
# (x/y = 0 ou 2^z - 1) possèdent aussi ce qui dépasse (point à lon = 180, centre
# d'hexagone hors du monde) : sans cela ces comptes ne seraient dans aucune tuile.
_OWN_X = (
    "{c} >= CASE WHEN :x = 0 THEN -1e15 ELSE ST_XMin(e) END AND "
    "{c} < CASE WHEN :x = (1 << CAST(:z AS int)) - 1 THEN 1e15 ELSE ST_XMax(e) END"
)
_OWN_Y = (
    "{c} >= CASE WHEN :y = (1 << CAST(:z AS int)) - 1 THEN -1e15 ELSE ST_YMin(e) END AND "
    "{c} < CASE WHEN :y = 0 THEN 1e15 ELSE ST_YMax(e) END"
)


def _own(cx: str, cy: str) -> str:
    return _OWN_X.format(c=cx) + " AND " + _OWN_Y.format(c=cy)


def build_bin_mvt_sql(
    quote: Callable[[str], str],
    info: TableInfo,
    src: str | None,
    shape: str,
    stat: str,
    field: str | None,
) -> str:
    """Binning carré/hexagonal d'une tuile, une cellule = {point_count, value}.

    Exactitude : un point appartient à exactement une cellule, et une cellule à
    exactement une tuile (celle qui contient son CENTRE, intervalle semi-ouvert) ;
    la lecture est élargie d'un rayon de cellule pour que les cellules à cheval sur
    deux tuiles soient comptées entières. La somme des `point_count` de toutes les
    tuiles d'un zoom vaut donc `count(*)`. Seuls shape/stat/field validés
    (listes fermées, colonne introspectée) atteignent le SQL."""
    assert info.geometry_column is not None, "build_bin_mvt_sql exige une géométrie"
    assert shape in BIN_SHAPES and stat in BIN_STATS
    table = src or f"public.{quote(info.table_name)} t"
    geom = f"t.{quote(info.geometry_column)}"
    val = f"t.{quote(field)}::double precision" if field else "NULL::double precision"
    if info.srid == 4326 and info.geometry_type == "Point":
        lat = f"least(greatest(ST_Y({geom}), -{_MERC_MAX_LAT}), {_MERC_MAX_LAT})"
        pxy = (
            f"ST_X({geom}) * {_MERC_PER_DEG} AS px, "
            f"{_MERC_R} * ln(tan({_PI4} + radians({lat}) / 2)) AS py"
        )
    else:
        pxy = "ST_X(l.pp) AS px, ST_Y(l.pp) AS py"
        table += f", LATERAL (SELECT ST_PointOnSurface(ST_Transform({geom}, 3857)) AS pp) l"
    envelope = "ST_TileEnvelope(:z, :x, :y)"
    if shape == "hex":
        # Borné au monde : PROJ replie les longitudes > 180° au retour en 4326, ce
        # qui inverserait la boîte sur les tuiles de bord.
        w = 20037508.342789244
        e = envelope
        envelope = (
            f"ST_MakeEnvelope(greatest(ST_XMin({e}) - :cell, -{w}), "
            f"greatest(ST_YMin({e}) - :cell, -{w}), least(ST_XMax({e}) + :cell, {w}), "
            f"least(ST_YMax({e}) + :cell, {w}), 3857)"
        )
    where = f"{geom} && ST_Transform({envelope}, :srid)"
    if shape == "hex":
        cells = (
            f"f AS (SELECT (sqrt(3.0) / 3 * px - py / 3) / :cell AS fq, "
            f"(2.0 / 3 * py) / :cell AS fr, v FROM pts), "
            "r1 AS (SELECT round(fq) AS rq, round(fr) AS rr, round(-fq - fr) AS rs, "
            "abs(round(fq) - fq) AS dx, abs(round(fr) - fr) AS dz, "
            "abs(round(-fq - fr) + fq + fr) AS dy, v FROM f), "
            "h AS (SELECT CASE WHEN dx > dy AND dx > dz THEN -rr - rs ELSE rq END AS q, "
            "CASE WHEN dx > dy AND dx > dz THEN rr WHEN dy > dz THEN rr ELSE -rq - rs END AS r, "
            "v FROM r1), "
            "cells AS (SELECT :cell * sqrt(3.0) * (q + r / 2.0) AS mx, :cell * 1.5 * r AS my, "
            "count(*) AS point_count, {agg} AS value FROM h GROUP BY 1, 2), "
            "own AS (SELECT * FROM cells, (SELECT ST_TileEnvelope(:z, :x, :y) AS e) env "
            f"WHERE {_own('mx', 'my')}), "
            "q AS (SELECT point_count, value, ST_AsMVTGeom("
            f"ST_Translate(ST_Scale(ST_GeomFromText('{_HEX_WKT}'), :cell, :cell), mx, my), "
            "e, :extent, :buffer, true) AS geom FROM own)"
        )
    else:
        cells = (
            # Intervalle semi-ouvert : un point exactement sur la frontière de deux
            # tuiles (`&&` est inclusif) n'est compté que dans l'une d'elles.
            "cells AS (SELECT floor(px / :cell) AS cx, floor(py / :cell) AS cy, "
            "count(*) AS point_count, {agg} AS value FROM pts, "
            "(SELECT ST_TileEnvelope(:z, :x, :y) AS e) env "
            f"WHERE {_own('px', 'py')} "
            "GROUP BY 1, 2), "
            "q AS (SELECT point_count, value, ST_AsMVTGeom("
            "ST_MakeEnvelope(cx * :cell, cy * :cell, (cx + 1) * :cell, (cy + 1) * :cell, 3857), "
            "ST_TileEnvelope(:z, :x, :y), :extent, :buffer, true) AS geom FROM cells)"
        )
    agg = {"count": "count(*)::double precision", "sum": "sum(v)", "avg": "avg(v)"}[stat]
    return (
        f"WITH pts AS (SELECT {pxy}, {val} AS v FROM {table} WHERE {where}), "
        + cells.replace("{agg}", agg)
        + " SELECT ST_AsMVT(q, :layer, :extent, 'geom') FROM q WHERE q.geom IS NOT NULL"
    )


def apply_tile_statement_timeout(session: Session, ms: int = TILE_STATEMENT_TIMEOUT_MS) -> None:
    """Borne la durée d'UNE requête de tuile, dans la transaction courante.

    `set_config(..., true)` paramétré plutôt qu'un `SET LOCAL` interpolé —
    même patron que `rls_scope` (app/features/rls.py). Transaction-local :
    rien ne fuit sur la connexion suivante à travers PgBouncer."""
    session.execute(
        text("SELECT set_config('statement_timeout', :ms, true), set_config('jit', 'off', true)"),
        {"ms": str(ms)},
    )
    # REV-283 : le JIT compile ~700 ms une agrégation dont l'exécution tient en
    # ~250 ms (coût planifié gonflé par ST_Transform) ; une tuile n'en profite jamais.


def _etag_matches(if_none_match: str | None, etag: str) -> bool:
    """Comparaison faible (RFC 9110 §13.1.2) : liste, `W/` et `*` acceptés."""
    if not if_none_match:
        return False
    return any(t.strip().removeprefix("W/") in (etag, "*") for t in if_none_match.split(","))


@router.get("/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
def get_collection_tile(
    collection_id: str,
    z: int,
    x: int,
    y: int,
    request: Request,
    bin: Literal["square", "hex"] | None = Query(default=None),  # noqa: A002
    stat: Literal["count", "sum", "avg"] = "count",
    field: str | None = Query(default=None, max_length=128),
    bins: int = Query(default=16, ge=2, le=64),
    user=Depends(get_current_user_optional),
    guest: GuestActor | None = Depends(get_share_link_actor),
    session: Session = Depends(get_session, scope="function"),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
    masked=Depends(get_masked_for_user),
) -> Response:
    # Même porte que GET /items : 404 avant 403, anonyme accepté sur une
    # collection publique — plus désormais un jeton invité scopé (GAP-19).
    col = get_collection_for_read(session, user, collection_id, guest=guest)
    masked = unmask_for_owner(masked, user, col)
    try:
        validate_tile_coords(z, x, y)
    except InvalidTileCoords as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    try:
        info = introspect(session, col.table_name)
    except TableNotFound as exc:
        raise HTTPException(status_code=404, detail="collection not found") from exc
    if info.geometry_column is None:
        raise HTTPException(status_code=400, detail="collection has no geometry column")
    if masked:
        info = hide_sensitive_columns(info, col.sensitive_fields)

    bin_field: str | None = None
    if bin is not None:
        if stat != "count":
            by_name = {c.name: c for c in info.columns}
            col_info = by_name.get(field or "")
            if col_info is None or col_info.type not in BIN_NUMERIC_TYPES:
                raise HTTPException(
                    status_code=400,
                    detail="stat sum/avg requires a numeric 'field' of the collection",
                )
            bin_field = col_info.name

    quote = functools.partial(quote_ident, session)
    aggregated = False
    params = {
        "z": z,
        "x": x,
        "y": y,
        "layer": col.id,
        "extent": MVT_EXTENT,
        "buffer": MVT_BUFFER,
        "srid": info.srid or 4326,
    }
    # L'isolation tenant vient de la RLS (rôle gis_rls + GUC app.tenant_id),
    # jamais d'un WHERE applicatif.
    # `geo_source` après l'entrée dans `rls` (limites de la session) : sous une limite
    # géographique, toutes les requêtes de tuile lisent la géométrie DÉCOUPÉE.
    with rls(session, col.tenant_id, masked=masked), geo_source(session, info, quote=quote) as src:
        sql = build_mvt_sql(quote, info, src)
        agg_sql = (
            build_bin_mvt_sql(quote, info, src, bin, stat, bin_field)
            if bin is not None
            else build_agg_mvt_sql(quote, info, src)
        )
        cell = bin_cell_size(z, bins) if bin is not None else agg_cell_size(z)
        apply_tile_statement_timeout(session)
        # REV-283a : à bas zoom, une sonde bornée décide AVANT toute lecture
        # lourde ; tuile dense => agrégation seule (pas de lecture brute jetée).
        if (
            bin is not None
            or 0 < tile_agg_max_zoom() >= z
            and (
                session.execute(
                    text(build_probe_sql(quote, info, src)),
                    {**params, "max_features": MAX_TILE_FEATURES},
                ).scalar()
                > MAX_TILE_FEATURES
            )
        ):
            aggregated = True
            apply_tile_statement_timeout(session, TILE_AGG_STATEMENT_TIMEOUT_MS)
            try:
                row = session.execute(text(agg_sql), {**params, "cell": cell}).first()
            except DBAPIError as exc:
                if getattr(exc.orig, "sqlstate", None) != "57014":  # query_canceled
                    raise
                # Réponse construite ici : le gestionnaire RFC 7807 global ne
                # relaie pas les en-têtes d'une HTTPException (Retry-After perdu).
                return Response(
                    content=b'{"title":"tile aggregation timed out","status":503}',
                    status_code=503,
                    media_type="application/problem+json",
                    headers={"Retry-After": "5"},
                )
            row = (row[0], 0) if row is not None else None
        else:
            row = session.execute(
                text(sql),
                {
                    **params,
                    "fid": mvt_feature_id_column(info),
                    "max_features": MAX_TILE_FEATURES,
                },
            ).first()
    if row is None or not row[0]:
        return Response(status_code=204)
    tile, feature_count = row[0], row[1]
    # Réponse dépendante de l'identité (colonnes sensibles, RLS) : cache
    # partagé seulement pour l'anonyme (c01-007).
    visibility = "public" if col.is_public and user is None and guest is None else "private"
    content = bytes(tile)
    # REV-283b : revalidation à 304 — même empreinte pour mêmes octets, quelle
    # que soit l'identité (Vary: Authorization garde les caches séparés).
    # Le mode agrégé est salé dans l'empreinte : mêmes octets ≠ même sémantique.
    digest = hashlib.sha256((b"agg:" if aggregated else b"") + content)
    etag = '"' + digest.hexdigest()[:32] + '"'
    headers = {
        "Cache-Control": f"{visibility}, max-age=300",
        "Vary": "Authorization",
        "ETag": etag,
    }
    if _etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    if aggregated:
        headers["X-Tile-Aggregated"] = "true"
    elif feature_count > MAX_TILE_FEATURES:
        headers["X-Tile-Truncated"] = "true"
    return Response(content=content, media_type=MVT_MEDIA_TYPE, headers=headers)
