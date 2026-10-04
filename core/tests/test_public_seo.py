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
        "/v1/configs",
        json={"title": title, "config": _SITE_CONFIG, "slug": slug},
    )
    assert response.status_code == 201, response.text
    item_id = response.json()["itemId"]
    if abstract:
        response = client.patch(f"/v1/items/{item_id}", json={"abstract": abstract})
        assert response.status_code == 200, response.text
    return item_id


def _publish(client, item_id: str) -> None:
    response = client.patch(f"/v1/items/{item_id}", json={"isPublished": True})
    assert response.status_code == 200, response.text


def test_sitemap_contains_only_published_sites(client):
    published_id = _create_site(client, "Portail public", "portail-public")
    _publish(client, published_id)
    _create_site(client, "Brouillon", "brouillon")  # jamais publié

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sitemap.xml")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/xml")
    body = response.text
    assert f"{_PUBLIC_BASE_URL}/sites/portail-public" in body
    assert "brouillon" not in body


def test_sitemap_excludes_non_site_kinds(client):
    response = client.post(
        "/v1/configs",
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
    sitemap = client.get("/v1/public/sitemap.xml")
    assert "Appli" not in sitemap.text


def test_robots_txt_references_sitemap(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/robots.txt")
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
    response = client.get("/v1/public/sites/portail-public/social-preview")
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
    response = client.get("/v1/public/sites/nexiste-pas/social-preview")
    assert response.status_code == 404


def test_social_preview_404_on_unpublished_site(client):
    _create_site(client, "Brouillon", "brouillon")

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/brouillon/social-preview")
    assert response.status_code == 404


def test_social_preview_escapes_html_in_title(client):
    # Falsifiable (Step 4 du plan) : un titre contenant une séquence
    # injectable ne doit jamais apparaître telle quelle dans le HTML rendu.
    item_id = _create_site(client, "<script>alert(1)</script>", "malicieux")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/v1/public/sites/malicieux/social-preview")
    assert response.status_code == 200
    assert "<script>alert(1)</script>" not in response.text
    assert "&lt;script&gt;" in response.text


def _make_collection(client, cid: str, title: str, *, is_public: bool):
    from app.collections import repository as collections_repo

    with client.session_factory() as s:
        collections_repo.create_collection(
            s,
            tenant_id=client.tenant.id,
            owner_id=client.user.id,
            table_name=cid,
            title=title,
            description="Desc <b>x</b>",
            is_public=is_public,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.commit()


def test_sitemap_covers_sites_items_and_public_datasets_with_lastmod(client):
    site = _create_site(client, "Portail", "portail")
    _publish(client, site)
    r = client.post(
        "/v1/configs",
        json={
            "title": "Appli",
            "config": {
                "kind": "app",
                "layout": {"type": "grid", "items": []},
            },
        },
    )
    app_id = r.json()["itemId"]
    _publish(client, app_id)
    _make_collection(client, "ouvert", "Ouvert", is_public=True)
    _make_collection(client, "secret", "Secret", is_public=False)

    del client.app.dependency_overrides[get_current_user]
    body = client.get("/v1/public/sitemap.xml").text
    assert f"{_PUBLIC_BASE_URL}/sites/portail</loc><lastmod>" in body
    assert f"{_PUBLIC_BASE_URL}/public/items/{app_id}</loc><lastmod>" in body
    assert f"{_PUBLIC_BASE_URL}/public/datasets/ouvert</loc>" in body
    assert "secret" not in body


def test_head_sitemap_and_robots_are_200(client):
    del client.app.dependency_overrides[get_current_user]
    for p in ("sitemap.xml", "robots.txt"):
        r = client.head(f"/v1/public/{p}")
        assert r.status_code == 200
        assert "max-age" in r.headers["cache-control"]


def test_social_preview_is_complete_for_sites(client):
    _publish(client, _create_site(client, "Portail", "portail", abstract="Résumé"))
    del client.app.dependency_overrides[get_current_user]
    body = client.get("/v1/public/sites/portail/social-preview").text
    assert f'property="og:url" content="{_PUBLIC_BASE_URL}/sites/portail"' in body
    assert 'property="og:type"' in body
    assert 'name="twitter:card"' in body
    assert "<h1>Portail</h1>" in body


def test_item_social_preview_with_public_thumbnail(client, monkeypatch):
    monkeypatch.setenv("CORE_BASE_URL", "https://api.gis.example.fr")  # REV-289b
    from app.items import routes as items_routes
    from app.items.storage import InMemoryThumbnailStore

    store = InMemoryThumbnailStore()
    client.app.dependency_overrides[items_routes.get_thumbnail_store] = lambda: store
    item_id = _create_site(client, "Portail", "portail")
    client.post(
        f"/v1/items/{item_id}/thumbnail", files={"file": ("t.png", b"PNGDATA", "image/png")}
    )
    # Non publié : ni aperçu ni vignette anonymes.
    del client.app.dependency_overrides[get_current_user]
    assert client.get(f"/v1/public/items/{item_id}/social-preview").status_code == 404
    assert client.get(f"/v1/public/items/{item_id}/thumbnail").status_code == 404

    client.app.dependency_overrides[get_current_user] = lambda: client.user
    _publish(client, item_id)
    del client.app.dependency_overrides[get_current_user]
    page = client.get(f"/v1/public/items/{item_id}/social-preview").text
    thumb = f"https://api.gis.example.fr/v1/public/items/{item_id}/thumbnail"
    assert f'property="og:image" content="{thumb}"' in page
    assert 'content="summary_large_image"' in page
    img = client.get(f"/v1/public/items/{item_id}/thumbnail")
    assert img.status_code == 200 and img.content == b"PNGDATA"
    assert img.headers["x-content-type-options"] == "nosniff"
    # un SVG uploadé (image/*) ne doit jamais exécuter de script dans l'origine du cœur
    assert "sandbox" in img.headers["content-security-policy"]
    listed = client.get("/v1/public/items").json()["items"][0]
    assert listed["thumbnailUrl"] == f"/public/items/{item_id}/thumbnail"


def test_dataset_social_preview_public_only_and_escaped(client):
    _make_collection(client, "ouvert", "A&B", is_public=True)
    _make_collection(client, "secret", "Secret", is_public=False)
    del client.app.dependency_overrides[get_current_user]
    ok = client.get("/v1/public/datasets/ouvert/social-preview")
    assert ok.status_code == 200
    assert "A&amp;B" in ok.text and "<b>x</b>" not in ok.text
    assert f'rel="canonical" href="{_PUBLIC_BASE_URL}/public/datasets/ouvert"' in ok.text
    assert client.get("/v1/public/datasets/secret/social-preview").status_code == 404
    assert client.get("/v1/public/datasets/nope/social-preview").status_code == 404


def test_sitemap_becomes_an_index_beyond_the_cap(client, monkeypatch):
    # REV-289a : au-delà du plafond (abaissé à 2), index + tranches.
    from app.public import routes as public_routes

    monkeypatch.setattr(public_routes, "_SITEMAP_MAX_URLS", 2)
    for slug in ("s1", "s2"):
        _publish(client, _create_site(client, slug.upper(), slug))
    _make_collection(client, "ouvert", "Ouvert", is_public=True)  # 3e URL

    del client.app.dependency_overrides[get_current_user]
    index = client.get("/v1/public/sitemap.xml").text
    assert "<sitemapindex" in index
    assert f"<loc>{_PUBLIC_BASE_URL}/sitemap-1.xml</loc>" in index
    assert f"<loc>{_PUBLIC_BASE_URL}/sitemap-2.xml</loc>" in index
    assert "sitemap-3.xml" not in index

    first = client.get("/v1/public/sitemap-1.xml")
    assert first.status_code == 200
    assert first.text.count("<url>") == 2
    second = client.get("/v1/public/sitemap-2.xml").text
    assert second.count("<url>") == 1
    assert f"{_PUBLIC_BASE_URL}/public/datasets/ouvert</loc>" in second
    assert client.get("/v1/public/sitemap-3.xml").status_code == 404
    assert client.get("/v1/public/sitemap-0.xml").status_code == 404
    assert client.head("/v1/public/sitemap-1.xml").status_code == 200


def test_sitemap_slices_partition_items_and_datasets_exactly(client, monkeypatch):
    # Items (3) non multiple du plafond (2) : les datasets débordent sur la
    # tranche 2 puis remplissent la 3 — chaque URL apparaît exactement une fois.
    from app.public import routes as public_routes

    monkeypatch.setattr(public_routes, "_SITEMAP_MAX_URLS", 2)
    for slug in ("s1", "s2", "s3"):
        _publish(client, _create_site(client, slug.upper(), slug))
    for cid in ("d1", "d2"):
        _make_collection(client, cid, cid, is_public=True)

    del client.app.dependency_overrides[get_current_user]
    assert client.get("/v1/public/sitemap.xml").text.count("<sitemap>") == 3
    slices = [client.get(f"/v1/public/sitemap-{n}.xml").text for n in (1, 2, 3)]
    assert [t.count("<url>") for t in slices] == [2, 2, 1]
    assert client.get("/v1/public/sitemap-4.xml").status_code == 404
    locs = [loc for t in slices for loc in t.split("<loc>")[1:]]
    assert len({loc.split("</loc>")[0] for loc in locs}) == 5
    assert sum("/public/datasets/" in loc for loc in locs) == 2


def test_sitemap_under_the_cap_stays_a_urlset(client):
    _publish(client, _create_site(client, "Portail", "portail"))
    del client.app.dependency_overrides[get_current_user]
    body = client.get("/v1/public/sitemap.xml").text
    assert "<urlset" in body and "<sitemapindex" not in body
    assert client.get("/v1/public/sitemap-1.xml").status_code == 404  # pas de tranche
