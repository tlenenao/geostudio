# SPDX-License-Identifier: Apache-2.0
"""ARC-11 : WFS 2.0 (lecture) + OGC API Tiles servis par le cœur (ADR 0018).
PostGIS réel, vraie RLS. Critères : droits identiques à l'API Features, masquage
GAP-22 respecté, capacité absente quand le flag est éteint, activation par
collection."""

import xml.etree.ElementTree as ET

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

WFS = "http://www.opengis.net/wfs/2.0"
GML = "http://www.opengis.net/gml/3.2"
XSD = "http://www.w3.org/2001/XMLSchema"
OWS = "http://www.opengis.net/ows/1.1"
BASE = "/v1/ows/wfs"
ROWS = [("alpha", "s1", 1.0, 45.0), ("bravo", "s2", 2.0, 46.0), ("charlie", "s3", 3.0, 47.0)]


def _kvp(**kw):
    return {"service": "WFS", "version": "2.0.0", **kw}


@pytest.fixture()
def env(pg_engine, monkeypatch):
    monkeypatch.setenv("CORE_OWS_ENABLED", "true")
    return _build(pg_engine)


def _build(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_ows"))
        conn.execute(
            text(
                "CREATE TABLE demo_ows (id serial PRIMARY KEY, nom text, secret text, "
                "geom geometry(Point, 4326))"
            )
        )
    Session_ = make_session_factory(pg_engine)
    with Session_() as s:
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
        with request_scoped_session(Session_) as session:
            yield session

    class _S3:
        def delete_object(self, *, Bucket, Key):
            pass

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()

    def login(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_optional] = lambda: user

    login(admin)
    c = TestClient(app)
    assert c.post("/v1/collections", json={"tableName": "demo_ows"}).status_code == 201
    for nom, secret, lon, lat in ROWS:
        r = c.post(
            "/v1/collections/demo_ows/items",
            json={
                "type": "Feature",
                "properties": {"nom": nom, "secret": secret},
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
            },
        )
        assert r.status_code == 201, r.text
    return c, login, admin


@pytest.fixture(autouse=True)
def _cleanup(pg_engine):
    yield
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_ows"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _enable(c, **extra):
    r = c.patch(
        "/v1/collections/demo_ows",
        json={"owsEnabled": True, "isPublic": True, "sensitiveFields": ["secret"], **extra},
    )
    assert r.status_code == 200, r.text
    assert r.json()["owsEnabled"] is True


def _names(root):
    return [e.text.split(":")[-1] for e in root.iter(f"{{{WFS}}}Name")]


def test_flag_off_capability_is_absent(pg_engine, monkeypatch):
    monkeypatch.delenv("CORE_OWS_ENABLED", raising=False)
    c, _login, _admin = _build(pg_engine)
    assert c.get(BASE, params=_kvp(request="GetCapabilities")).status_code == 404
    assert c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/0/0/0").status_code == 404


def test_activation_is_per_collection(env):
    c, _login, _admin = env
    root = ET.fromstring(c.get(BASE, params=_kvp(request="GetCapabilities")).text)
    assert "demo_ows" not in _names(root)  # désactivée par défaut
    r = c.get(BASE, params=_kvp(request="GetFeature", typenames="demo_ows"))
    assert r.status_code == 404
    assert ET.fromstring(r.text).tag == f"{{{OWS}}}ExceptionReport"
    assert c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/0/0/0").status_code == 404
    _enable(c)
    root = ET.fromstring(c.get(BASE, params=_kvp(request="GetCapabilities")).text)
    assert "demo_ows" in _names(root)
    assert root.tag == f"{{{WFS}}}WFS_Capabilities" and root.get("version") == "2.0.0"


def test_describe_feature_type_hides_sensitive_for_anonymous(env):
    c, login, admin = env
    _enable(c)
    q = _kvp(request="DescribeFeatureType", typenames="demo_ows")
    login(None)
    anon = ET.fromstring(c.get(BASE, params=q).text)
    els = {e.get("name"): e.get("type") for e in anon.iter(f"{{{XSD}}}element")}
    assert "nom" in els and "geom" in els and "secret" not in els
    assert els["geom"] == "gml:PointPropertyType"
    login(admin)
    full = ET.fromstring(c.get(BASE, params=q).text)
    assert "secret" in {e.get("name") for e in full.iter(f"{{{XSD}}}element")}


def test_get_feature_gml32_axis_order_ids_and_paging(env):
    c, login, _admin = env
    _enable(c)
    login(None)  # anonyme sur collection publique : même porte que l'API Features
    r = c.get(
        BASE,
        params=_kvp(request="GetFeature", typenames="demo_ows", count=2, startindex=0),
    )
    assert r.status_code == 200, r.text
    assert "gml+xml" in r.headers["content-type"]
    root = ET.fromstring(r.text)
    assert root.tag == f"{{{WFS}}}FeatureCollection"
    assert root.get("numberReturned") == "2" and root.get("numberMatched") == "3"
    assert root.get("next") and "startindex=2" in root.get("next").lower()
    members = list(root.iter(f"{{{WFS}}}member"))
    feat = members[0][0]
    assert feat.get(f"{{{GML}}}id") == "demo_ows.1"
    assert feat.find("{http://geostudio.local/ows}nom").text == "alpha"
    assert feat.find("{http://geostudio.local/ows}secret") is None  # GAP-22
    point = next(feat.iter(f"{{{GML}}}Point"))
    assert point.get(f"{{{GML}}}id")
    assert point.get("srsName") == "urn:ogc:def:crs:EPSG::4326"
    assert next(point.iter(f"{{{GML}}}pos")).text.split() == ["45", "1"]  # lat lon
    page2 = ET.fromstring(
        c.get(BASE, params=_kvp(request="GetFeature", typenames="demo_ows", startindex=2)).text
    )
    assert page2.get("numberReturned") == "1" and page2.get("next") is None


def test_get_feature_geojson_bbox_cql_and_hits(env):
    c, login, admin = env
    _enable(c)
    login(admin)
    q = _kvp(request="GetFeature", typenames="demo_ows", outputformat="application/json")
    body = c.get(BASE, params=q).json()
    assert body["type"] == "FeatureCollection" and len(body["features"]) == 3
    assert "secret" in body["features"][0]["properties"]  # admin voit le sensible
    # BBOX en urn:EPSG::4326 = ordre lat,lon (WFS 2.0)
    box = "45.5,1.5,47.5,3.5,urn:ogc:def:crs:EPSG::4326"
    got = c.get(BASE, params={**q, "bbox": box}).json()["features"]
    assert [f["properties"]["nom"] for f in got] == ["bravo", "charlie"]
    got = c.get(BASE, params={**q, "cql_filter": "nom = 'alpha'"}).json()["features"]
    assert len(got) == 1
    assert c.get(BASE, params={**q, "cql_filter": "nom = 1; DROP"}).status_code == 400
    hits = ET.fromstring(
        c.get(BASE, params=_kvp(request="GetFeature", typenames="demo_ows", resulttype="hits")).text
    )
    assert hits.get("numberMatched") == "3" and hits.get("numberReturned") == "0"


def test_get_feature_srsname_projected(env):
    c, login, admin = env
    _enable(c)
    login(admin)
    r = c.get(
        BASE,
        params=_kvp(
            request="GetFeature",
            typenames="demo_ows",
            srsname="urn:ogc:def:crs:EPSG::3857",
            count=1,
        ),
    )
    point = next(ET.fromstring(r.text).iter(f"{{{GML}}}pos"))
    x, y = (float(v) for v in point.text.split())
    assert 111000 < x < 112000  # 1 degré de longitude en Web Mercator


def test_private_collection_is_invisible_to_anonymous(env):
    c, login, _admin = env
    assert c.patch("/v1/collections/demo_ows", json={"owsEnabled": True}).status_code == 200
    login(None)  # collection non publique : anonyme = rien (même porte que /items)
    root = ET.fromstring(c.get(BASE, params=_kvp(request="GetCapabilities")).text)
    assert "demo_ows" not in _names(root)
    for req in ("GetFeature", "DescribeFeatureType"):
        r = c.get(BASE, params=_kvp(request=req, typenames="demo_ows"))
        assert r.status_code == 404, req
        assert c.get("/v1/collections/demo_ows/items").status_code == r.status_code


def test_bad_requests_are_ows_exceptions(env):
    c, _login, _admin = env
    _enable(c)
    for q in (
        _kvp(request="Transaction"),
        _kvp(request="GetFeature"),
        _kvp(request="GetFeature", typenames="a,b"),
        _kvp(request="GetFeature", typenames="demo_ows", outputformat="text/x-nope"),
        _kvp(request="GetFeature", typenames="demo_ows", count="x"),
        _kvp(request="GetFeature", typenames="demo_ows", bbox="1,2,3"),
        {"service": "WMS", "request": "GetCapabilities"},
    ):
        r = c.get(BASE, params=q)
        assert r.status_code == 400, q
        assert ET.fromstring(r.text).tag == f"{{{OWS}}}ExceptionReport"


def test_ogc_tiles_same_bytes_and_rules_as_mvt_route(env):
    c, login, admin = env
    _enable(c)
    ogc = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/0/0/0")
    legacy = c.get("/v1/collections/demo_ows/tiles/0/0/0.mvt")
    assert ogc.status_code == 200 and ogc.content == legacy.content
    assert ogc.headers["content-type"].startswith("application/vnd.mapbox-vector-tile")
    assert c.get("/v1/collections/demo_ows/tiles/NoSuchTms/0/0/0").status_code == 404
    assert c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/0/5/0").status_code == 400
    # anonyme : le champ sensible n'apparaît pas dans la tuile
    login(None)
    anon = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/0/0/0")
    assert anon.status_code == 200 and b"secret" not in anon.content and b"nom" in anon.content
    tilesets = c.get("/v1/collections/demo_ows/tiles").json()
    assert tilesets["tilesets"][0]["tileMatrixSetURI"].endswith("WebMercatorQuad")


TILES_CORE = "http://www.opengis.net/spec/ogcapi-tiles-1/1.0/conf/core"


def test_tiles_conformance_and_tms_discovery(env):
    c, _login, _admin = env
    _enable(c)
    assert TILES_CORE in c.get("/v1/conformance").json()["conformsTo"]
    assert c.get("/v1/tileMatrixSets").json()["tileMatrixSets"][0]["id"] == "WebMercatorQuad"
    tms = c.get("/v1/tileMatrixSets/WebMercatorQuad").json()
    assert tms["crs"] == "http://www.opengis.net/def/crs/EPSG/0/3857"
    assert len(tms["tileMatrices"]) == 23
    assert tms["tileMatrices"][1]["matrixWidth"] == 2
    assert c.get("/v1/tileMatrixSets/Nope").status_code == 404
    ts = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad").json()
    item = next(link for link in ts["links"] if link["rel"] == "item")
    assert item["href"].endswith("/WebMercatorQuad/{tileMatrix}/{tileRow}/{tileCol}")


def test_ogc_tile_path_is_matrix_row_col(env):
    c, _login, _admin = env
    _enable(c)
    # alpha (lon 1, lat 45) au zoom 1 : colonne 1 (est), ligne 0 (nord)
    ogc = c.get("/v1/collections/demo_ows/tiles/WebMercatorQuad/1/0/1")
    legacy = c.get("/v1/collections/demo_ows/tiles/1/1/0.mvt")
    assert legacy.status_code == 200 and legacy.content
    assert ogc.status_code == 200 and ogc.content == legacy.content


def test_tiles_conformance_absent_when_ows_off(pg_engine, monkeypatch):
    monkeypatch.delenv("CORE_OWS_ENABLED", raising=False)
    c, _login, _admin = _build(pg_engine)
    assert TILES_CORE not in c.get("/v1/conformance").json()["conformsTo"]


def test_get_feature_is_bounded_by_statement_timeout(env, monkeypatch):
    # AUD-155 : `hits` = count exact ; borné comme le rendu WMS, 57014 -> 503.
    from sqlalchemy.exc import OperationalError

    from app.features.routes import get_features_repo
    from app.ows import routes as ows_routes

    c, login, admin = env
    _enable(c)
    seen = []
    real = ows_routes.apply_tile_statement_timeout
    monkeypatch.setattr(
        ows_routes,
        "apply_tile_statement_timeout",
        lambda s, ms: (seen.append(ms), real(s, ms)),
    )
    q = _kvp(request="GetFeature", typenames="demo_ows", resulttype="hits")
    assert c.get(BASE, params=q).status_code == 200
    assert seen == [5000]

    class _Canceled:
        sqlstate = "57014"

    class _SlowRepo:
        def select_features(self, *a, **k):
            raise OperationalError("SELECT count(*)", {}, _Canceled())

    c.app.dependency_overrides[get_features_repo] = lambda: _SlowRepo()
    r = c.get(BASE, params=q)
    assert r.status_code == 503 and "query timed out" in r.text
