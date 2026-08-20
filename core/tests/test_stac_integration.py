# SPDX-License-Identifier: Apache-2.0
"""Bout en bout STAC sur PostGIS réel : vrai introspecteur, vraie DDL RLS,
vrai select_features sous rls_scope. Couvre §10 : navigation, portée anonyme
publié/public sans fuite, bbox, lien next, datetime granularité collection."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stac_roads"))
        conn.execute(
            text(
                "CREATE TABLE stac_roads (id serial PRIMARY KEY, "
                "n text, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
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
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    yield app, TestClient(app)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stac_roads"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _seed(app, client, public):
    client.post("/collections", json={"tableName": "stac_roads", "isPublic": public})
    for lon, lat in [(1.0, 44.0), (2.0, 45.0), (3.0, 46.0)]:
        client.post(
            "/collections/stac_roads/items",
            json={
                "type": "Feature",
                "properties": {"n": "x"},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            },
        )


def test_full_stac_navigation(pg_app):
    app, client = pg_app
    _seed(app, client, public=True)

    landing = client.get("/stac").json()
    assert "https://api.stacspec.org/v1.0.0/item-search" in landing["conformsTo"]

    col = client.get("/stac/collections/stac_roads").json()
    assert col["type"] == "Collection" and col["license"] == "other"
    bbox = col["extent"]["spatial"]["bbox"][0]
    assert bbox[0] == pytest.approx(1.0, abs=0.5) and bbox[2] == pytest.approx(3.0, abs=0.5)
    assert col["extent"]["temporal"]["interval"][0][1] is None

    items = client.get("/stac/collections/stac_roads/items?limit=2").json()
    assert items["type"] == "FeatureCollection" and len(items["features"]) == 2
    assert items["features"][0]["properties"]["datetime"].endswith("Z")
    assert any(l["rel"] == "next" for l in items["links"])

    # bbox filter : seul le point (1,44) est dans l'emprise serrée.
    tight = client.get("/stac/collections/stac_roads/items?bbox=0.9,43.9,1.1,44.1").json()
    assert len(tight["features"]) == 1

    search = client.get("/stac/search?collections=stac_roads&bbox=0,40,4,47").json()
    assert {f["collection"] for f in search["features"]} == {"stac_roads"}


def test_anonymous_sees_public_only_no_leak(pg_app):
    app, client = pg_app
    _seed(app, client, public=False)  # non publique
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    # Collection non publique → 404 non-fuyant (indistinguable d'inexistante).
    assert client.get("/stac/collections/stac_roads").status_code == 404
    assert client.get("/stac/collections/stac_roads/items").status_code == 404
    assert client.get("/stac/collections").json()["collections"] == []
    assert client.get("/stac/search").json()["features"] == []
    # Une collection inexistante renvoie le même 404.
    assert client.get("/stac/collections/does-not-exist").status_code == 404
