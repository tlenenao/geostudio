# SPDX-License-Identifier: Apache-2.0
"""SP-42/F-securite-tenant-rls-02 : l'emprise STAC/DCAT doit rester bornée au
tenant sous RLS, comme stac/routes.py et dcat/routes.py le donnent à
comprendre en enveloppant l'appel dans `with rls(session, col.tenant_id)`.
Avant correctif, le bbox_provider par défaut (ST_EstimatedExtent) lisait les
statistiques du planificateur — non filtrées par policy — et fuyait la
géométrie d'un AUTRE tenant partageant la même table physique."""

import pytest
from sqlalchemy import text

from app.collections.introspection import TableInfo
from app.dcat.routes import get_bbox_provider as dcat_get_bbox_provider
from app.features.rls import rls_scope
from app.stac.routes import get_bbox_provider as stac_get_bbox_provider

pytestmark = pytest.mark.postgis


@pytest.fixture()
def two_tenant_geom_table(pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_stac_extent_rls"))
        conn.execute(
            text(
                "CREATE TABLE t_stac_extent_rls ("
                "id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "geom geometry(Point, 4326))"
            )
        )
        conn.execute(text("ALTER TABLE t_stac_extent_rls ENABLE ROW LEVEL SECURITY"))
        conn.execute(
            text(
                "CREATE POLICY tenant_isolation ON t_stac_extent_rls "
                "USING (tenant_id = current_setting('app.tenant_id')) "
                "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
            )
        )
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_stac_extent_rls TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_stac_extent_rls_id_seq TO gis_rls"))
        conn.execute(
            text(
                "INSERT INTO t_stac_extent_rls (tenant_id, geom) VALUES "
                "('default', ST_SetSRID(ST_MakePoint(1, 1), 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_stac_extent_rls (tenant_id, geom) VALUES "
                "('other', ST_SetSRID(ST_MakePoint(150, 80), 4326))"
            )
        )
        conn.execute(text("ANALYZE t_stac_extent_rls"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_stac_extent_rls"))


@pytest.mark.parametrize(
    "get_provider", [stac_get_bbox_provider, dcat_get_bbox_provider], ids=["stac", "dcat"]
)
def test_bbox_provider_never_exceeds_tenant_extent_under_rls(
    two_tenant_geom_table, pg_session_factory, get_provider
):
    info = TableInfo(
        table_name="t_stac_extent_rls",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
    )
    bbox_provider = get_provider()

    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            bbox = bbox_provider(session, info)

    assert bbox is not None
    # Le seul point visible sous RLS pour "default" est (1, 1) : toute
    # emprise qui déborde jusqu'au point (150, 80) de "other" prouve une
    # fuite cross-tenant.
    assert bbox[2] < 5, f"emprise a fuité au-delà du tenant 'default' : {bbox}"
    assert bbox[3] < 5, f"emprise a fuité au-delà du tenant 'default' : {bbox}"
