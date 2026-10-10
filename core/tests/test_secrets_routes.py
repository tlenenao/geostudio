# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role, ensure_built_in_roles
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

BEARER_BODY = {
    "name": "weather-api",
    "payload": {"kind": "bearer_token", "token": "s3cr3t-token-value"},
}


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
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
        # Rôle "reader" (zéro privilège) plutôt que le "creator" par défaut :
        # depuis que le Créateur porte automation.secrets.manage (SP-47 §2.2),
        # le "creator" par défaut ne fait plus un témoin valide de "utilisateur
        # sans privilège de secrets" pour les 3 tests test_*_requires_admin
        # ci-dessous.
        built_in_roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        regular.role_id = built_in_roles["reader"].id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_create_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/v1/secrets", json=BEARER_BODY).status_code == 403


def test_list_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.get("/v1/secrets").status_code == 403


def test_delete_requires_admin(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/v1/secrets", json=BEARER_BODY).json()
    _as(app, regular)
    assert client.delete(f"/v1/secrets/{created['id']}").status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/v1/secrets", json=BEARER_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "weather-api"
    assert body["kind"] == "bearer_token"
    assert set(body) == {"id", "name", "kind", "createdAt", "updatedAt"}
    listed = client.get("/v1/secrets").json()
    assert [s["name"] for s in listed] == ["weather-api"]


def test_create_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/v1/secrets", json=BEARER_BODY)
    assert "s3cr3t-token-value" not in r.text


def test_list_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/v1/secrets", json=BEARER_BODY)
    r = client.get("/v1/secrets")
    assert "s3cr3t-token-value" not in r.text


def test_create_duplicate_name_conflicts(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/v1/secrets", json=BEARER_BODY)
    r = client.post("/v1/secrets", json=BEARER_BODY)
    assert r.status_code == 409


def test_delete_removes_secret(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/secrets", json=BEARER_BODY).json()
    assert client.delete(f"/v1/secrets/{created['id']}").status_code == 204
    assert client.get("/v1/secrets").json() == []


def test_delete_missing_returns_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.delete("/v1/secrets/does-not-exist").status_code == 404


def test_delete_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/secrets", json=BEARER_BODY).json()

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s,
            tenant_id=other_tenant.id,
            oidc_sub="oa",
            username="other-admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.delete(f"/v1/secrets/{created['id']}").status_code == 404


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/v1/secrets", json=BEARER_BODY).json()
    client.delete(f"/v1/secrets/{created['id']}")

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
        payloads = list(s.scalars(select(AuditLog.payload)))
    assert actions == ["secret.create", "secret.delete"]
    assert all("s3cr3t-token-value" not in str(p) for p in payloads)


def test_create_app_fails_fast_without_master_key(monkeypatch):
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    with pytest.raises(KeyError):
        create_app()


def test_a_role_with_only_automation_secrets_manage_can_manage_secrets(env):
    app, client, Session, admin, regular = env
    with Session() as s:
        tenant_id = admin.tenant_id
        custom = create_role(
            s,
            tenant_id=tenant_id,
            name="Secrets pipeline",
            privileges=[Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )
        target = s.get(User, regular.id)
        assert target is not None
        target.role_id = custom.id
        s.commit()
        s.refresh(target)

    _as(app, target)
    resp = client.post("/v1/secrets", json=BEARER_BODY)
    assert resp.status_code == 201, resp.text
    resp = client.get("/v1/secrets")
    assert resp.status_code == 200
    secret_id = resp.json()[0]["id"]
    resp = client.delete(f"/v1/secrets/{secret_id}")
    assert resp.status_code == 204


def test_a_role_with_neither_secrets_privilege_is_rejected(env):
    app, client, Session, admin, regular = env
    with Session() as s:
        tenant_id = admin.tenant_id
        custom = create_role(s, tenant_id=tenant_id, name="Sans secrets", privileges=[])
        target = s.get(User, regular.id)
        assert target is not None
        target.role_id = custom.id
        s.commit()
        s.refresh(target)

    _as(app, target)
    resp = client.post("/v1/secrets", json=BEARER_BODY)
    assert resp.status_code == 403


def test_create_concurrent_duplicate_race_returns_409(env, monkeypatch):
    """The route pre-checks get_secret_by_name() before inserting, but two
    concurrent requests for the same name can both pass that check before
    either commits. Simulate the race by making the pre-check always report
    "no existing secret" (as it would for both racing requests) so the
    route falls through to repo.create_secret() — the second call then hits
    the real uq_connector_secrets_tenant_name DB constraint, and the route's
    except IntegrityError backstop must turn that into a 409, not a 500."""
    app, client, _, admin, _regular = env
    _as(app, admin)

    import app.secrets.routes as secrets_routes

    monkeypatch.setattr(secrets_routes.repo, "get_secret_by_name", lambda *a, **k: None)

    first = client.post("/v1/secrets", json=BEARER_BODY)
    assert first.status_code == 201

    second = client.post("/v1/secrets", json=BEARER_BODY)
    assert second.status_code == 409
    assert second.json()["detail"] == "Un secret porte déjà ce nom."


def _creator_with_secrets(env):
    app, client, Session, admin, regular = env
    with Session() as s:
        custom = create_role(
            s,
            tenant_id=admin.tenant_id,
            name="Secrets pipeline",
            privileges=[Privilege.AUTOMATION_SECRETS_MANAGE.value],
        )
        target = s.get(User, regular.id)
        target.role_id = custom.id
        s.commit()
        s.refresh(target)
    return target


def test_p16_01_creator_cannot_see_or_delete_someone_elses_secret(env):
    app, client, _, admin, _regular = env
    target = _creator_with_secrets(env)
    _as(app, admin)
    sid = client.post("/v1/secrets", json=BEARER_BODY).json()["id"]
    _as(app, target)
    assert client.get("/v1/secrets").json() == []
    assert client.delete(f"/v1/secrets/{sid}").status_code == 404
    assert (
        client.put(f"/v1/secrets/{sid}", json={"payload": BEARER_BODY["payload"]}).status_code
        == 404
    )
    _as(app, admin)
    assert len(client.get("/v1/secrets").json()) == 1


def test_p16_05_update_in_place_and_delete_refused_while_referenced(env):
    from app.configs.models import Config, ConfigRevision
    from app.items.repository import create_item

    app, client, Session, admin, _regular = env
    _as(app, admin)
    sid = client.post("/v1/secrets", json=BEARER_BODY).json()["id"]
    new = {"kind": "bearer_token", "token": "rotated"}
    r = client.put(f"/v1/secrets/{sid}", json={"payload": new})
    assert r.status_code == 200 and "rotated" not in r.text
    assert client.put(f"/v1/secrets/{sid}", json={"payload": {"kind": "smtp"}}).status_code == 422
    kind_change = {"kind": "basic_auth", "username": "u", "password": "p"}
    assert client.put(f"/v1/secrets/{sid}", json={"payload": kind_change}).status_code == 422
    with Session() as s:
        item = create_item(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            resource_type="pipeline",
            title="Pipe X",
        )
        s.add(Config(id="c1", tenant_id=admin.tenant_id, kind="pipeline", item_id=item.id))
        s.add(
            ConfigRevision(
                tenant_id=admin.tenant_id,
                config_id="c1",
                version=1,
                data={"nodes": [{"params": {"secretName": "weather-api"}}]},
            )
        )
        s.commit()
        item_id = item.id
    r = client.delete(f"/v1/secrets/{sid}")
    assert r.status_code == 409 and "Pipe X" in r.json()["detail"]
    assert r.json()["detail"] == (
        "Suppression impossible : encore utilisé par Pipe X. "
        "Retirez d'abord ce secret de ces éléments."
    )
    with Session() as s:
        s.query(ConfigRevision).filter_by(config_id="c1").delete()
        s.query(Config).filter_by(id="c1").delete()
        s.commit()
    assert item_id
    assert client.delete(f"/v1/secrets/{sid}").status_code == 204


def test_p16_06_07_validation_errors_do_not_echo_values_and_reject_empty(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post(
        "/v1/secrets",
        json={"name": "x", "payload": {"kind": "bearer_token", "token": ""}},
    )
    assert r.status_code == 422
    leaky = {
        "name": "x",
        "payload": {
            "kind": "basic_auth",
            "username": "u",
            "password": "TOPSECRET",
            "bogus": 1,
            "kind2": 3,
        },
    }
    leaky["payload"].pop("kind2")
    leaky["payload"]["username"] = ""
    r = client.post("/v1/secrets", json=leaky)
    assert r.status_code == 422
    assert "TOPSECRET" not in r.text
    r = client.post(
        "/v1/secrets", json={"name": "x", "payload": {"kind": "bearer_token", "token": 5}}
    )
    assert r.status_code == 422 and "input" not in r.text


def test_rev273c_409_lists_only_items_the_caller_can_read(env):
    from app.configs.models import Config, ConfigRevision
    from app.items.repository import create_item

    app, client, Session, admin, _regular = env
    with Session() as s:
        bob = get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(bob)
    _as(app, bob)
    sid = client.post("/v1/secrets", json=BEARER_BODY).json()["id"]
    with Session() as s:
        for n, (title, owner) in enumerate([("Mine", bob.id), ("Theirs", admin.id)]):
            item = create_item(
                s,
                tenant_id=admin.tenant_id,
                owner_id=owner,
                resource_type="pipeline",
                title=title,
            )
            s.add(Config(id=f"c{n}", tenant_id=admin.tenant_id, kind="pipeline", item_id=item.id))
            s.add(
                ConfigRevision(
                    tenant_id=admin.tenant_id,
                    config_id=f"c{n}",
                    version=1,
                    data={"nodes": [{"params": {"secretName": "weather-api"}}]},
                )
            )
        s.commit()
    r = client.delete(f"/v1/secrets/{sid}")
    assert r.status_code == 409
    detail = r.json()["detail"]
    assert "Mine" in detail
    assert "Theirs" not in detail
    assert "1 autre objet non visible" in detail
    assert detail.startswith("Suppression impossible : encore utilisé par Mine et 1 autre")


def test_rev300_m6_409_visibility_check_is_not_n_plus_1(env):
    """REV-300 M6 : le nombre de requêtes du DELETE 409 ne croît pas avec le
    nombre d'objets citant le secret (plus de `can()` par objet)."""
    from sqlalchemy import event

    from app.configs.models import Config, ConfigRevision
    from app.items.repository import create_item

    app, client, Session, admin, _regular = env
    with Session() as s:
        bob = get_or_create_user(
            s,
            tenant_id=admin.tenant_id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        s.refresh(bob)
    _as(app, bob)

    def statements_for_delete(secret_name: str, n_usages: int) -> int:
        body = {"name": secret_name, "payload": BEARER_BODY["payload"]}
        sid = client.post("/v1/secrets", json=body).json()["id"]
        with Session() as s:
            for n in range(n_usages):
                item = create_item(
                    s,
                    tenant_id=admin.tenant_id,
                    owner_id=admin.id,
                    resource_type="pipeline",
                    title=f"{secret_name}-{n}",
                )
                cid = f"{secret_name}-c{n}"
                s.add(Config(id=cid, tenant_id=admin.tenant_id, kind="pipeline", item_id=item.id))
                s.add(
                    ConfigRevision(
                        tenant_id=admin.tenant_id,
                        config_id=cid,
                        version=1,
                        data={"nodes": [{"params": {"secretName": secret_name}}]},
                    )
                )
            s.commit()
        seen: list[str] = []
        engine = Session.kw["bind"]

        def count(conn, cursor, statement, *a):
            seen.append(statement)

        event.listen(engine, "before_cursor_execute", count)
        try:
            assert client.delete(f"/v1/secrets/{sid}").status_code == 409
        finally:
            event.remove(engine, "before_cursor_execute", count)
        return len(seen)

    assert statements_for_delete("few", 2) == statements_for_delete("many", 8)


def test_rev273e_post_smtp_without_tls_remote_is_422_and_does_not_echo_password(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    smtp = {
        "kind": "smtp",
        "host": "smtp.example.test",
        "port": 25,
        "username": "u",
        "password": "ultra-secret-pw",
        "useTls": False,
        "fromAddress": "a@example.test",
    }
    r = client.post("/v1/secrets", json={"name": "smtp-clear", "payload": smtp})
    assert r.status_code == 422
    assert "useTls" in r.text and "ultra-secret-pw" not in r.text
    ok = client.post(
        "/v1/secrets",
        json={"name": "smtp-local", "payload": {**smtp, "host": "localhost"}},
    )
    assert ok.status_code == 201
