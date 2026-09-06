# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 5 : application du quota d'items/collections aux points de
création réels (POST /configs, POST /collections/empty). Vérifie aussi que
désactiver CORE_QUOTAS_ENABLED fait disparaître la garde (pas de régression
sur le comportement par défaut, capacité éteinte) — spec §3.1.2, Step 2."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user
from app.db import Base, init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="creator-sub",
            username="creator",
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
    app.dependency_overrides[get_current_user] = lambda: creator
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, creator


def _map_body(title: str) -> dict:
    return {
        "title": title,
        "config": {
            "kind": "map",
            "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
        },
    }


def test_create_config_refuses_past_item_quota(env, monkeypatch):
    app, client, _creator = env
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "1")

    resp1 = client.post("/v1/configs", json=_map_body("premier"))
    assert resp1.status_code == 201, resp1.text

    resp2 = client.post("/v1/configs", json=_map_body("second"))
    assert resp2.status_code == 409, resp2.text


def test_create_config_quota_guard_disappears_when_capacity_disabled(env, monkeypatch):
    app, client, _creator = env
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", "1")

    resp1 = client.post("/v1/configs", json=_map_body("premier"))
    assert resp1.status_code == 201, resp1.text
    # La capacité est éteinte : la limite (pourtant configurée) ne s'applique
    # pas, comportement par défaut inchangé.
    resp2 = client.post("/v1/configs", json=_map_body("second"))
    assert resp2.status_code == 201, resp2.text


def test_create_config_quota_guard_noop_when_no_limit_configured(env, monkeypatch):
    app, client, _creator = env
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.delenv("CORE_QUOTA_MAX_ITEMS_PER_TENANT", raising=False)

    resp1 = client.post("/v1/configs", json=_map_body("premier"))
    assert resp1.status_code == 201, resp1.text
    resp2 = client.post("/v1/configs", json=_map_body("second"))
    assert resp2.status_code == 201, resp2.text


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="creator-sub",
            username="creator",
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
    app.dependency_overrides[get_current_user] = lambda: creator
    client = TestClient(app)
    yield client
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


@pytest.mark.postgis
def test_create_empty_collection_refuses_past_collection_quota(pg_app, monkeypatch):
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")

    body = {
        "title": "collection 1",
        "columns": [{"name": "commune", "sqlType": "text"}],
        "geometryType": None,
        "srid": None,
    }
    resp1 = pg_app.post("/v1/collections/empty", json=body)
    assert resp1.status_code == 201, resp1.text

    body2 = {**body, "title": "collection 2"}
    resp2 = pg_app.post("/v1/collections/empty", json=body2)
    assert resp2.status_code == 409, resp2.text


@pytest.mark.postgis
def test_create_empty_collection_quota_guard_disappears_when_capacity_disabled(pg_app, monkeypatch):
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")

    body = {
        "title": "collection 1",
        "columns": [{"name": "commune", "sqlType": "text"}],
        "geometryType": None,
        "srid": None,
    }
    resp1 = pg_app.post("/v1/collections/empty", json=body)
    assert resp1.status_code == 201, resp1.text
    body2 = {**body, "title": "collection 2"}
    resp2 = pg_app.post("/v1/collections/empty", json=body2)
    assert resp2.status_code == 201, resp2.text
