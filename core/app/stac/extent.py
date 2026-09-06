# SPDX-License-Identifier: Apache-2.0
"""Emprise spatiale STAC d'une collection : ST_Extent (scan réel de la table,
donc soumis à toute policy RLS active sur la session), toujours reprojetée en
4326. None si pas de géométrie ou table vide → l'appelant retombe sur
l'emprise monde.

SP-42/F-securite-tenant-rls-02 : ce module utilisait auparavant
ST_EstimatedExtent (lecture de pg_statistic, rapide mais table entière, donc
PAS filtrée par RLS) avec repli ST_Extent seulement si les stats étaient
absentes — stac/routes.py et dcat/routes.py enveloppent pourtant cet appel
dans `with rls(session, col.tenant_id)`, ce qui donnait l'illusion d'un
calcul borné au tenant. Mesuré : sur une table à deux tenants, l'emprise
« estimée » publiait la géométrie d'un tenant que le lecteur ne pouvait pas
lire. Corrigé en utilisant uniquement ST_Extent (déjà implémenté et déjà
soumis à RLS dans app.collections.extent::table_extent, dupliqué ici pour la
reprojection 4326 qu'exige STAC/DCAT — table_extent ne reprojette pas).
Compromis assumé : ST_Extent scanne la table entière sous RLS (pas de lecture
des statistiques du planificateur), plus coûteux que ST_EstimatedExtent sur
une grosse collection. Aucune voie connue ne préserve à la fois la
performance de ST_EstimatedExtent et son filtrage par tenant — ST_EstimatedExtent
ignore RLS par construction (pg_statistic n'est pas soumis aux policies)."""

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.collections.introspection import TableInfo
from app.sql_ident import quote_ident


def _box_4326(session: Session, inner_sql: str, params: dict) -> list[float] | None:
    row = session.execute(
        text(
            f"SELECT ST_XMin(g), ST_YMin(g), ST_XMax(g), ST_YMax(g) FROM "
            f"(SELECT ST_Transform(ST_SetSRID(({inner_sql})::geometry, :srid), 4326) AS g) s "
            f"WHERE g IS NOT NULL"
        ),
        params,
    ).one_or_none()
    return [row[0], row[1], row[2], row[3]] if row else None


def rls_scoped_bbox_4326(session: Session, info: TableInfo) -> list[float] | None:
    if info.geometry_column is None:
        return None
    srid = info.srid or 4326
    t = quote_ident(session, info.table_name)
    g = quote_ident(session, info.geometry_column)
    return _box_4326(session, f"SELECT ST_Extent({g}) FROM public.{t}", {"srid": srid})
