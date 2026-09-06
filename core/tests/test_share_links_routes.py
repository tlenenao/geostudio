# SPDX-License-Identifier: Apache-2.0
"""Routes /items/{id}/share-links (create/list/revoke) + /share-links/{token}
(résolution publique, sans authentification utilisateur) — GAP-12."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# >=32 bytes, même contrainte que test_export_tokens.py (InsecureKeyLengthWarning
# promue en échec dur par ce dépôt, filterwarnings = ["error", ...]).
_SECRET = "test-share-link-routes-secret-padding-0"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            setup_session,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="app",
            title="Item 1",
        )
        setup_session.commit()
        item_id = item.id

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    test_client.item_id = item_id  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def test_create_share_link_requires_write_access(client):
    response = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7})
    assert response.status_code == 201
    body = response.json()
    assert "/share-links/" in body["url"]
    assert "expiresAt" in body


def test_create_share_link_refuses_a_ttl_above_the_server_cap(client):
    response = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 31})
    assert response.status_code == 422


def test_create_share_link_on_unreadable_item_returns_404(client):
    response = client.post("/v1/items/does-not-exist/share-links", json={"ttlDays": 7})
    assert response.status_code == 404


def test_create_share_link_by_non_sharer_returns_403(client):
    with client.session_factory() as session:
        stranger = get_or_create_user(
            session,
            tenant_id=client.tenant.id,
            oidc_sub="sub-stranger",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        session.commit()

    client.app.dependency_overrides[get_current_user] = lambda: stranger
    try:
        response = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7})
    finally:
        client.app.dependency_overrides[get_current_user] = lambda: client.user
    assert response.status_code == 404  # item invisible au stranger (pas partagé)


def test_list_share_links_shows_status(client):
    client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7})
    listed = client.get(f"/v1/items/{client.item_id}/share-links")
    assert listed.status_code == 200
    rows = listed.json()
    assert len(rows) == 1
    assert rows[0]["revoked"] is False
    assert "id" in rows[0]
    assert "expiresAt" in rows[0]


def test_revoke_share_link(client):
    client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7})
    link_id = client.get(f"/v1/items/{client.item_id}/share-links").json()[0]["id"]
    response = client.delete(f"/v1/items/{client.item_id}/share-links/{link_id}")
    assert response.status_code == 204
    rows = client.get(f"/v1/items/{client.item_id}/share-links").json()
    assert rows[0]["revoked"] is True


def test_revoke_unknown_share_link_returns_404(client):
    response = client.delete(f"/v1/items/{client.item_id}/share-links/nope")
    assert response.status_code == 404


def test_resolve_share_link_by_token(client):
    created = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    # Résolution publique : PAS de get_current_user overridé pour cet appel
    # (le token porte à lui seul le droit d'accès) — mais l'override reste
    # posé globalement par ce client de test ; la route elle-même ne doit
    # jamais dépendre de get_current_user (vérifié en lisant la route, pas
    # seulement en observant que ce test passe avec l'override actif).
    response = client.get(f"/v1/share-links/{token}")
    assert response.status_code == 200
    body = response.json()
    assert body["itemId"] == client.item_id
    assert body["title"] == "Item 1"


def test_resolve_unknown_token_returns_401(client):
    response = client.get("/v1/share-links/not-a-real-token")
    assert response.status_code == 401


def test_resolve_revoked_link_returns_401_even_before_expiry(client):
    created = client.post(f"/v1/items/{client.item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    link_id = client.get(f"/v1/items/{client.item_id}/share-links").json()[0]["id"]
    client.delete(f"/v1/items/{client.item_id}/share-links/{link_id}")

    response = client.get(f"/v1/share-links/{token}")
    assert response.status_code == 401
