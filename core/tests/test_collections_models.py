# SPDX-License-Identifier: Apache-2.0
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.sharing.models import CollectionShare
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_collection_row_roundtrip():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        session.add(
            Collection(
                id="incidents",
                tenant_id=tenant.id,
                owner_id=user.id,
                table_name="incidents",
                title="Incidents",
                pk_column="id",
                geometry_column="geom",
                geometry_type="Point",
                srid=4326,
            )
        )
        session.commit()
        row = session.get(Collection, "incidents")
        assert row.is_public is False and row.editable is True


def test_user_is_admin_defaults_false():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        assert user.is_admin is False


def test_collection_share_composite_pk():
    Session = _session_factory()
    with Session() as session:
        assert {c.name for c in CollectionShare.__table__.primary_key.columns} == {
            "collection_id",
            "group_id",
        }


def test_collection_row_stores_feature_count():
    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        session.add(
            Collection(
                id="incidents",
                tenant_id=tenant.id,
                owner_id=user.id,
                table_name="incidents",
                title="Incidents",
                pk_column="id",
                geometry_column="geom",
                geometry_type="Point",
                srid=4326,
                feature_count=42,
            )
        )
        session.commit()
        row = session.get(Collection, "incidents")
        assert row.feature_count == 42


def test_create_collection_defaults_feature_count_to_none():
    from app.collections.repository import create_collection

    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        col = create_collection(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=False,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        assert col.feature_count is None


def test_create_collection_stores_feature_count():
    from app.collections.repository import create_collection

    Session = _session_factory()
    with Session() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        col = create_collection(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=False,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
            feature_count=7,
        )
        assert col.feature_count == 7
