# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 7 : POST /compliance/users/{user_id}/erase.

Deux cas d'appel (spec §3.2) : `user_id` == l'appelant lui-même (ou le
littéral "me") — aucun privilège supplémentaire requis, chacun peut effacer
son propre compte ; un autre `user_id` du même tenant — requiert
admin.users.manage. Jamais d'anonymisation cross-tenant, même avec le
privilège."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-sub",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="regular-sub",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        other_tenant = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        s.add(other_tenant)
        s.flush()
        ensure_built_in_roles(s, tenant_id=other_tenant.id)
        outsider = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="outsider-sub",
            username="outsider",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()
        admin_id, regular_id, outsider_id = admin.id, regular.id, outsider.id

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, admin_id, regular_id, outsider_id


def _as_user_id(app, Session, user_id: str):
    from app.users.models import User

    def _get_current_user(session=None):
        with Session() as s:
            user = s.get(User, user_id)
            # Détaché : la route ouvre sa propre session via Depends(get_session).
            s.expunge(user)
            return user

    app.dependency_overrides[get_current_user] = _get_current_user


def test_regular_user_can_erase_their_own_account(env):
    app, client, _admin_id, regular_id, _outsider_id = env
    _as_user_id(app, client.session_factory, regular_id)
    resp = client.post(f"/compliance/users/{regular_id}/erase")
    assert resp.status_code == 204, resp.text


def test_regular_user_cannot_erase_another_user_without_privilege(env):
    app, client, admin_id, regular_id, _outsider_id = env
    _as_user_id(app, client.session_factory, regular_id)
    resp = client.post(f"/compliance/users/{admin_id}/erase")
    assert resp.status_code == 403, resp.text


def test_admin_can_erase_another_user_with_privilege(env):
    app, client, admin_id, regular_id, _outsider_id = env
    _as_user_id(app, client.session_factory, admin_id)
    resp = client.post(f"/compliance/users/{regular_id}/erase")
    assert resp.status_code == 204, resp.text


def test_cross_tenant_erasure_is_rejected_even_with_privilege(env):
    app, client, admin_id, _regular_id, outsider_id = env
    _as_user_id(app, client.session_factory, admin_id)
    resp = client.post(f"/compliance/users/{outsider_id}/erase")
    assert resp.status_code == 404, resp.text


def test_erase_me_literal_targets_the_caller(env):
    app, client, _admin_id, regular_id, _outsider_id = env
    _as_user_id(app, client.session_factory, regular_id)
    resp = client.post("/compliance/users/me/erase")
    assert resp.status_code == 204, resp.text


def test_erase_already_erased_user_returns_409(env):
    app, client, _admin_id, regular_id, _outsider_id = env
    _as_user_id(app, client.session_factory, regular_id)
    first = client.post(f"/compliance/users/{regular_id}/erase")
    assert first.status_code == 204
    _as_user_id(app, client.session_factory, regular_id)
    second = client.post(f"/compliance/users/{regular_id}/erase")
    assert second.status_code == 409, second.text
