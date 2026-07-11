import pytest
from sqlalchemy import text

from app.features.rls import rls_scope

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_rls_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope, t_core_like"))
        conn.execute(text(
            "CREATE TABLE t_scope (id serial PRIMARY KEY, v text, tenant_id text NOT NULL)"))
        conn.execute(text("ALTER TABLE t_scope ENABLE ROW LEVEL SECURITY"))
        conn.execute(text(
            "CREATE POLICY tenant_isolation ON t_scope "
            "USING (tenant_id = current_setting('app.tenant_id')) "
            "WITH CHECK (tenant_id = current_setting('app.tenant_id'))"))
        conn.execute(text("GRANT SELECT, INSERT, UPDATE, DELETE ON t_scope TO gis_rls"))
        conn.execute(text("GRANT USAGE, SELECT ON SEQUENCE t_scope_id_seq TO gis_rls"))
        conn.execute(text("CREATE TABLE t_core_like (id serial PRIMARY KEY, note text)"))
        conn.execute(text(
            "INSERT INTO t_scope (v, tenant_id) VALUES ('mine', 'default'), ('theirs', 'other')"))
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_scope, t_core_like"))


def test_scope_filters_and_releases_role(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            rows = session.execute(text("SELECT v FROM t_scope")).scalars().all()
            assert rows == ["mine"]
        # Après le scope, même transaction : le rôle est rendu →
        # la table « cœur » (non grantée à gis_rls) est accessible (pattern audit).
        session.execute(text("INSERT INTO t_core_like (note) VALUES ('audit')"))
        session.commit()


def test_scope_releases_role_on_exception(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with pytest.raises(RuntimeError):
            with rls_scope(session, "default"):
                raise RuntimeError("boom")
        # La transaction n'est pas en erreur SQL : le rôle est rendu.
        assert session.execute(text("SELECT current_user")).scalar() == "gis"


def test_scope_preserves_original_sql_error(pg_rls_table, pg_session_factory):
    import sqlalchemy.exc
    with pg_session_factory() as session:
        with pytest.raises(sqlalchemy.exc.DBAPIError) as exc_info:
            with rls_scope(session, "other"):
                # WITH CHECK rejette : erreur SQL DANS le scope
                session.execute(text(
                    "INSERT INTO t_scope (v, tenant_id) VALUES ('x', 'default')"))
        # C'est l'erreur d'ORIGINE qui doit remonter, pas l'échec du RESET ROLE
        assert "row-level security" in str(exc_info.value).lower()


def test_scope_write_stamps_current_tenant(pg_rls_table, pg_session_factory):
    with pg_session_factory() as session:
        with rls_scope(session, "default"):
            session.execute(text(
                "INSERT INTO t_scope (v, tenant_id) "
                "VALUES ('new', current_setting('app.tenant_id'))"))
        session.commit()
    with pg_session_factory() as session:
        assert session.execute(text(
            "SELECT tenant_id FROM t_scope WHERE v = 'new'")).scalar() == "default"
