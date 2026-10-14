# SPDX-License-Identifier: Apache-2.0
"""Routes /v1/webhooks et /v1/file-triggers (ARC4-F6) : garde de privilège, egress à la
création, jamais de secret dans la réponse, rejeu."""

import socket

from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.outbox.models import OutboundWebhook, OutboxEvent
from app.roles.repository import ensure_built_in_roles
from app.secrets import crypto as secrets_crypto
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, BearerTokenPayload
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role

KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def _client(monkeypatch, *, admin: bool):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", KEY_B64)
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))],
    )
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
            bootstrap_admin=True,
        )
        ct, nonce = secrets_crypto.encrypt(
            SECRET_PAYLOAD_ADAPTER.dump_python(BearerTokenPayload(token="topsecret"))
        )
        secrets_repo.create_secret(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            name="sig",
            kind="bearer_token",
            ciphertext=ct,
            nonce=nonce,
        )
        if not admin:  # le 1er utilisateur d'un tenant est admin : l'appelant est un 2e compte
            user = get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub="b",
                username="bob",
                email=None,
                first_name="",
                last_name="",
            )
            roles = ensure_built_in_roles(s, tenant_id=tenant.id)
            set_user_role(
                s,
                tenant_id=tenant.id,
                user_id=user.id,
                role_id=roles["reader"].id,
                role_slug="reader",
            )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return client


_BODY = {"url": "https://hook.example.test/in", "eventTypes": ["item.created"], "secretName": "sig"}


def test_requires_automation_privilege(monkeypatch):
    client = _client(monkeypatch, admin=False)
    assert client.get("/v1/webhooks").status_code == 403
    assert client.post("/v1/webhooks", json=_BODY).status_code == 403
    assert client.get("/v1/file-triggers").status_code == 403


def test_private_url_is_rejected_at_creation(monkeypatch):
    client = _client(monkeypatch, admin=True)
    for url in ("http://127.0.0.1/hook", "http://192.168.1.10/hook", "http://10.0.0.5/hook"):
        r = client.post("/v1/webhooks", json={**_BODY, "url": url})
        assert r.status_code == 422, url


def test_webhooks_are_capped_per_tenant(monkeypatch):
    from app.webhooks import routes as webhook_routes

    monkeypatch.setattr(webhook_routes, "MAX_WEBHOOKS_PER_TENANT", 2, raising=False)
    client = _client(monkeypatch, admin=True)
    assert [client.post("/v1/webhooks", json=_BODY).status_code for _ in range(3)] == [
        201,
        201,
        409,
    ]


def test_unknown_secret_is_rejected(monkeypatch):
    client = _client(monkeypatch, admin=True)
    assert client.post("/v1/webhooks", json={**_BODY, "secretName": "nope"}).status_code == 422


def test_crud_and_replay_never_expose_the_secret(monkeypatch):
    client = _client(monkeypatch, admin=True)
    r = client.post("/v1/webhooks", json=_BODY)
    assert r.status_code == 201
    hook = r.json()
    assert "topsecret" not in r.text and hook["enabled"] is True
    assert [h["id"] for h in client.get("/v1/webhooks").json()] == [hook["id"]]

    with client.session_factory() as s:
        s.add(
            OutboxEvent(
                id="e1",
                tenant_id=s.get(OutboundWebhook, hook["id"]).tenant_id,
                webhook_id=hook["id"],
                event_type="item.created",
                payload={},
                status="failed",
                attempts=5,
            )
        )
        s.commit()
    assert client.get(f"/v1/webhooks/{hook['id']}/deliveries").json()[0]["status"] == "failed"
    assert client.post(f"/v1/webhooks/{hook['id']}/deliveries/e1/replay").status_code == 202
    assert client.get(f"/v1/webhooks/{hook['id']}/deliveries").json()[0]["status"] == "pending"

    r = client.patch(f"/v1/webhooks/{hook['id']}", json={"enabled": False})
    assert r.json()["enabled"] is False
    # destination désactivée : le rejeu est refusé explicitement
    assert client.post(f"/v1/webhooks/{hook['id']}/deliveries/e1/replay").status_code == 409
    assert client.delete(f"/v1/webhooks/{hook['id']}").status_code == 204
    assert client.get("/v1/webhooks").json() == []
