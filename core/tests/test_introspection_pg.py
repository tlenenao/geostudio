import pytest
from sqlalchemy import text

from app.collections.introspection import TableNotFound, UnsupportedTable
from app.collections.introspection_pg import introspect_table

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
