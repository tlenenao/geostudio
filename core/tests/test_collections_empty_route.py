# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
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
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
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
    client = TestClient(app)
    yield client
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_creates_a_readable_empty_collection_for_a_regular_non_admin_user(pg_app):
    resp = pg_app.post(
        "/v1/collections/empty",
        json={
            "title": "Ma requête",
            "columns": [{"name": "commune", "sqlType": "text"}],
            "geometryType": None,
            "srid": None,
        },
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["featureCount"] == 0
    assert pg_app.get(f"/v1/collections/{body['id']}").status_code == 200


def test_rate_limited_after_budget_exhausted(pg_app):
    # Budget "collections_empty" = 5/60s (limiter.py) — la 6e création en
    # boucle serrée doit être coupée, DDL réel ou pas.
    for i in range(5):
        resp = pg_app.post(
            "/v1/collections/empty",
            json={"title": f"Requête {i}", "columns": [{"name": "x", "sqlType": "text"}]},
        )
        assert resp.status_code == 201
    resp = pg_app.post(
        "/v1/collections/empty",
        json={"title": "Requête 6", "columns": [{"name": "x", "sqlType": "text"}]},
    )
    assert resp.status_code == 429


def test_rejects_an_unknown_sql_type_with_422(pg_app):
    resp = pg_app.post(
        "/v1/collections/empty",
        json={
            "title": "Injection",
            "columns": [{"name": "x", "sqlType": "text); DROP TABLE users; --"}],
        },
    )
    assert resp.status_code == 422


def test_reader_without_data_manage_cannot_create_an_empty_collection(pg_engine):
    # SP-42, correctif 1 (F-securite-autorisation-01) : cette route exécute du
    # DDL (création de table PostGIS) — réservée à data.manage (Créateur
    # l'a, Lecteur non), même privilège que POST /uploads.
    from app.roles.repository import ensure_built_in_roles
    from app.users.repository import set_user_role

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=roles["reader"].id,
            role_slug=roles["reader"].slug,
        )
        s.commit()
    # Même détail que côté ingestion : l'objet retourné par le dependency
    # override est une instance detachée figée, jamais re-fetchée par
    # requête — la muter directement reflète le rôle changé côté DB.
    user.role_id = roles["reader"].id
    user.is_admin = False

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    client = TestClient(app)
    try:
        resp = client.post(
            "/v1/collections/empty",
            json={
                "title": "Ma requête",
                "columns": [{"name": "commune", "sqlType": "text"}],
                "geometryType": None,
                "srid": None,
            },
        )
        assert resp.status_code == 403
    finally:
        with pg_engine.begin() as conn:
            conn.execute(
                text(
                    "TRUNCATE items, configs, config_revisions, collections, "
                    "audit_log, users, tenants CASCADE"
                )
            )
