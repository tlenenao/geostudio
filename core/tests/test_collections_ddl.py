# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.ddl import TenantColumnMismatch, apply_collection_ddl

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_table(pg_engine, pg_session_factory):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls"))
        conn.execute(
            text(
                "CREATE TABLE t_rls (id serial PRIMARY KEY, titre text, geom geometry(Point, 4326))"
            )
        )
    yield "t_rls"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls"))


def test_ddl_adds_tenant_and_rls(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        cols = (
            session.execute(
                text(
                    "SELECT column_name FROM information_schema.columns WHERE table_name = 't_rls'"
                )
            )
            .scalars()
            .all()
        )
        assert "tenant_id" in cols
        rls = session.execute(
            text("SELECT relrowsecurity FROM pg_class WHERE relname = 't_rls'")
        ).scalar()
        assert rls is True
        policies = (
            session.execute(text("SELECT policyname FROM pg_policies WHERE tablename = 't_rls'"))
            .scalars()
            .all()
        )
        assert "tenant_isolation" in policies


def test_ddl_is_idempotent(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        apply_collection_ddl(session, pg_table)  # ne doit pas lever
        session.commit()


def test_ddl_creates_tenant_index(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.commit()
    with pg_session_factory() as session:
        idx = (
            session.execute(text("SELECT indexname FROM pg_indexes WHERE tablename = 't_rls'"))
            .scalars()
            .all()
        )
        assert "ix_t_rls_tenant_id" in idx


def test_rls_blocks_update_across_tenants(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text("INSERT INTO t_rls (titre, tenant_id) VALUES ('a', 'default')"))
        session.commit()
    with pg_session_factory() as session:
        # Mauvais tenant : l'UPDATE ne voit aucune ligne (USING) — 0 modifiée.
        session.execute(text("SELECT set_config('app.tenant_id', 'other', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls"))
        r = session.execute(text("UPDATE t_rls SET titre = 'hack'"))
        assert r.rowcount == 0
    with pg_session_factory() as session:
        # Bon tenant : impossible de réécrire tenant_id vers un autre (WITH CHECK).
        session.execute(text("SELECT set_config('app.tenant_id', 'default', true)"))
        session.execute(text("SET LOCAL ROLE gis_rls"))
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.DBAPIError):
            session.execute(text("UPDATE t_rls SET tenant_id = 'other'"))


def test_rls_blocks_wrong_tenant(pg_table, pg_session_factory):
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table)
        session.execute(text("INSERT INTO t_rls (titre, tenant_id) VALUES ('a', 'default')"))
        session.commit()
    with pg_session_factory() as session:
        # Sous le rôle RLS avec le bon tenant : la ligne est visible.
        session.execute(text("SET LOCAL ROLE gis_rls"))
        session.execute(text("SET LOCAL app.tenant_id = 'default'"))
        assert session.execute(text("SELECT count(*) FROM t_rls")).scalar() == 1
    with pg_session_factory() as session:
        # Mauvais tenant : rien à lire, et l'écriture est rejetée par WITH CHECK.
        session.execute(text("SET LOCAL ROLE gis_rls"))
        session.execute(text("SET LOCAL app.tenant_id = 'other'"))
        assert session.execute(text("SELECT count(*) FROM t_rls")).scalar() == 0
        import sqlalchemy.exc

        with pytest.raises(sqlalchemy.exc.DBAPIError):
            session.execute(text("INSERT INTO t_rls (titre, tenant_id) VALUES ('b', 'default')"))


@pytest.fixture()
def pg_table_with_foreign_tenant_column(pg_engine):
    # Table PRÉEXISTANTE portant déjà une colonne tenant_id peuplée par un
    # autre système (pas créée par notre pipeline d'ingestion, qui se
    # protège lui-même — cf. app/ingestion/importer.py:129-135).
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls_foreign"))
        conn.execute(
            text(
                "CREATE TABLE t_rls_foreign (id serial PRIMARY KEY, tenant_id text NOT NULL, "
                "geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "INSERT INTO t_rls_foreign (tenant_id, geom) VALUES "
                "('acme', ST_SetSRID(ST_MakePoint(1, 1), 4326))"
            )
        )
    yield "t_rls_foreign"
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_rls_foreign"))


def test_ddl_rejects_preexisting_tenant_column_with_foreign_values(
    pg_table_with_foreign_tenant_column, pg_session_factory
):
    # SP-42/F-securite-tenant-rls-01 : ADD COLUMN IF NOT EXISTS est un no-op
    # silencieux quand tenant_id existe déjà — sans cette garde, la policy
    # RLS serait posée sur des valeurs étrangères ('acme' != 'default') et
    # toutes les lectures sous RLS renverraient 0 ligne malgré un COUNT(*)
    # hors RLS non nul.
    with pg_session_factory() as session:
        with pytest.raises(TenantColumnMismatch):
            apply_collection_ddl(session, pg_table_with_foreign_tenant_column, tenant_id="default")
        session.rollback()


def test_ddl_accepts_preexisting_tenant_column_with_matching_values(
    pg_table_with_foreign_tenant_column, pg_session_factory
):
    # Contre-épreuve : le même mécanisme ne doit pas refuser une table dont
    # la colonne tenant_id préexistante correspond déjà au tenant appelant.
    with pg_session_factory() as session:
        apply_collection_ddl(session, pg_table_with_foreign_tenant_column, tenant_id="acme")
        session.commit()
