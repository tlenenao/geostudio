# SPDX-License-Identifier: Apache-2.0
"""Bout en bout DCAT-AP sur PostGIS réel : vrai introspecteur, vraie DDL RLS,
vraie emprise ST_EstimatedExtent (app.stac.extent, réutilisée telle quelle).
Couvre §10 : dump complet, dataset dé-référençable, portée anonyme
publié/public sans fuite, conformité SHACL sur un payload réellement produit
par les routes (pas seulement les serializers en isolation, Tasks 1-3)."""
import json

import pytest
import rdflib
from fastapi.testclient import TestClient
from pyshacl import validate
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
        conn.execute(text("DROP TABLE IF EXISTS dcat_roads"))
        conn.execute(text("CREATE TABLE dcat_roads (id serial PRIMARY KEY, "
                          "n text, geom geometry(Point, 4326))"))
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="",
                                   bootstrap_admin=True)
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
        conn.execute(text("DROP TABLE IF EXISTS dcat_roads"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def _seed(app, client, public):
    client.post("/collections", json={"tableName": "dcat_roads", "isPublic": public,
                                      "description": "Réseau routier"})
    for lon, lat in [(1.0, 44.0), (2.0, 45.0), (3.0, 46.0)]:
        client.post("/collections/dcat_roads/items", json={
            "type": "Feature", "properties": {"n": "x"},
            "geometry": {"type": "Point", "coordinates": [lon, lat]}})


def test_full_dcat_dump_is_shacl_valid_with_real_bbox(pg_app, dcat_shacl_shapes):
    app, client = pg_app
    _seed(app, client, public=True)

    cat = client.get("/dcat/catalog")
    assert cat.headers["content-type"] == "application/ld+json"
    body = cat.json()
    ds = body["dcat:dataset"][0]
    poly = json.loads(ds["dct:spatial"]["locn:geometry"]["@value"])
    xs = [p[0] for p in poly["coordinates"][0]]
    ys = [p[1] for p in poly["coordinates"][0]]
    assert min(xs) == pytest.approx(1.0, abs=0.5) and max(xs) == pytest.approx(3.0, abs=0.5)
    assert min(ys) == pytest.approx(44.0, abs=0.5) and max(ys) == pytest.approx(46.0, abs=0.5)

    g = rdflib.Graph()
    g.parse(data=json.dumps(body), format="json-ld")
    conforms, _, text_ = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text_


def test_dataset_detail_is_shacl_valid_standalone(pg_app, dcat_shacl_shapes):
    app, client = pg_app
    _seed(app, client, public=True)
    body = client.get("/dcat/datasets/dcat_roads").json()
    g = rdflib.Graph()
    g.parse(data=json.dumps(body), format="json-ld")
    conforms, _, text_ = validate(g, shacl_graph=dcat_shacl_shapes)
    assert conforms, text_


def test_anonymous_sees_public_only_no_leak(pg_app):
    app, client = pg_app
    _seed(app, client, public=False)  # non publique
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/dcat/catalog").json()["dcat:dataset"] == []
    # Collection non publique → 404 non-fuyant (indistinguable d'inexistante).
    assert client.get("/dcat/datasets/dcat_roads").status_code == 404
    assert client.get("/dcat/datasets/does-not-exist").status_code == 404
