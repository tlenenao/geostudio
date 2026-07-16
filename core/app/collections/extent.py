# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale d'une collection (description OGC). Dans app.collections
(pas app.features) : consommé par collections.routes, qui ne peut pas
importer vers le haut. L'appelant pose rls_scope() si l'emprise doit être
bornée au tenant."""
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.ddl import quote_ident
from app.collections.introspection import TableInfo


def table_extent(session: Session, info: TableInfo) -> list[float] | None:
    if info.geometry_column is None:
        return None
    t = quote_ident(session, info.table_name)
    g = quote_ident(session, info.geometry_column)
    box = session.execute(text(
        f"SELECT ST_XMin(e), ST_YMin(e), ST_XMax(e), ST_YMax(e) "
        f"FROM (SELECT ST_Extent({g}) AS e FROM public.{t}) s WHERE e IS NOT NULL"
    )).one_or_none()
    return [box[0], box[1], box[2], box[3]] if box else None
