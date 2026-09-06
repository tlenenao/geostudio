# SPDX-License-Identifier: Apache-2.0
# NOTE : ce fichier tourne entièrement sur SQLite (dérogation documentée au
# brief de la Task 5, qui prescrivait client_admin/client_anon + un test
# @pytest.mark.postgis dans tests/public/). Le seul test qui a réellement
# besoin de deux tenants distincts (isolation de slug) n'a besoin d'aucune
# fonctionnalité spécifique à Postgres — juste d'un deuxième Tenant/User en
# base — donc il tourne lui aussi sur SQLite, comme le reste de la suite
# tests/test_public_routes.py dont ce fichier copie le patron de fixture.
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as repo
from app.main import create_app
from app.tenants.models import Tenant
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
            email=None,
            first_name="",
            last_name="",
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
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


_SITE_CONFIG = {
    "version": 1,
    "kind": "site",
    "theme": {},
    "dataSources": [],
    "layout": {"type": "grid", "breakpoints": {}, "items": []},
    "messages": [],
    "pages": [],
}

_APP_CONFIG = {
    "kind": "app",
    "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 4, "h": 4}]},
}


def _create_site(client, title: str, slug: str) -> str:
    response = client.post(
        "/v1/configs",
        json={"title": title, "config": _SITE_CONFIG, "slug": slug},
    )
    assert response.status_code == 201, response.text
    return response.json()["itemId"]


def _create_app(client, title: str) -> str:
    response = client.post("/v1/configs", json={"title": title, "config": _APP_CONFIG})
    assert response.status_code == 201, response.text
    return response.json()["itemId"]


def _publish(client, item_id: str) -> None:
    response = client.patch(f"/v1/items/{item_id}", json={"isPublished": True})
    assert response.status_code == 200, response.text


def test_site_publie_200(client):
    item_id = _create_site(client, "Portail", "mon-portail")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/mon-portail")
    assert response.status_code == 200
    assert response.json()["pk"] == item_id
    assert response.json()["slug"] == "mon-portail"


def test_site_non_publie_404_jamais_403(client):
    _create_site(client, "Brouillon", "brouillon")

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/brouillon")
    assert response.status_code == 404


def test_slug_inexistant_404(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/nexiste-pas")
    assert response.status_code == 404


def test_non_site_meme_publie_404(client):
    item_id = _create_app(client, "Appli")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/appli")
    assert response.status_code == 404


def test_isolation_tenant_meme_slug(client):
    # Un deuxième tenant enregistre un site publié sous le même slug
    # "shared" que celui recherché. La route /public/sites/{slug} résout
    # toujours contre le tenant "default" (aucun header/paramètre de tenant
    # n'existe côté route publique) : le site homonyme de l'autre tenant ne
    # doit jamais fuiter, même en 404 indirect (pas de leak d'existence).
    with client.session_factory() as session:
        other_tenant = Tenant(id="other", slug="other", name="Other")
        session.add(other_tenant)
        session.flush()
        bob = get_or_create_user(
            session,
            tenant_id="other",
            oidc_sub="sub-other",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        item = repo.create_item(
            session,
            tenant_id="other",
            owner_id=bob.id,
            resource_type="site",
            title="Shared",
            slug="shared",
        )
        item.is_published = True
        session.commit()

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/shared")
    assert response.status_code == 404
