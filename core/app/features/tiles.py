# SPDX-License-Identifier: Apache-2.0
"""Tuiles vectorielles MVT servies par le cœur (spec SP-24 §3.1).

Pourquoi ici et pas Martin : Martin se connecte en propriétaire des tables,
donc hors RLS, et n'a aucune notion de collection ni de `can()`. Servir le MVT
depuis le cœur donne les trois d'un coup — autorisation, isolation tenant, et
un `collectionId` sur la couche.

Ce module est volontairement coupé en deux : des helpers purs (testés sans
base) et une route mince qui les assemble."""

from collections.abc import Callable

from app.collections.introspection import TableInfo

MVT_EXTENT = 4096
MVT_BUFFER = 64
MAX_TILE_ZOOM = 24

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
        f"WHERE {geom} && ST_Transform(ST_TileEnvelope(:z, :x, :y), :srid)"
        ") AS tile WHERE tile.geom IS NOT NULL"
    )
