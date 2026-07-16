# SPDX-License-Identifier: Apache-2.0
"""Bout en bout sur PostGIS réel : enregistrement (vrai introspecteur + vraie
DDL RLS) puis CRUD via l'API — le critère d'acceptation §9 de la spec.
Fixture : même pattern que test_seed_demo.py (Base.metadata.create_all sur
pg_engine, teardown TRUNCATE ciblé + DROP des tables jetables), app câblée
sur la session factory PostGIS SANS override du repo ni du scope RLS."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(text(
            "CREATE TABLE demo_incidents (id serial PRIMARY KEY, "
            "titre text NOT NULL, geom geometry(Point, 4326))"))
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
    yield TestClient(app)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def test_full_crud_roundtrip(pg_app):
    client = pg_app
    assert client.post("/collections", json={"tableName": "demo_incidents"}).status_code == 201
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 0
    r = client.post("/collections/demo_incidents/items", json={
        "type": "Feature", "properties": {"titre": "Nid de poule"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}})
    assert r.status_code == 201
    fid = r.json()["id"]
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 1
    desc = client.get("/collections/demo_incidents").json()
    assert desc["extent"]["spatial"]["bbox"] == [[1.85, 45.27, 1.85, 45.27]]
    body = client.get("/collections/demo_incidents/items").json()
    assert body["numberMatched"] == 1
    assert body["features"][0]["properties"]["titre"] == "Nid de poule"
    assert client.put(f"/collections/demo_incidents/items/{fid}", json={
        "type": "Feature", "properties": {"titre": "Réparé"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]}}).status_code == 204
    assert client.get(f"/collections/demo_incidents/items/{fid}").json()[
        "properties"]["titre"] == "Réparé"
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 1  # PUT inchangé
    assert client.delete(f"/collections/demo_incidents/items/{fid}").status_code == 204
    assert client.get("/collections/demo_incidents/items").json()["numberMatched"] == 0
    assert client.get("/collections/demo_incidents").json()["featureCount"] == 0
