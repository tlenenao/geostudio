# SPDX-License-Identifier: Apache-2.0
"""sitemap.xml / robots.txt / aperçu social pour /sites/{slug} (SP-55 §3,
GAP-07). Rendus côté serveur (jamais exécutés côté client) — nécessaire pour
les robots de prévisualisation qui n'exécutent pas de JS (Slack, Twitter/X,
Facebook, Discord, WhatsApp…)."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_PUBLIC_BASE_URL = "https://gis.example.fr"


@pytest.fixture()
def client(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", _PUBLIC_BASE_URL)
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


def _create_site(client, title: str, slug: str, abstract: str = "") -> str:
    response = client.post(
        "/configs",
        json={"title": title, "config": _SITE_CONFIG, "slug": slug},
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["itemId"]
    if abstract:
        response = client.patch(f"/items/{item_id}", json={"abstract": abstract})
        assert response.status_code == 200, response.text
    return item_id


def _publish(client, item_id: str) -> None:
    response = client.patch(f"/items/{item_id}", json={"isPublished": True})
    assert response.status_code == 200, response.text


def test_sitemap_contains_only_published_sites(client):
    published_id = _create_site(client, "Portail public", "portail-public")
    _publish(client, published_id)
    _create_site(client, "Brouillon", "brouillon")  # jamais publié

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert f"{_PUBLIC_BASE_URL}/sites/portail-public" in body
    assert "brouillon" not in body


def test_sitemap_excludes_non_site_kinds(client):
    response = client.post(
        "/configs",
        json={
            "title": "Appli",
            "config": {
                "kind": "app",
                "layout": {
                    "type": "grid",
                    "items": [{"widget": "map", "x": 0, "y": 0, "w": 4, "h": 4}],
                },
            },
        },
    )
    assert response.status_code == 201, response.text
    _publish(client, response.json()["itemId"])

    del client.app.dependency_overrides[get_current_user]
    sitemap = client.get("/public/sitemap.xml")
    assert "Appli" not in sitemap.text


def test_robots_txt_references_sitemap(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/robots.txt")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/plain")
    assert f"Sitemap: {_PUBLIC_BASE_URL}/sitemap.xml" in response.text
    assert "Allow: /" in response.text


def test_social_preview_returns_meta_tags(client):
    item_id = _create_site(
        client, "Portail public", "portail-public", abstract="Un portail de démo"
    )
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/sites/portail-public/social-preview")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/html")
    body = response.text
    assert "<title>Portail public</title>" in body
    assert 'property="og:title" content="Portail public"' in body
    assert 'name="description" content="Un portail de démo"' in body
    assert 'property="og:description" content="Un portail de démo"' in body
    assert f'rel="canonical" href="{_PUBLIC_BASE_URL}/sites/portail-public"' in body


def test_social_preview_404_on_unknown_slug(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/sites/nexiste-pas/social-preview")
    assert response.status_code == 404


def test_social_preview_404_on_unpublished_site(client):
    _create_site(client, "Brouillon", "brouillon")

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/sites/brouillon/social-preview")
    assert response.status_code == 404


def test_social_preview_escapes_html_in_title(client):
    # Falsifiable (Step 4 du plan) : un titre contenant une séquence
    # injectable ne doit jamais apparaître telle quelle dans le HTML rendu.
    item_id = _create_site(client, "<script>alert(1)</script>", "malicieux")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/sites/malicieux/social-preview")
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text
