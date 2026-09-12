# SPDX-License-Identifier: Apache-2.0
"""GET /collections/{id}/tiles/{z}/{x}/{y}.mvt accepte le jeton invité
(GAP-19, Task 5) — même patron que test_features_tiles_postgis.py, dont ce
fichier reprend le style de fixture (ST_AsMVT n'a aucun équivalent SQLite)."""

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

_SECRET = "test-tiles-guest-access-secret-padding"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        for table in ("demo_incidents_guest", "demo_other_guest"):
            conn.execute(text(f"DROP TABLE IF EXISTS {table}"))
            conn.execute(
                text(
                    f"CREATE TABLE {table} (id serial PRIMARY KEY, "
                    "titre text NOT NULL, geom geometry(Point, 4326))"
                )
            )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
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
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    client.post("/v1/collections", json={"tableName": "demo_incidents_guest", "isPublic": False})
    client.post("/v1/collections", json={"tableName": "demo_other_guest", "isPublic": False})
    client.post(
        "/v1/collections/demo_incidents_guest/items",
        json={
            "type": "Feature",
            "properties": {"titre": "Fuite"},
            "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
        },
    )
    body = {
        "kind": "app",
        "dataSources": [
            {
                "id": "ds1",
                "type": "features",
                "service": "core",
                "layer": "demo_incidents_guest",
                "query": {},
            }
        ],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    yield client, app, token
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents_guest"))
        conn.execute(text("DROP TABLE IF EXISTS demo_other_guest"))
        conn.execute(
            text(
                "TRUNCATE collection_shares, collections, config_revisions, configs, "
                "share_link, items, audit_log, users, tenants CASCADE"
            )
        )


def test_guest_token_reads_a_tile_of_a_referenced_private_collection(pg_app):
    client, app, token = pg_app
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/demo_incidents_guest/tiles/0/0/0.mvt",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 200
    assert r.content


def test_guest_token_gets_404_on_an_unreferenced_private_collection(pg_app):
    client, app, token = pg_app
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get(
        "/v1/collections/demo_other_guest/tiles/0/0/0.mvt",
        headers={"X-Share-Link-Token": token},
    )
    assert r.status_code == 404
