# SPDX-License-Identifier: Apache-2.0
"""REV-352 : écriture réelle X <-> MultiX et couche GEOMETRY mixte."""

import pytest
from sqlalchemy import text

from app.collections.introspection_pg import introspect_table
from app.features.repository import insert_feature
from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis

POLY = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]}
MPOLY = {"type": "MultiPolygon", "coordinates": [POLY["coordinates"]]}


@pytest.fixture()
def tables(pg_engine):
    names = {"t_gp_multi": "MultiPolygon", "t_gp_poly": "Polygon", "t_gp_mixed": "Geometry"}
    with pg_engine.begin() as conn:
        for name, gtype in names.items():
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))
            conn.execute(
                text(
                    f"CREATE TABLE {name} (id serial PRIMARY KEY, "
                    f"tenant_id text NOT NULL DEFAULT 'default', geom geometry({gtype}, 4326))"
                )
            )
            conn.execute(text(f"ALTER TABLE {name} ENABLE ROW LEVEL SECURITY"))
            conn.execute(
                text(
                    f"CREATE POLICY tenant_isolation ON {name} "
                    "USING (tenant_id = current_setting('app.tenant_id')) "
                    "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"
                )
            )
            conn.execute(text(f"GRANT SELECT, INSERT ON {name} TO gis_rls"))
            conn.execute(text(f"GRANT USAGE, SELECT ON SEQUENCE {name}_id_seq TO gis_rls"))
    yield list(names)
    with pg_engine.begin() as conn:
        for name in names:
            conn.execute(text(f"DROP TABLE IF EXISTS {name}"))


def _insert_and_type(factory, table, geometry):
    with factory() as session:
        info = introspect_table(session, table)
        with rls_scope(session, "default"):
            fid = insert_feature(session, info, properties={}, geometry=geometry)
        session.commit()
        return session.execute(
            text(f"SELECT GeometryType(geom) FROM {table} WHERE id = :i"), {"i": fid}
        ).scalar()


@pytest.mark.parametrize(
    ("table", "geometry", "stored"),
    [
        ("t_gp_multi", POLY, "MULTIPOLYGON"),  # promotion Polygon -> MultiPolygon
        ("t_gp_multi", MPOLY, "MULTIPOLYGON"),
        ("t_gp_poly", MPOLY, "POLYGON"),  # MultiPolygon à une partie -> Polygon
        ("t_gp_mixed", {"type": "Point", "coordinates": [0, 0]}, "POINT"),
        ("t_gp_mixed", POLY, "POLYGON"),
    ],
)
def test_geometry_written_to_declared_type(tables, pg_session_factory, table, geometry, stored):
    assert _insert_and_type(pg_session_factory, table, geometry) == stored
