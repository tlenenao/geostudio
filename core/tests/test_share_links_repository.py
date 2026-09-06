# SPDX-License-Identifier: Apache-2.0
"""app.sharing.repository — create/list/revoke/resolve un share_link
(GAP-12). Fixture SQLite locale, patron déjà établi par ce dépôt pour un
test de repository pur (pas de route HTTP)."""

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.sharing import repository as sharing_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant(session):
    t = get_or_create_default_tenant(session)
    session.commit()
    return t


@pytest.fixture()
def user(session, tenant):
    u = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="sub-1",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    session.commit()
    return u


@pytest.fixture()
def item(session, tenant, user):
    it = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Item"
    )
    session.commit()
    return it


def test_create_list_revoke_share_link(session, tenant, user, item):
    link = sharing_repo.create_share_link(
        session, tenant_id=tenant.id, item_id=item.id, created_by=user.id, ttl_seconds=86400
    )
    session.commit()
    assert link.tenant_id == tenant.id
    assert link.item_id == item.id
    assert link.revoked_at is None

    links = sharing_repo.list_share_links(session, tenant_id=tenant.id, item_id=item.id)
    assert [row.id for row in links] == [link.id]

    ok = sharing_repo.revoke_share_link(session, tenant_id=tenant.id, link_id=link.id)
    session.commit()
    assert ok is True

    links_after = sharing_repo.list_share_links(session, tenant_id=tenant.id, item_id=item.id)
    assert links_after[0].revoked_at is not None


def test_revoke_unknown_link_returns_false(session, tenant):
    ok = sharing_repo.revoke_share_link(session, tenant_id=tenant.id, link_id="nope")
    assert ok is False


def test_get_active_share_link_returns_none_for_unknown_id(session, tenant):
    assert sharing_repo.get_active_share_link(session, tenant_id=tenant.id, link_id="nope") is None


def test_get_active_share_link_returns_none_for_expired_link(session, tenant, user, item):
    link = sharing_repo.create_share_link(
        session, tenant_id=tenant.id, item_id=item.id, created_by=user.id, ttl_seconds=-1
    )
    session.commit()
    assert sharing_repo.get_active_share_link(session, tenant_id=tenant.id, link_id=link.id) is None


def test_resolve_rejects_revoked_link_even_before_token_expiry(session, tenant, user, item):
    # Le point qui distingue ce mécanisme de export_tokens.py (spec §6.1) :
    # un jeton valide ET non expiré doit néanmoins être rejeté si la ligne
    # share_link correspondante porte revoked_at non NULL — la ligne prime
    # sur le TTL du jeton lui-même.
    link = sharing_repo.create_share_link(
        session, tenant_id=tenant.id, item_id=item.id, created_by=user.id, ttl_seconds=86400
    )
    session.commit()
    assert (
        sharing_repo.get_active_share_link(session, tenant_id=tenant.id, link_id=link.id)
        is not None
    )

    sharing_repo.revoke_share_link(session, tenant_id=tenant.id, link_id=link.id)
    session.commit()

    assert sharing_repo.get_active_share_link(session, tenant_id=tenant.id, link_id=link.id) is None


def test_get_active_share_link_cross_tenant_returns_none(session, tenant, user, item):
    link = sharing_repo.create_share_link(
        session, tenant_id=tenant.id, item_id=item.id, created_by=user.id, ttl_seconds=86400
    )
    session.commit()
    assert (
        sharing_repo.get_active_share_link(session, tenant_id="other-tenant", link_id=link.id)
        is None
    )
