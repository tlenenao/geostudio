# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale STAC d'une collection : ST_EstimatedExtent (rapide, via les
stats ANALYZE), repli ST_Extent quand les stats sont absentes, toujours
reprojetée en 4326. Les emprises STAC étant advisory, l'approximation par
statistiques est assumée (§2.3). None si pas de géométrie ou table vide →
l'appelant retombe sur l'emprise monde."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import TableInfo


def _box_4326(session: Session, inner_sql: str, params: dict) -> list[float] | None:
    row = session.execute(text(
        f"SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM "
        f"(SELECT ST_Transform(ST_SetSRID(({inner_sql})::geometry, :srid), 4326) AS g) s "
        f"WHERE g IS NOT NULL"
    ), params).one_or_none()
    return [row[0], row[1], row[2], row[3]] if row else None


def estimated_bbox_4326(session: Session, info: TableInfo) -> list[float] | None:
    if info.geometry_column is None:
        return None
    srid = info.srid or 4326
    est = _box_4326(
        session, "ST_EstimatedExtent(:schema, :table, :geom)",
        {"schema": "public", "table": info.table_name,
         "geom": info.geometry_column, "srid": srid},
    )
    if est is not None:
        return est
    # Stats absentes (ST_EstimatedExtent NULL) : repli exact sur ST_Extent.
    t = quote_ident(session, info.table_name)
    g = quote_ident(session, info.geometry_column)
    return _box_4326(session, f"SELECT ST_Extent({g}) FROM public.{t}", {"srid": srid})
