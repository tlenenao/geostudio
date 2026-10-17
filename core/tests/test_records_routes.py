# SPDX-License-Identifier: Apache-2.0
"""AUD-048 : OGC API Records Part 1 sur le catalogue d'items, même can() que /items."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

RECORDS = "/v1/records/collections/catalog/items"


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    c = TestClient(app)
    c.anonymous = lambda: app.dependency_overrides.__setitem__(  # type: ignore[attr-defined]
        get_current_user_optional, lambda: None
    )
    yield c
    engine.dispose()


def _create(client, title, kind="app"):
    r = client.post(
        "/v1/configs",
        json={"title": title, "config": {"kind": kind, "layout": {"type": "grid", "items": []}}},
    )
    assert r.status_code == 201, r.text
    return r.json()["itemId"]


def _publish(client, item_id):
    assert client.patch(f"/v1/items/{item_id}", json={"isPublished": True}).status_code == 200


def test_landing_conformance_and_catalog(client):
    links = {link["rel"] for link in client.get("/v1/records").json()["links"]}
    assert {"self", "conformance", "data"} <= links
    conf = client.get("/v1/records/conformance").json()["conformsTo"]
    assert "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/record-core" in conf
    cat = client.get("/v1/records/collections/catalog").json()
    assert (cat["id"], cat["type"], cat["itemType"]) == ("catalog", "Collection", "record")
    assert client.get("/v1/records/collections/nope").status_code == 404


def test_authenticated_sees_own_unpublished_anonymous_only_published(client):
    pub = _create(client, "Carte publiée des rivières")
    _publish(client, pub)
    _create(client, "Brouillon privé")
    r = client.get(RECORDS)
    assert r.headers["content-type"].startswith("application/geo+json")
    assert {f["properties"]["title"] for f in r.json()["features"]} == {
        "Carte publiée des rivières",
        "Brouillon privé",
    }
    client.anonymous()
    body = client.get(RECORDS, params={"q": "rivières"}).json()
    assert [f["id"] for f in body["features"]] == [pub]
    rec = body["features"][0]
    assert rec["type"] == "Feature" and rec["properties"]["type"] == "app"
    assert rec["conformsTo"] == [
        "http://www.opengis.net/spec/ogcapi-records-1/1.0/conf/record-core"
    ]
    assert client.get(f"{RECORDS}/{pub}").json()["id"] == pub
    assert client.get(RECORDS, params={"q": "Brouillon"}).json()["features"] == []


def test_unpublished_record_is_404_for_anonymous(client):
    draft = _create(client, "Brouillon")
    client.anonymous()
    assert client.get(f"{RECORDS}/{draft}").status_code == 404


def test_paging_links(client):
    for i in range(3):
        _publish(client, _create(client, f"Item {i}"))
    body = client.get(RECORDS, params={"limit": 2}).json()
    assert body["numberMatched"] == 3 and body["numberReturned"] == 2
    nxt = next(link["href"] for link in body["links"] if link["rel"] == "next")
    assert "page=2" in nxt
