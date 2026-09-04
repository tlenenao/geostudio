# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.notifications import repository as notifications_repo
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    other_user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="b",
        username="bob",
        email=None,
        first_name="",
        last_name="",
    )
    session.commit()
    return session, tenant, user, other_user


def _create(session, *, tenant_id, recipient_user_id, status="success", kind="pipeline"):
    return notifications_repo.create_notification(
        session,
        tenant_id=tenant_id,
        recipient_user_id=recipient_user_id,
        kind=kind,
        status=status,
        item_id=None,
        item_resource_type="pipeline",
        item_title="Pipeline test",
    )


def test_create_notification_writes_all_fields(env):
    session, tenant, user, _other = env
    n = notifications_repo.create_notification(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        kind="export",
        status="failure",
        item_id=None,
        item_resource_type="map",
        item_title="Carte X",
        error_message="boom",
    )
    session.commit()
    assert n.id is not None
    assert n.kind == "export"
    assert n.status == "failure"
    assert n.error_message == "boom"
    assert n.read_at is None


def test_list_notifications_orders_most_recent_first_and_isolates_recipient(env):
    session, tenant, user, other_user = env
    first = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    second = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    _create(session, tenant_id=tenant.id, recipient_user_id=other_user.id)
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="all",
        page=1,
        page_size=20,
    )
    assert total == 2
    assert [r.id for r in rows] == [second.id, first.id]


def test_list_notifications_failures_only_filter(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="failures_only",
        page=1,
        page_size=20,
    )
    assert total == 1
    assert rows[0].id == failure.id


def test_list_notifications_none_preference_returns_nothing(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="none",
        page=1,
        page_size=20,
    )
    assert rows == []
    assert total == 0


def test_count_unread_matches_filter_and_read_state(env):
    session, tenant, user, _other = env
    _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="all"
        )
        == 2
    )
    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
        )
        == 1
    )

    notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=failure.id
    )
    session.commit()
    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
        )
        == 0
    )


def test_mark_notification_read_is_idempotent_and_scoped_to_recipient(env):
    session, tenant, user, other_user = env
    n = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    assert (
        notifications_repo.mark_notification_read(
            session, tenant_id=tenant.id, recipient_user_id=other_user.id, notification_id=n.id
        )
        is None
    )
    first = notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=n.id
    )
    session.commit()
    assert first.read_at is not None
    second = notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=n.id
    )
    assert second.read_at == first.read_at


def test_mark_all_notifications_read_respects_preference_filter(env):
    session, tenant, user, _other = env
    success = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="success")
    failure = _create(session, tenant_id=tenant.id, recipient_user_id=user.id, status="failure")
    session.commit()

    notifications_repo.mark_all_notifications_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, preference="failures_only"
    )
    session.commit()
    session.refresh(success)
    session.refresh(failure)
    assert success.read_at is None
    assert failure.read_at is not None


def test_list_notifications_paginates_beyond_the_first_page(env):
    """I5 (revue finale SP-39, spec §6) : aucun test n'exerçait page=2 avant
    ce correctif — tous les tests de pagination existants s'arrêtaient à
    page=1."""
    session, tenant, user, _other = env
    n1 = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    n2 = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    n3 = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    page1, total1 = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="all",
        page=1,
        page_size=2,
    )
    page2, total2 = notifications_repo.list_notifications(
        session,
        tenant_id=tenant.id,
        recipient_user_id=user.id,
        preference="all",
        page=2,
        page_size=2,
    )
    assert total1 == 3
    assert total2 == 3
    assert [r.id for r in page1] == [n3.id, n2.id]
    assert [r.id for r in page2] == [n1.id]


def test_notifications_are_isolated_by_tenant_even_with_the_same_relative_role(env):
    """I5 (revue finale SP-39, spec §6) : les 22 tests précédents de ce
    fichier partagent tous le même tenant — seule l'isolation
    inter-DESTINATAIRE (même tenant) était couverte, jamais l'isolation
    inter-TENANT. Tenant B a un utilisateur portant le même username/rôle
    relatif que le user du tenant A — la notification du tenant A ne doit
    être ni visible, ni comptable, ni marquable-lue depuis le tenant B."""
    session, tenant, user, _other = env
    tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
    session.add(tenant_b)
    session.flush()
    user_b = get_or_create_user(
        session,
        tenant_id=tenant_b.id,
        oidc_sub="a",  # même oidc_sub relatif que `user` du tenant A (scopé par tenant)
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    notif_a = _create(session, tenant_id=tenant.id, recipient_user_id=user.id)
    session.commit()

    rows, total = notifications_repo.list_notifications(
        session,
        tenant_id=tenant_b.id,
        recipient_user_id=user_b.id,
        preference="all",
        page=1,
        page_size=20,
    )
    assert rows == []
    assert total == 0

    assert (
        notifications_repo.count_unread_notifications(
            session, tenant_id=tenant_b.id, recipient_user_id=user_b.id, preference="all"
        )
        == 0
    )

    # Ni avec le mauvais recipient_user_id...
    assert (
        notifications_repo.mark_notification_read(
            session,
            tenant_id=tenant_b.id,
            recipient_user_id=user_b.id,
            notification_id=notif_a.id,
        )
        is None
    )
    # ...ni même avec le BON recipient_user_id mais le mauvais tenant : la
    # portée tenant seule doit suffire à bloquer, indépendamment du
    # recipient_user_id passé.
    assert (
        notifications_repo.mark_notification_read(
            session,
            tenant_id=tenant_b.id,
            recipient_user_id=user.id,
            notification_id=notif_a.id,
        )
        is None
    )
    # La notification reste bien lisible/marquable depuis son propre tenant.
    own_tenant_result = notifications_repo.mark_notification_read(
        session, tenant_id=tenant.id, recipient_user_id=user.id, notification_id=notif_a.id
    )
    assert own_tenant_result is not None
    assert own_tenant_result.read_at is not None


def test_notification_preference_defaults_to_all_and_round_trips(env):
    session, tenant, user, _other = env
    assert (
        notifications_repo.get_notification_preference(
            session, tenant_id=tenant.id, user_id=user.id
        )
        == "all"
    )
    notifications_repo.set_notification_preference(
        session, tenant_id=tenant.id, user_id=user.id, value="failures_only"
    )
    session.commit()
    assert (
        notifications_repo.get_notification_preference(
            session, tenant_id=tenant.id, user_id=user.id
        )
        == "failures_only"
    )
