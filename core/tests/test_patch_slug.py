# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


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
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_site(client, title, slug=None):
    body = {
        "title": title,
        "config": {
            "version": 1,
            "kind": "site",
            "theme": {},
            "dataSources": [],
            "layout": {"type": "grid", "breakpoints": {}, "items": []},
            "messages": [],
            "pages": [],
        },
    }
    if slug:
        body["slug"] = slug
    res = client.post("/configs", json=body)
    assert res.status_code == 201, res.text
    return res.json()["itemId"]


def test_patch_slug_valide(client):
    item_id = _create_site(client, "Portail")
    res = client.patch(f"/items/{item_id}", json={"slug": "nouveau-slug"})
    assert res.status_code == 200, res.text
    assert res.json()["slug"] == "nouveau-slug"


def test_patch_slug_invalide_422(client):
    item_id = _create_site(client, "Portail")
    res = client.patch(f"/items/{item_id}", json={"slug": "Pas Valide"})
    assert res.status_code == 422


def test_patch_slug_collision_409(client):
    _create_site(client, "A", slug="pris")
    item_id = _create_site(client, "B")
    res = client.patch(f"/items/{item_id}", json={"slug": "pris"})
    assert res.status_code == 409


def test_patch_meme_slug_sur_soi_ok(client):
    item_id = _create_site(client, "A", slug="stable")
    res = client.patch(f"/items/{item_id}", json={"slug": "stable"})
    assert res.status_code == 200, res.text
