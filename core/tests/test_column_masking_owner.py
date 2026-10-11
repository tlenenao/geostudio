# SPDX-License-Identifier: Apache-2.0
"""REV-276 / j07-016 (décision Tanguy 2026-10-11) : le propriétaire d'une
collection et le détenteur d'`admin.collections.manage` lisent en clair les
champs sensibles ; un tiers sans `data.view_sensitive` reste masqué, sur les
lectures RLS Postgres (liste, fiche, export)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


def _user(s, tenant, sub, privileges=None, role_name=None):
    u = get_or_create_user(
        s,
        tenant_id=tenant.id,
        oidc_sub=sub,
        username=sub,
        email=None,
        first_name="",
        last_name="",
        bootstrap_admin=(sub == "admin"),
    )
    if privileges is not None:
        u.role_id = create_role(
            s, tenant_id=tenant.id, name=role_name or sub, privileges=privileges
        ).id
    return u


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
        users = {
            "admin": _user(s, tenant, "admin"),
            "third": _user(s, tenant, "third", [Privilege.DATA_VIEW.value]),
            "owner": _user(s, tenant, "owner", [Privilege.DATA_VIEW.value]),
            "manager": _user(
                s,
                tenant,
                "manager",
                [Privilege.DATA_VIEW.value, Privilege.ADMIN_COLLECTIONS_MANAGE.value],
            ),
        }
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)

    def as_(name):
        app.dependency_overrides[get_current_user] = lambda: users[name]
        app.dependency_overrides[get_current_user_optional] = lambda: users[name]

    as_("admin")
    assert client.post("/v1/collections", json={"tableName": "demo_employees"}).status_code == 201
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
    with next(override_session()) as s:
        s.get(Collection, "demo_employees").owner_id = users["owner"].id
        s.commit()
    yield client, as_, r.json()["id"]
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_employees"))
        conn.execute(
            text(
                "TRUNCATE roles, collection_shares, collections, audit_log, users, tenants CASCADE"
            )
        )


def _reads(client, fid):
    listed = client.get("/v1/collections/demo_employees/items").json()["features"][0]
    single = client.get(f"/v1/collections/demo_employees/items/{fid}").json()
    csv = client.get("/v1/collections/demo_employees/export/items?format=csv").content.decode()
    return listed["properties"], single["properties"], csv


def test_third_party_stays_masked(pg_app):
    client, as_, fid = pg_app
    as_("third")
    listed, single, csv = _reads(client, fid)
    assert "salary" not in listed and "salary" not in single
    assert "salary" not in csv.lower() and "dupont" in csv.lower()


@pytest.mark.parametrize("who", ["owner", "manager"])
def test_owner_and_collection_manager_read_sensitive_in_clear(pg_app, who):
    client, as_, fid = pg_app
    as_(who)
    listed, single, csv = _reads(client, fid)
    assert listed["salary"] == 45000 and single["salary"] == 45000
    assert "salary" in csv.lower() and "45000" in csv


def test_put_without_sensitive_column_keeps_it(pg_app):
    """Un PUT dont le corps omet la colonne sensible ne la met pas à NULL."""
    client, as_, fid = pg_app
    as_("owner")
    body = {
        "type": "Feature",
        "properties": {"nom": "Durand"},
        "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
    }
    assert client.put(f"/v1/collections/demo_employees/items/{fid}", json=body).status_code == 204
    single = client.get(f"/v1/collections/demo_employees/items/{fid}").json()
    assert single["properties"]["salary"] == 45000
