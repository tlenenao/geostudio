# SPDX-License-Identifier: Apache-2.0
"""ARC-02 : `sortby`, `datetime`, `crs`/`bbox-crs` sur GET /collections/{id}/items
(PostGIS réel, vraie RLS ; même patron que test_features_integration.py)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

ROWS = [  # nom, quand, lon, lat
    ("charlie", "2024-12-31T23:00:00Z", 1.0, 45.0),
    ("alpha", "2025-01-01T10:00:00Z", 2.0, 46.0),
    ("bravo", "2025-06-15T08:30:00Z", 3.0, 47.0),
    ("alpha", "2025-07-01T00:00:00Z", 4.0, 48.0),
]
URL = "/v1/collections/demo_a2/items"


@pytest.fixture()
def client(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_a2"))
        conn.execute(
            text(
                "CREATE TABLE demo_a2 (id serial PRIMARY KEY, nom text NOT NULL, "
                "quand timestamptz, geom geometry(Point, 4326))"
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
    assert c.post("/v1/collections", json={"tableName": "demo_a2"}).status_code == 201
    for nom, quand, lon, lat in ROWS:
        r = c.post(
            URL,
            json={
                "type": "Feature",
                "properties": {"nom": nom, "quand": quand},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            },
        )
        assert r.status_code == 201, r.text
    yield c
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_a2"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _noms(r):
    assert r.status_code == 200, r.text
    return [f["properties"]["nom"] for f in r.json()["features"]]


def test_sortby_desc_then_asc(client):
    assert _noms(client.get(URL, params={"sortby": "-nom"})) == [
        "charlie",
        "bravo",
        "alpha",
        "alpha",
    ]
    assert _noms(client.get(URL, params={"sortby": "nom"}))[0] == "alpha"
    # tri multiple, PK en départage : (nom asc, quand desc)
    r = client.get(URL, params={"sortby": "nom,-quand"})
    assert [f["properties"]["quand"][:10] for f in r.json()["features"]][:2] == [
        "2025-07-01",
        "2025-01-01",
    ]


def test_sortby_unknown_column_is_400_problem(client):
    for bad in ("nope", "-nope", "geom", "nom;drop table x", ""):
        r = client.get(URL, params={"sortby": bad})
        assert r.status_code == 400, bad
        assert r.json()["errors"][0]["code"] == "invalid_sortby"


def test_pagination_is_correct_under_custom_sort(client):
    seen, url = [], f"{URL}?sortby=-nom&limit=3"
    for _ in range(3):
        body = client.get(url).json()
        seen += [f["properties"]["nom"] for f in body["features"]]
        nxt = [lk for lk in body["links"] if lk["rel"] == "next"]
        if not nxt:
            break
        assert "cursor=" not in nxt[0]["href"] and "offset=3" in nxt[0]["href"]
        url = nxt[0]["href"]
    assert seen == ["charlie", "bravo", "alpha", "alpha"]
    assert client.get(URL, params={"sortby": "-nom", "cursor": "e30"}).status_code == 400


def test_default_order_keeps_keyset_cursor(client):
    body = client.get(URL, params={"limit": 2}).json()
    assert any("cursor=" in lk["href"] for lk in body["links"] if lk["rel"] == "next")


def test_datetime_open_interval_and_instant(client):
    assert _noms(client.get(URL, params={"datetime": "2025-01-01T00:00:00Z/.."})) == [
        "alpha",
        "bravo",
        "alpha",
    ]
    assert _noms(client.get(URL, params={"datetime": "../2025-01-01"})) == ["charlie", "alpha"]
    assert _noms(client.get(URL, params={"datetime": "2025-06-15T08:30:00Z"})) == ["bravo"]
    assert _noms(client.get(URL, params={"datetime": "2025-01-01/2025-06-30"})) == [
        "alpha",
        "bravo",
    ]


@pytest.mark.parametrize("odd", ["2024-W01-1", "2024-01-01T10", "20250615", "2025-06-15T08"])
def test_datetime_iso_forms_postgres_cannot_cast_do_not_500(client, odd):
    # fromisoformat les accepte mais Postgres rejette la chaîne brute : on lie
    # l'objet parsé, pas la chaîne.
    assert client.get(URL, params={"datetime": odd}).status_code == 200


@pytest.mark.parametrize("bad", ["pas-une-date", "../..", "a/b/c", "2025-13-45/.."])
def test_datetime_invalid_is_400(client, bad):
    r = client.get(URL, params={"datetime": bad})
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "invalid_datetime"


def test_crs_lambert93_matches_postgis_transform(client, pg_engine):
    r = client.get(URL, params={"crs": "EPSG:2154", "sortby": "nom,-quand"})
    assert r.status_code == 200
    assert r.headers["Content-Crs"] == "<http://www.opengis.net/def/crs/EPSG/0/2154>"
    got = r.json()["features"][0]["geometry"]["coordinates"]  # alpha 2025-07-01 (4, 48)
    with pg_engine.connect() as conn:
        x, y = conn.execute(
            text(
                "SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Transform("
                "ST_SetSRID(ST_MakePoint(4, 48), 4326), 2154) g) q"
            )
        ).one()
    assert got == pytest.approx([x, y], abs=1e-3)
    assert got[0] > 1000  # bien des mètres, pas des degrés
    uri = "http://www.opengis.net/def/crs/EPSG/0/3857"
    assert client.get(URL, params={"crs": uri}).status_code == 200


def test_single_feature_crs_and_content_crs_header(client, pg_engine):
    # REV-367 a : `crs` aussi sur GET /items/{fid} ; l'ETag reste celui de la vue de stockage.
    base = client.get(f"{URL}/1")
    r = client.get(f"{URL}/1", params={"crs": "EPSG:2154"})
    assert r.status_code == 200
    assert r.headers["Content-Crs"] == "<http://www.opengis.net/def/crs/EPSG/0/2154>"
    assert r.json()["geometry"]["coordinates"][0] > 1000
    assert r.headers["ETag"] == base.headers["ETag"]
    assert client.get(f"{URL}/1", params={"crs": "EPSG:9999"}).status_code == 400


def test_crs84_is_advertised_and_epsg_4326_uri_refused(client):
    # Part 2 : l'URI EPSG/0/4326 impose lat/lon (non servi) ; CRS84 = lon/lat.
    crs84 = "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
    r = client.get(URL, params={"crs": crs84})
    assert r.status_code == 200
    assert r.headers["Content-Crs"] == f"<{crs84}>"
    r = client.get(URL, params={"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"})
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "invalid_crs"


def test_collection_description_lists_storage_crs(client):
    body = client.get("/v1/collections/demo_a2").json()
    assert body["storageCrs"] == "http://www.opengis.net/def/crs/OGC/1.3/CRS84"
    assert body["storageCrs"] in body["crs"]
    assert "http://www.opengis.net/def/crs/EPSG/0/2154" in body["crs"]


def test_crs_unsupported_is_400(client):
    for bad in ("EPSG:9999", "bidon", "EPSG:"):
        r = client.get(URL, params={"crs": bad})
        assert r.status_code == 400, bad
        assert r.json()["errors"][0]["code"] == "invalid_crs"


def test_bbox_crs_projected(client, pg_engine):
    with pg_engine.connect() as conn:
        x, y = conn.execute(
            text(
                "SELECT ST_X(g), ST_Y(g) FROM (SELECT ST_Transform("
                "ST_SetSRID(ST_MakePoint(2, 46), 4326), 2154) g) q"
            )
        ).one()
    r = client.get(
        URL,
        params={"bbox": f"{x - 10},{y - 10},{x + 10},{y + 10}", "bbox-crs": "EPSG:2154"},
    )
    assert _noms(r) == ["alpha"]
    # bbox projeté sans bbox-crs = hors bornes 4326 -> 400 (pas 500)
    assert client.get(URL, params={"bbox": f"{x},{y},{x + 1},{y + 1}"}).status_code == 400
