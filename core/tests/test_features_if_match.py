# SPDX-License-Identifier: Apache-2.0
"""ARC-04 : ETag par entité + `If-Match` optionnel sur PUT/DELETE (PostGIS réel,
table non vide au départ — piège n°8)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.features.etag import feature_etag, if_match_satisfied
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

BASE = "/v1/collections/demo_etag/items"


def _feat(titre, x=1.0):
    return {
        "type": "Feature",
        "properties": {"titre": titre},
        "geometry": {"type": "Point", "coordinates": [x, 45.0]},
    }


@pytest.fixture()
def client(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_etag"))
        conn.execute(
            text(
                "CREATE TABLE demo_etag (id serial PRIMARY KEY, titre text NOT NULL, "
                "geom geometry(Point, 4326))"
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

    class _S3:
        def delete_object(self, *, Bucket, Key):
            pass

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    c = TestClient(app)
    assert c.post("/v1/collections", json={"tableName": "demo_etag"}).status_code == 201
    # base non vide avant tout test d'en-tête
    for i in range(3):
        assert c.post(BASE, json=_feat(f"pre{i}", i)).status_code == 201
    yield c
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_etag"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _create(c, titre="x"):
    r = c.post(BASE, json=_feat(titre))
    assert r.status_code == 201
    return r.json()["id"], r.headers["ETag"]


def test_etag_on_post_get_and_put_agree(client):
    fid, etag_post = _create(client)
    got = client.get(f"{BASE}/{fid}")
    assert got.headers["ETag"] == etag_post
    r = client.put(f"{BASE}/{fid}", json=_feat("y"))
    assert r.status_code == 204
    assert r.headers["ETag"] != etag_post
    assert client.get(f"{BASE}/{fid}").headers["ETag"] == r.headers["ETag"]


def test_second_concurrent_put_gets_412(client):
    fid, etag = _create(client)
    first = client.put(f"{BASE}/{fid}", json=_feat("a"), headers={"If-Match": etag})
    assert first.status_code == 204
    second = client.put(f"{BASE}/{fid}", json=_feat("b"), headers={"If-Match": etag})
    assert second.status_code == 412
    assert second.headers["content-type"].startswith("application/problem+json")
    # la 2e écriture n'a pas eu lieu
    assert client.get(f"{BASE}/{fid}").json()["properties"]["titre"] == "a"
    # avec l'ETag frais, ça passe
    fresh = client.put(
        f"{BASE}/{fid}", json=_feat("c"), headers={"If-Match": first.headers["ETag"]}
    )
    assert fresh.status_code == 204


def test_without_header_behaviour_is_unchanged(client):
    fid, _ = _create(client)
    assert client.put(f"{BASE}/{fid}", json=_feat("a")).status_code == 204
    assert client.put(f"{BASE}/{fid}", json=_feat("b")).status_code == 204
    assert client.delete(f"{BASE}/{fid}").status_code == 204


def test_if_match_star_and_lists(client):
    fid, etag = _create(client)
    assert (
        client.put(f"{BASE}/{fid}", json=_feat("a"), headers={"If-Match": "*"}).status_code == 204
    )
    fresh = client.get(f"{BASE}/{fid}").headers["ETag"]
    hdr = f'"autre", {fresh}'
    assert (
        client.put(f"{BASE}/{fid}", json=_feat("b"), headers={"If-Match": hdr}).status_code == 204
    )


def test_delete_with_stale_etag_is_412_then_fresh_is_204(client):
    fid, etag = _create(client)
    client.put(f"{BASE}/{fid}", json=_feat("a"))
    assert client.delete(f"{BASE}/{fid}", headers={"If-Match": etag}).status_code == 412
    assert client.get(f"{BASE}/{fid}").status_code == 200
    fresh = client.get(f"{BASE}/{fid}").headers["ETag"]
    assert client.delete(f"{BASE}/{fid}", headers={"If-Match": fresh}).status_code == 204


def test_if_match_on_missing_feature_is_404(client):
    assert (
        client.put(f"{BASE}/999999", json=_feat("a"), headers={"If-Match": "*"}).status_code == 404
    )
    assert client.delete(f"{BASE}/999999", headers={"If-Match": "*"}).status_code == 404


def test_etag_helpers():
    f = {"id": 1, "geometry": None, "properties": {"a": 1}}
    assert feature_etag(f) == feature_etag({**f, "extra": "ignored"})
    assert feature_etag(f) != feature_etag({**f, "properties": {"a": 2}})
    assert if_match_satisfied("*", feature_etag(f))
    assert not if_match_satisfied('W/"x"', feature_etag(f))
