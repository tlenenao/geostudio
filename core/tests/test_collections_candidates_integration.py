# SPDX-License-Identifier: Apache-2.0
"""Bout en bout sur PostGIS réel : /collections/candidates avec la vraie
introspection Postgres (information_schema.tables), pas de fake — même
patron que test_features_integration.py (Base.metadata.create_all sur
pg_engine, teardown TRUNCATE + DROP des tables jetables)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS cand_points"))
        conn.execute(text("DROP TABLE IF EXISTS cand_no_pk"))
        conn.execute(
            text(
                "CREATE TABLE cand_points (id serial PRIMARY KEY, "
                "titre text NOT NULL, geom geometry(Point, 4326))"
            )
        )
        conn.execute(text("CREATE TABLE cand_no_pk (a int, b int)"))
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant_a = get_or_create_default_tenant(s)
        admin_a = get_or_create_user(
            s,
            tenant_id=tenant_a.id,
            oidc_sub="a",
            username="admin-a",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        tenant_b = Tenant(id="tenant-b-candidates", slug="tenant-b-candidates", name="Tenant B")
        s.add(tenant_b)
        s.flush()
        admin_b = get_or_create_user(
            s,
            tenant_id=tenant_b.id,
            oidc_sub="b",
            username="admin-b",
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
    client = TestClient(app)
    yield client, app, admin_a, admin_b
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS cand_points"))
        conn.execute(text("DROP TABLE IF EXISTS cand_no_pk"))
        conn.execute(
            text("TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE")
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_candidates_real_introspection_and_tenant_isolation(pg_app):
    client, app, admin_a, admin_b = pg_app
    _as(app, admin_a)
    body = client.get("/v1/collections/candidates").json()["candidates"]
    by_name = {c["tableName"]: c for c in body}
    assert by_name["cand_points"]["registrable"] is True
    assert by_name["cand_points"]["geometryType"] == "Point"
    assert by_name["cand_no_pk"]["registrable"] is False
    assert by_name["cand_no_pk"]["reason"] == "table has no primary key"

    assert client.post("/v1/collections", json={"tableName": "cand_points"}).status_code == 201
    body_a = client.get("/v1/collections/candidates").json()["candidates"]
    assert "cand_points" not in {c["tableName"] for c in body_a}

    _as(app, admin_b)
    body_b = client.get("/v1/collections/candidates").json()["candidates"]
    assert "cand_points" in {c["tableName"] for c in body_b}
