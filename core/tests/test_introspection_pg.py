import pytest
from sqlalchemy import text

from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table, list_public_tables

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_session(pg_session_factory, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_incidents"))
        conn.execute(text("DROP TYPE IF EXISTS t_gravite"))
        conn.execute(text("CREATE TYPE t_gravite AS ENUM ('faible','moyenne','haute')"))
        conn.execute(text("""
            CREATE TABLE t_incidents (
                id serial PRIMARY KEY,
                titre varchar(200) NOT NULL,
                gravite t_gravite,
                date_incident date,
                resolu boolean DEFAULT false,
                payload jsonb,
                geom geometry(Point, 4326)
            )"""))
    with pg_session_factory() as session:
        yield session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_incidents"))
        conn.execute(text("DROP TYPE IF EXISTS t_gravite"))


def test_introspects_types(pg_session):
    info = introspect_table(pg_session, "t_incidents")
    assert info.pk_column == "id"
    assert info.geometry_column == "geom"
    assert info.geometry_type == "Point" and info.srid == 4326
    by_name = {c.name: c for c in info.columns}
    assert by_name["titre"].type == "string" and by_name["titre"].required is True
    assert by_name["titre"].max_length == 200
    assert by_name["gravite"].type == "enum"
    assert by_name["gravite"].enum_values == ["faible", "moyenne", "haute"]
    assert by_name["date_incident"].type == "date"
    assert by_name["resolu"].type == "boolean"
    assert by_name["resolu"].required is False  # NOT NULL absent / défaut présent
    assert by_name["payload"].type == "unsupported"  # jsonb hors périmètre v1


def test_unknown_table(pg_session):
    with pytest.raises(TableNotFound):
        introspect_table(pg_session, "nope_table")


def test_composite_pk_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_composite"))
        conn.execute(text("CREATE TABLE t_composite (a int, b int, PRIMARY KEY (a, b))"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_composite")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_composite"))


def test_enum_lookup_is_schema_qualified(pg_session, pg_engine):
    # Un type homonyme dans un autre schéma ne doit pas polluer les valeurs.
    with pg_engine.begin() as conn:
        conn.execute(text("CREATE SCHEMA IF NOT EXISTS decoy"))
        conn.execute(text("DROP TYPE IF EXISTS decoy.t_gravite"))
        conn.execute(text("CREATE TYPE decoy.t_gravite AS ENUM ('polluee')"))
    try:
        info = introspect_table(pg_session, "t_incidents")
        by_name = {c.name: c for c in info.columns}
        assert by_name["gravite"].enum_values == ["faible", "moyenne", "haute"]
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TYPE IF EXISTS decoy.t_gravite"))
            conn.execute(text("DROP SCHEMA IF EXISTS decoy"))


def test_table_without_pk_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_nopk"))
        conn.execute(text("CREATE TABLE t_nopk (a int)"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_nopk")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_nopk"))


def test_two_geometry_columns_refused(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_twogeom"))
        conn.execute(text(
            "CREATE TABLE t_twogeom (id serial PRIMARY KEY, "
            "g1 geometry(Point,4326), g2 geometry(Point,4326))"))
    try:
        with pytest.raises(UnsupportedTable):
            introspect_table(pg_session, "t_twogeom")
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE t_twogeom"))


def test_lists_public_base_tables_only(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_extra"))
        conn.execute(text("DROP VIEW IF EXISTS t_a_view"))
        conn.execute(text("CREATE TABLE t_extra (id serial PRIMARY KEY)"))
        conn.execute(text("CREATE VIEW t_a_view AS SELECT id FROM t_extra"))
    try:
        names = list_public_tables(pg_session)
        assert "t_incidents" in names  # from the pg_session fixture
        assert "t_extra" in names
        assert "t_a_view" not in names  # views are excluded
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP VIEW IF EXISTS t_a_view"))
            conn.execute(text("DROP TABLE IF EXISTS t_extra"))
