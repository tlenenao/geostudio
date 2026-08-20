# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection_pg import introspect_table
from app.collections.provisioning import create_empty_collection
from app.collections.schemas import EmptyCollectionColumn
from app.db import Base, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_creates_an_empty_table_with_the_requested_columns_and_no_rows(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            title="Ma requête",
            columns=[
                EmptyCollectionColumn(name="commune", sqlType="text"),
                EmptyCollectionColumn(name="total", sqlType="integer"),
            ],
            geometry_type=None,
            srid=None,
            introspect=introspect_table,
            apply_ddl=apply_collection_ddl,
        )
        s.commit()
        rows = s.execute(text(f"SELECT commune, total FROM public.{col.table_name}")).fetchall()
        assert rows == []
        assert col.geometry_column is None
        assert col.feature_count == 0
        assert col.is_public is False


def test_creates_a_geometry_column_when_geometry_type_is_given(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            title="Ma requête spatiale",
            columns=[EmptyCollectionColumn(name="commune", sqlType="text")],
            geometry_type="Point",
            srid=4326,
            introspect=introspect_table,
            apply_ddl=apply_collection_ddl,
        )
        s.commit()
        assert col.geometry_column == "geom"
        assert col.geometry_type == "Point"
        assert col.srid == 4326


def test_column_names_are_quoted_defensively(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            title="Colonne réservée",
            columns=[EmptyCollectionColumn(name="select", sqlType="text")],  # mot réservé SQL
            geometry_type=None,
            srid=None,
            introspect=introspect_table,
            apply_ddl=apply_collection_ddl,
        )
        s.commit()
        rows = s.execute(text(f'SELECT "select" FROM public.{col.table_name}')).fetchall()
        assert rows == []
