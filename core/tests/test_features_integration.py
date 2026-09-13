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
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3Client:
    """Stub minimal pour attachments_routes.get_s3_client (SP-40) : la
    cascade de suppression de remove_feature (app/features/routes.py) en
    dépend, best-effort — cf. test_features_routes_write.py, même patron."""

    def delete_object(self, *, Bucket, Key):
        pass


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text(
                "CREATE TABLE demo_incidents (id serial PRIMARY KEY, "
                "titre text NOT NULL, geom geometry(Point, 4326))"
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
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()
    yield TestClient(app)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def test_full_crud_roundtrip(pg_app):
    client = pg_app
    assert client.post("/v1/collections", json={"tableName": "demo_incidents"}).status_code == 201
    assert client.get("/v1/collections/demo_incidents").json()["featureCount"] == 0
    r = client.post(
        "/v1/collections/demo_incidents/items",
        json={
            "type": "Feature",
            "properties": {"titre": "Nid de poule"},
            "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
        },
    )
    assert r.status_code == 201
    fid = r.json()["id"]
    assert client.get("/v1/collections/demo_incidents").json()["featureCount"] == 1
    desc = client.get("/v1/collections/demo_incidents").json()
    assert desc["extent"]["spatial"]["bbox"] == [[1.85, 45.27, 1.85, 45.27]]
    body = client.get("/v1/collections/demo_incidents/items").json()
    assert body["numberMatched"] == 1
    assert body["features"][0]["properties"]["titre"] == "Nid de poule"
    assert (
        client.put(
            f"/v1/collections/demo_incidents/items/{fid}",
            json={
                "type": "Feature",
                "properties": {"titre": "Réparé"},
                "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
            },
        ).status_code
        == 204
    )
    assert (
        client.get(f"/v1/collections/demo_incidents/items/{fid}").json()["properties"]["titre"]
        == "Réparé"
    )
    assert client.get("/v1/collections/demo_incidents").json()["featureCount"] == 1  # PUT inchangé
    assert client.delete(f"/v1/collections/demo_incidents/items/{fid}").status_code == 204
    assert client.get("/v1/collections/demo_incidents/items").json()["numberMatched"] == 0
    assert client.get("/v1/collections/demo_incidents").json()["featureCount"] == 0


def test_list_features_masks_sensitive_column_under_real_grant_revoke(pg_engine):
    """GAP-22 (correctif dirigé par le contrôleur, cross-tâche Task 6/Task 8) :
    sync_masked_role_grants (Task 3) REVOKE la colonne sensible au niveau
    colonne, jamais table — sous le rôle gis_rls_masked, un SELECT qui NOMME
    encore cette colonne échoue l'instruction ENTIÈRE avec
    psycopg.errors.InsufficientPrivilege ("permission denied for table"),
    Postgres ne l'omet jamais silencieusement. test_features_routes_read.py
    ne pouvait pas détecter ce défaut (repo/introspecteur en spy, jamais de
    vrai GRANT/REVOKE) ; ce test-ci passe par le vrai chemin, sans aucun
    override d'introspecteur ni de rls_scope (même patron que
    test_full_crud_roundtrip ci-dessus). Falsifié en session : retirer
    l'appel à hide_sensitive_columns() dans list_features fait échouer ce
    test avec un 500 (InsufficientPrivilege), pas une propriété absente."""
    from app.collections import repository as collections_repo
    from app.collections.ddl import apply_collection_ddl, sync_masked_role_grants

    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_incidents_salary"))
        conn.execute(
            text(
                "CREATE TABLE demo_incidents_salary (id serial PRIMARY KEY, "
                "titre text NOT NULL, salary integer, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="admin-salary-gap22",
            username="admin-salary-gap22",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        # Rôle par défaut "creator" (get_or_create_user sans bootstrap_admin) :
        # ne porte pas data.view_sensitive (BUILT_IN_ROLE_PRIVILEGES, app/roles/
        # privileges.py) -> get_masked_for_user renvoie True pour cet utilisateur.
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="regular-salary-gap22",
            username="regular-salary-gap22",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        apply_collection_ddl(s, "demo_incidents_salary")
        col = collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=admin.id,
            table_name="demo_incidents_salary",
            title="Incidents salaire",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
        )
        s.execute(
            text(
                "INSERT INTO demo_incidents_salary (tenant_id, titre, salary, geom) VALUES "
                "(:tid, 'Nid de poule', 5000, ST_SetSRID(ST_MakePoint(2.3, 48.8), 4326))"
            ),
            {"tid": tenant.id},
        )
        s.commit()
        col.sensitive_fields = ["salary"]
        s.commit()
        sync_masked_role_grants(s, "demo_incidents_salary", ["salary"])
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    try:
        app.dependency_overrides[get_current_user] = lambda: regular
        app.dependency_overrides[get_current_user_optional] = lambda: regular
        r = client.get("/v1/collections/demo_incidents_salary/items")
        assert r.status_code == 200
        props = r.json()["features"][0]["properties"]
        assert props["titre"] == "Nid de poule"
        assert "salary" not in props

        app.dependency_overrides[get_current_user] = lambda: admin
        app.dependency_overrides[get_current_user_optional] = lambda: admin
        r2 = client.get("/v1/collections/demo_incidents_salary/items")
        assert r2.status_code == 200
        assert r2.json()["features"][0]["properties"]["salary"] == 5000
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP TABLE IF EXISTS demo_incidents_salary"))
            conn.execute(
                text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
            )
