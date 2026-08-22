# SPDX-License-Identifier: Apache-2.0
"""Tuiles vectorielles MVT servies par le cœur (spec SP-24 §3.1).

Pourquoi ici et pas Martin : Martin se connecte en propriétaire des tables,
donc hors RLS, et n'a aucune notion de collection ni de `can()`. Servir le MVT
depuis le cœur donne les trois d'un coup — autorisation, isolation tenant, et
un `collectionId` sur la couche.

Ce module est volontairement coupé en deux : des helpers purs (testés sans
base) et une route mince qui les assemble."""

import functools
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.ddl import quote_ident
from app.collections.introspection import TableInfo, TableNotFound
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.features.routes import get_rls_scope

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


def build_mvt_sql(quote: Callable[[str], str], info: TableInfo) -> str:
    assert info.geometry_column is not None, "build_mvt_sql exige une géométrie"
    table = f"public.{quote(info.table_name)}"
    geom = f"t.{quote(info.geometry_column)}"
    props = ", ".join(f"t.{quote(name)} AS {quote(name)}" for name in mvt_property_columns(info))
    props_clause = f", {props}" if props else ""
    return (
        "SELECT ST_AsMVT(tile, :layer, :extent, 'geom', :fid) FROM ("
        f"SELECT ST_AsMVTGeom(ST_Transform({geom}, 3857), "
        "ST_TileEnvelope(:z, :x, :y), :extent, :buffer, true) AS geom"
        f"{props_clause} "
        f"FROM {table} t "
        # Le filtre porte sur la géométrie brute pour rester indexable par le
        # GiST posé par apply_collection_ddl : ST_Transform à gauche du && le
        # rendrait inutilisable.
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid) "
        # Plafond DANS la sous-requête : c'est le nombre de lignes lues et
        # transformées qu'il faut borner, pas la sortie de l'agrégat (une
        # tuile est toujours une seule ligne).
        "LIMIT :max_features"
        ") AS tile WHERE tile.geom IS NOT NULL"
    )


def apply_tile_statement_timeout(session: Session) -> None:
    """Borne la durée d'UNE requête de tuile, dans la transaction courante.

    `set_config(..., true)` paramétré plutôt qu'un `SET LOCAL` interpolé —
    même patron que `rls_scope` (app/features/rls.py). Transaction-local :
    rien ne fuit sur la connexion suivante à travers PgBouncer."""
    session.execute(
        text("SELECT set_config('statement_timeout', :ms, true)"),
        {"ms": str(TILE_STATEMENT_TIMEOUT_MS)},
    )


@router.get("/collections/{collection_id}/tiles/{z}/{x}/{y}.mvt")
def get_collection_tile(
    collection_id: str,
    z: int,
    x: int,
    y: int,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    rls=Depends(get_rls_scope),
) -> Response:
    # Même porte que GET /items : 404 avant 403, anonyme accepté sur une
    # collection publique. Aucune variante — la garde est réutilisée verbatim.
    col = get_readable_collection(session, user, collection_id)
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

    quote = functools.partial(quote_ident, session)
    sql = build_mvt_sql(quote, info)
    # L'isolation tenant vient de la RLS (rôle gis_rls + GUC app.tenant_id),
    # jamais d'un WHERE applicatif.
    with rls(session, col.tenant_id):
        apply_tile_statement_timeout(session)
        tile = session.execute(
            text(sql),
            {
                "z": z,
                "x": x,
                "y": y,
                "layer": col.id,
                "extent": MVT_EXTENT,
                "buffer": MVT_BUFFER,
                "srid": info.srid or 4326,
                "fid": mvt_feature_id_column(info),
                "max_features": MAX_TILE_FEATURES,
            },
        ).scalar()
    if not tile:
        return Response(status_code=204)
    visibility = "public" if col.is_public else "private"
    return Response(
        content=bytes(tile),
        media_type=MVT_MEDIA_TYPE,
        headers={"Cache-Control": f"{visibility}, max-age=300"},
    )
