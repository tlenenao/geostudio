# SPDX-License-Identifier: Apache-2.0
import pytest

from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory
from app.items.models import Item
from app.quotas.service import (
    count_collections_for_tenant,
    count_items_for_tenant,
    count_users_for_tenant,
)
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant_a = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant_a.id)
        # Un deuxième tenant, créé à la main (get_or_create_default_tenant ne
        # sait créer que "le" tenant par défaut) — un second User avec un
        # tenant_id distinct suffit à distinguer les compteurs.
        from app.tenants.models import Tenant

        tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        s.add(tenant_b)
        s.flush()
        ensure_built_in_roles(s, tenant_id=tenant_b.id)
        user_a = get_or_create_user(
            s,
            tenant_id=tenant_a.id,
            oidc_sub="a1",
            username="a1",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        user_b = get_or_create_user(
            s,
            tenant_id=tenant_b.id,
            oidc_sub="b1",
            username="b1",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.add(
            Item(
                id="item-a1",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                resource_type="map",
                title="A1",
            )
        )
        s.add(
            Item(
                id="item-a2",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                resource_type="map",
                title="A2",
            )
        )
        s.add(
            Item(
                id="item-b1",
                tenant_id=tenant_b.id,
                owner_id=user_b.id,
                resource_type="map",
                title="B1",
            )
        )
        s.add(
            Collection(
                id="col-a1",
                tenant_id=tenant_a.id,
                owner_id=user_a.id,
                table_name="col_a1",
                title="Col A1",
                pk_column="id",
            )
        )
        s.commit()
        yield s, tenant_a.id, tenant_b.id


def test_count_items_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b = env
    assert count_items_for_tenant(session, tenant_a) == 2
    assert count_items_for_tenant(session, tenant_b) == 1


def test_count_collections_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b = env
    assert count_collections_for_tenant(session, tenant_a) == 1
    assert count_collections_for_tenant(session, tenant_b) == 0


def test_count_users_for_tenant_counts_only_this_tenant(env):
    session, tenant_a, tenant_b = env
    assert count_users_for_tenant(session, tenant_a) == 1
    assert count_users_for_tenant(session, tenant_b) == 1
