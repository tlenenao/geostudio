# SPDX-License-Identifier: Apache-2.0
"""REV-277 / j02-005 (décision 2026-10-11) : `GET /groups` n'expose plus tout
l'annuaire de groupes du tenant. Par défaut : les groupes dont l'appelant est
membre ou créateur (tout le tenant pour `admin.users.manage`). `?q=` (>= 2
caractères, plafonné) cherche dans le tenant pour qui détient le partage."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.sharing import repository as sharing_repo
from app.sharing.models import GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _user(s, tenant_id, sub, role):
    u = get_or_create_user(
        s,
        tenant_id=tenant_id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
    )
    u.role_id = ensure_built_in_roles(s, tenant_id=tenant_id)[role].id
    u.is_admin = role == "admin"
    return u


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        t = get_or_create_default_tenant(s)
        admin = _user(s, t.id, "admin", "admin")
        reader = _user(s, t.id, "reader", "reader")
        creator = _user(s, t.id, "creator", "creator")
        s.flush()
        mine = sharing_repo.create_group(
            s, tenant_id=t.id, name="equipe-lecture", created_by=admin.id
        )
        s.add(GroupMember(group_id=mine.id, user_id=reader.id, tenant_id=t.id))
        sharing_repo.create_group(s, tenant_id=t.id, name="groupe-secret", created_by=admin.id)
        for i in range(30):
            sharing_repo.create_group(s, tenant_id=t.id, name=f"bulk-{i:02d}", created_by=admin.id)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    def as_(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_optional] = lambda: user

    return TestClient(app), as_, {"admin": admin, "reader": reader, "creator": creator}


def _names(r):
    assert r.status_code == 200, r.text
    return {g["name"] for g in r.json()}


def test_reader_lists_only_groups_he_belongs_to(env):
    c, as_, u = env
    as_(u["reader"])
    assert _names(c.get("/v1/groups")) == {"equipe-lecture"}


def test_creator_without_membership_does_not_see_the_tenant_directory(env):
    c, as_, u = env
    as_(u["creator"])
    assert _names(c.get("/v1/groups")) == set()


def test_sharer_finds_targetable_groups_through_a_capped_search(env):
    c, as_, u = env
    as_(u["creator"])
    assert _names(c.get("/v1/groups", params={"q": "secret"})) == {"groupe-secret"}
    assert len(c.get("/v1/groups", params={"q": "bulk"}).json()) == 20  # plafond
    assert c.get("/v1/groups", params={"q": "s"}).status_code == 422  # >= 2 caractères
    assert _names(c.get("/v1/groups", params={"q": "%%"})) == set()  # littéral


def test_group_admin_still_lists_the_whole_tenant(env):
    c, as_, u = env
    as_(u["admin"])
    assert len(c.get("/v1/groups").json()) == 32
