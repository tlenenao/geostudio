# SPDX-License-Identifier: Apache-2.0
"""Bout en bout PostGIS réel : un champ marqué sensible est absent des
réponses pour un utilisateur sans data.view_sensitive, présent pour un
utilisateur qui le porte — critère d'acceptation §5 de la spec GAP-22."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _FakeS3Client:
    def delete_object(self, *, Bucket, Key):
        pass


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_employees"))
        conn.execute(
            text(
                "CREATE TABLE demo_employees (id serial PRIMARY KEY, "
                "nom text NOT NULL, salary integer, geom geometry(Point, 4326))"
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
        # rôle sur mesure SANS data.view_sensitive, avec de quoi lire/gérer
        # des collections (sinon 403 avant même le masquage à tester)
        limited_role = create_role(
            s,
            tenant_id=tenant.id,
            name="limited",
            privileges=[Privilege.DATA_VIEW.value, Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        limited = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="l",
            username="limited",
            email=None,
            first_name="",
            last_name="",
        )
        limited.role_id = limited_role.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _FakeS3Client()
    client = TestClient(app)
    yield client, app, admin, limited
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_employees"))
        conn.execute(
            text(
                "TRUNCATE roles, collection_shares, collections, audit_log, users, tenants CASCADE"
            )
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_sensitive_field_absent_from_list_and_export_without_privilege(pg_app):
    client, app, admin, limited = pg_app
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "demo_employees"}).status_code == 201
    # isPublic=True donne à `limited` un accès lecture réel via can() (is_public
    # court-circuite roles_for_collections) — nécessaire ici car, à la
    # différence de collections/routes.py et de stac/dcat/routes.py (SP-35/
    # GAP-60), aucun des 4 appels à get_readable_collection() dans
    # app/features/routes.py ne passe can_manage_collections : porter
    # Privilege.ADMIN_COLLECTIONS_MANAGE seul (sans être propriétaire/partagé/
    # public) ne suffit PAS à lire les features d'une collection, contrairement
    # à ce que l'hypothèse initiale du brief supposait — vérifié en session
    # (404 avant ce correctif), trouvaille documentée dans le rapport de
    # clôture de cette tâche, hors périmètre de correction de ce plan
    # (masquage de colonnes), pas un défaut du mécanisme de masquage lui-même.
    assert (
        client.patch(
            "/v1/collections/demo_employees",
            json={"sensitiveFields": ["salary"], "isPublic": True},
        ).status_code
        == 200
    )
    r = client.post(
        "/v1/collections/demo_employees/items",
        json={
            "type": "Feature",
            "properties": {"nom": "Dupont", "salary": 45000},
            "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
        },
    )
    assert r.status_code == 201
    fid = r.json()["id"]

    _as(app, limited)
    listed = client.get("/v1/collections/demo_employees/items").json()
    props = listed["features"][0]["properties"]
    assert "salary" not in props
    assert props["nom"] == "Dupont"

    single = client.get(f"/v1/collections/demo_employees/items/{fid}").json()
    assert "salary" not in single["properties"]

    exported = client.get("/v1/collections/demo_employees/export/items?format=csv").content.decode()
    assert "salary" not in exported.lower()
    assert "dupont" in exported.lower()

    _as(app, admin)
    listed_admin = client.get("/v1/collections/demo_employees/items").json()
    assert listed_admin["features"][0]["properties"]["salary"] == 45000
