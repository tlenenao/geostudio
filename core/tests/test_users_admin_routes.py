# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import create_role, ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        role_ids = {slug: role.id for slug, role in roles.items()}
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular, role_ids


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_list_users_requires_admin_users_manage(env):
    app, client, _, admin, regular, _roles = env
    _as(app, regular)
    assert client.get("/v1/users").status_code == 403
    _as(app, admin)
    body = client.get("/v1/users").json()
    assert body["total"] == 2
    assert {u["username"] for u in body["users"]} == {"admin", "regular"}


def test_promote_then_demote_via_role_id(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    r = client.patch(f"/v1/users/{regular.id}", json={"roleId": roles["admin"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "admin"
    r = client.patch(f"/v1/users/{regular.id}", json={"roleId": roles["reader"]})
    assert r.status_code == 200 and r.json()["roleSlug"] == "reader"


def test_last_admin_cannot_be_demoted(env):
    app, client, _, admin, _regular, roles = env
    _as(app, admin)
    assert (
        client.patch(f"/v1/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 409
    )


def test_anti_lockout_blocks_the_last_holder_of_a_privilege_split_across_two_custom_roles(env):
    # SP-42 / F-securite-autorisation-07 : la garde n'agissait qu'en
    # CONJONCTION sur les deux privilèges anti-lockout à la fois — inerte
    # dès qu'ils sont répartis sur deux rôles sur mesure distincts. R1 ne
    # porte que admin.users.manage, R2 ne porte que admin.roles.manage ;
    # aucun rôle du tenant ne les porte tous les deux à la fois.
    #
    # L'état de départ (Alice/R1, Bob/R2, personne ne détient les deux à la
    # fois) est construit par appel direct au dépôt — PAS à travers la route
    # PATCH /users elle-même gardée par ce même anti-lockout, qui bloquerait
    # légitimement la transition intermédiaire "admin perd un des deux
    # privilèges alors qu'il en est encore l'unique porteur conjoint". Cela
    # représente un tenant déjà dans cette configuration (ex. atteint via
    # CORE_ADMIN_SUBS), comme le note la trouvaille — le test exerce ensuite
    # la VRAIE route HTTP gardée pour l'assertion.
    app, client, Session, admin, regular, roles = env
    with Session() as s:
        r1 = create_role(s, tenant_id=admin.tenant_id, name="R1", privileges=["admin.users.manage"])
        r2 = create_role(s, tenant_id=admin.tenant_id, name="R2", privileges=["admin.roles.manage"])
        set_user_role(
            s, tenant_id=admin.tenant_id, user_id=admin.id, role_id=r1.id, role_slug=r1.slug
        )
        set_user_role(
            s, tenant_id=admin.tenant_id, user_id=regular.id, role_id=r2.id, role_slug=r2.slug
        )
        s.commit()

    # admin (désormais seul porteur de admin.users.manage, via R1 seul)
    # tente de se retirer ce privilège lui-même : avant le correctif, la
    # précondition en conjonction ne portait jamais puisque R1 seul ne
    # contient pas admin.roles.manage, laissant passer un 200.
    _as(app, admin)
    resp = client.patch(f"/v1/users/{admin.id}", json={"roleId": roles["reader"]})
    assert resp.status_code == 409, resp.text


def test_patch_unknown_user_404_and_non_admin_403(env):
    app, client, _, admin, regular, roles = env
    _as(app, admin)
    assert client.patch("/v1/users/nope", json={"roleId": roles["admin"]}).status_code == 404
    _as(app, regular)
    assert (
        client.patch(f"/v1/users/{admin.id}", json={"roleId": roles["reader"]}).status_code == 403
    )


def test_patch_user_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular, roles = env
    with Session() as s:
        other_tenant = Tenant(
            id=uuid.uuid4().hex, slug=f"other-{uuid.uuid4().hex[:8]}", name="Other"
        )
        s.add(other_tenant)
        s.flush()
        outsider = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="sub-outsider",
            username="outsider",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(outsider)

    _as(app, admin)
    assert (
        client.patch(f"/v1/users/{outsider.id}", json={"roleId": roles["admin"]}).status_code == 404
    )
    with Session() as s:
        refetched = s.get(User, outsider.id)
        assert refetched is not None
        assert refetched.role_id == outsider.role_id
        assert refetched.is_admin is False


def test_role_change_is_audited(env):
    app, client, Session, admin, regular, roles = env
    _as(app, admin)
    client.patch(f"/v1/users/{regular.id}", json={"roleId": roles["admin"]})
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    assert "user.role_change" in actions


def test_patch_user_rejects_an_unknown_role_id(env):
    app, client, _, admin, regular, _roles = env
    _as(app, admin)
    assert client.patch(f"/v1/users/{regular.id}", json={"roleId": "nope"}).status_code == 400


def test_list_users_filters_by_username(env):
    app, client, Session, admin, regular, _roles = env
    with Session() as s:
        get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="c",
            username="charlie",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()

    _as(app, admin)
    body = client.get("/v1/users?q=reg").json()
    assert body["total"] == 1
    assert {u["username"] for u in body["users"]} == {"regular"}

    body_ci = client.get("/v1/users?q=REG").json()
    assert body_ci["total"] == 1

    body_all = client.get("/v1/users").json()
    assert body_all["total"] == 3


# REV-085 : GET /users appelait get_role() une fois PAR utilisateur de la
# page (une requête par ligne) — même patron de garde-fou que
# tests/test_harvest_layers_no_nplus1.py : le nombre de requêtes SQL ne doit
# pas croître avec le nombre d'utilisateurs de la page.
def _build_users(n_users: int):
    from app.roles.repository import ensure_built_in_roles

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        for i in range(n_users):
            get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub=f"u{i}",
                username=f"user{i}",
                email=None,
                first_name="",
                last_name="",
            )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    return engine, TestClient(app)


def _count_queries(engine, fn):
    from sqlalchemy import event

    seen = 0

    def bump(conn, cursor, statement, params, context, executemany):
        nonlocal seen
        seen += 1

    event.listen(engine, "before_cursor_execute", bump)
    try:
        fn()
    finally:
        event.remove(engine, "before_cursor_execute", bump)
    return seen


@pytest.mark.parametrize("small,large", [(2, 12)])
def test_list_users_query_count_does_not_grow_with_page_size(small, large):
    counts = {}
    for n in (small, large):
        engine, client = _build_users(n)
        try:

            def call(client=client, n=n):
                response = client.get(f"/v1/users?pageSize={n + 5}")
                assert response.status_code == 200, response.text
                assert response.json()["total"] == n + 1  # + l'admin de la fixture

            counts[n] = _count_queries(engine, call)
        finally:
            engine.dispose()
    assert counts[small] == counts[large], (
        f"le nombre de requêtes croît avec le nombre d'utilisateurs : {counts} — "
        "c'est un N+1, probablement get_role() appelé ligne par ligne"
    )
