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


def _site_body(title: str, slug: str | None = None) -> dict:
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
    if slug is not None:
        body["slug"] = slug
    return body


def test_create_site_genere_slug(client):
    res = client.post("/v1/configs", json=_site_body("Mon Portail"))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/v1/items/{item_id}").json()
    assert item["resourceType"] == "site"
    assert item["slug"] == "mon-portail"


def test_create_site_slug_explicite_collision_409(client):
    assert client.post("/v1/configs", json=_site_body("A", slug="pris")).status_code == 201
    res = client.post("/v1/configs", json=_site_body("B", slug="pris"))
    assert res.status_code == 409
