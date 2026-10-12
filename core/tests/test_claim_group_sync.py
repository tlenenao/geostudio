# SPDX-License-Identifier: Apache-2.0
"""ARC-24 (ADR 0022) : appartenance aux groupes alimentée par les claims OIDC."""

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth import dependency
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.guards import has_privilege
from app.sharing import claim_sync
from app.sharing import repository as repo
from app.sharing.models import GroupClaimMapping, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

ISS = "https://keycloak.example/realms/geostudio"


@pytest.fixture()
def Session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


@pytest.fixture()
def oidc(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", ISS)
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    class _K:
        def __init__(self, k):
            self.key = k

    class _C:
        def get_signing_key_from_jwt(self, _t):
            return _K(key.public_key())

    monkeypatch.setattr(dependency, "_jwks_client", lambda: _C())

    def login(session, **extra):
        claims = {
            "sub": "sub-1",
            "aud": "geostudio-core",
            "iss": ISS,
            "preferred_username": "al",
            **extra,
        }
        token = jwt.encode(claims, key, algorithm="RS256")
        return dependency.get_current_user(authorization=f"Bearer {token}", session=session)

    return login


def _setup(session, claim="SIG"):
    tenant = get_or_create_default_tenant(session)
    admin = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="adm",
        username="adm",
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=True,
    )
    g = repo.create_group(session, tenant_id=tenant.id, name="SIG", created_by=admin.id)
    session.add(
        GroupClaimMapping(
            id="m1", tenant_id=tenant.id, group_id=g.id, claim_value=claim, created_by=admin.id
        )
    )
    session.commit()
    return tenant, admin, g


def _members(session, gid):
    rows = session.scalars(select(GroupMember).where(GroupMember.group_id == gid))
    return {m.user_id: m.origin for m in rows}


def test_login_joins_mapped_group_then_removed_when_claim_disappears(Session, oidc):
    with Session() as s:
        _, _, g = _setup(s)
        u = oidc(s, groups=["SIG", "autre"])
        s.commit()
        assert _members(s, g.id) == {u.id: "claim"}
        oidc(s, groups=["SIG"])  # idempotence
        s.commit()
        assert _members(s, g.id) == {u.id: "claim"}
        oidc(s, groups=["autre"])  # retrait côté IdP
        s.commit()
        assert _members(s, g.id) == {}


def test_manual_membership_is_never_removed_and_manual_add_wins(Session, oidc):
    with Session() as s:
        t, admin, g = _setup(s)
        u = oidc(s, groups=[])
        s.add(GroupMember(group_id=g.id, user_id=u.id, tenant_id=t.id))  # manual
        s.commit()
        oidc(s, groups=["x"])
        s.commit()
        assert _members(s, g.id) == {u.id: "manual"}
        oidc(s, groups=["SIG"])
        s.commit()
        assert _members(s, g.id) == {u.id: "manual"}
        s.execute(GroupMember.__table__.update().values(origin="claim"))
        assert repo.add_member(
            s, tenant_id=t.id, group_id=g.id, user_id=u.id, caller_id=admin.id, as_admin=True
        )
        assert _members(s, g.id) == {u.id: "manual"}


@pytest.mark.parametrize("bad", ["SIG", {"SIG": 1}, 42])
def test_malformed_claim_is_ignored_without_login_error_nor_removal(Session, oidc, bad):
    with Session() as s:
        _, _, g = _setup(s)
        u = oidc(s, groups=["SIG"])
        s.commit()
        again = oidc(s, groups=bad)
        s.commit()
        assert again.id == u.id
        assert _members(s, g.id) == {u.id: "claim"}


def test_non_string_entries_and_unknown_values_ignored(Session, oidc):
    with Session() as s:
        _, _, g = _setup(s)
        u = oidc(s, groups=[1, None, "", "inconnu", "SIG"])
        s.commit()
        assert _members(s, g.id) == {u.id: "claim"}


def test_no_privilege_escalation(Session, oidc):
    with Session() as s:
        _setup(s)
        before = oidc(s, groups=[])
        snap = (before.role_id, before.is_admin)
        privs = ("admin.users.manage", "catalog.manage")
        before_privs = {p: has_privilege(s, before, p) for p in privs}
        after = oidc(s, groups=["SIG"])
        assert (after.role_id, after.is_admin) == snap
        assert {p: has_privilege(s, after, p) for p in privs} == before_privs


def test_sync_failure_never_blocks_login(Session, oidc, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("db hiccup")

    monkeypatch.setattr(claim_sync, "sync_claim_memberships", boom)
    with Session() as s:
        _setup(s)
        assert oidc(s, groups=["SIG"]).username == "al"


def test_custom_claim_name(Session, oidc, monkeypatch):
    monkeypatch.setenv("CORE_OIDC_GROUPS_CLAIM", "roles_sig")
    with Session() as s:
        _, _, g = _setup(s)
        u = oidc(s, roles_sig=["SIG"], groups=[])
        s.commit()
        assert _members(s, g.id) == {u.id: "claim"}


def test_mock_mode_login_unaffected(Session, monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    with Session() as s:
        _setup(s)
        user = dependency.get_current_user(authorization="Bearer x", session=s)
        assert user.username == "mockuser"


# --- API d'administration du mapping ---------------------------------------


@pytest.fixture()
def api(Session):
    with Session() as s:
        tenant, admin, g = _setup(s)
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="cr",
            username="cr",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        ids = (admin.id, creator.id, g.id)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    state = {"who": ids[0]}

    def who():
        with Session() as s2:
            u = s2.get(User, state["who"])
            s2.expunge(u)
            return u

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = who
    c = TestClient(app)
    c.state, c.ids, c.Session = state, ids, Session  # type: ignore[attr-defined]
    return c


def test_mapping_crud_audited_and_admin_only(api):
    admin_id, creator_id, gid = api.ids
    listed = api.get("/v1/groups/claim-mappings").json()
    assert [m["claimValue"] for m in listed] == ["SIG"]
    r = api.post("/v1/groups/claim-mappings", json={"groupId": gid, "claimValue": "RH"})
    assert r.status_code == 201
    dup = api.post("/v1/groups/claim-mappings", json={"groupId": gid, "claimValue": "RH"})
    assert dup.status_code == 409
    unknown = api.post("/v1/groups/claim-mappings", json={"groupId": "nope", "claimValue": "x"})
    assert unknown.status_code == 404
    assert api.delete(f"/v1/groups/claim-mappings/{r.json()['id']}").status_code == 204
    with api.Session() as s:
        actions = {a.action for a in s.scalars(select(AuditLog))}
    assert {"group.claim_mapping.create", "group.claim_mapping.delete"} <= actions
    api.state["who"] = creator_id
    assert api.get("/v1/groups/claim-mappings").status_code == 403
    denied = api.post("/v1/groups/claim-mappings", json={"groupId": gid, "claimValue": "y"})
    assert denied.status_code == 403
