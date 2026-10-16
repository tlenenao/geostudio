# SPDX-License-Identifier: Apache-2.0
"""Fonds de carte du tenant (REV-367 i / ARC-09a)."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.security.csp_hosts import extract_basemap_hosts
from app.security.service import compute_csp_allowlist
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

STYLE = "https://tiles.exemple.fr/style.json"
XYZ = "xyz:https://tuiles.exemple.fr/{z}/{x}/{y}.png"


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        reader.role_id = roles["reader"].id
        s.commit()
        s.refresh(admin)
        s.refresh(reader)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    return app, TestClient(app), Session, admin, reader


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user


def test_admin_adds_a_basemap_everyone_lists_it_then_admin_removes_it(env):
    app, client, _Session, admin, reader = env
    _as(app, admin)
    created = client.post("/v1/basemaps", json={"label": "Plan IGN", "style": STYLE})
    assert created.status_code == 201, created.text
    assert client.post("/v1/basemaps", json={"label": "Ortho", "style": XYZ}).status_code == 201
    _as(app, reader)  # visible par tous les utilisateurs du tenant
    listed = client.get("/v1/basemaps").json()
    assert [b["label"] for b in listed] == ["Ortho", "Plan IGN"]
    _as(app, admin)
    assert client.delete(f"/v1/basemaps/{created.json()['id']}").status_code == 204
    assert [b["label"] for b in client.get("/v1/basemaps").json()] == ["Ortho"]
    assert client.delete("/v1/basemaps/inconnu").status_code == 404


def test_only_an_admin_can_write_basemaps(env):
    app, client, _Session, _admin, reader = env
    _as(app, reader)
    assert client.post("/v1/basemaps", json={"label": "x", "style": STYLE}).status_code == 403


@pytest.mark.parametrize(
    "style",
    ["ftp://x/style.json", "javascript:alert(1)", "pas une url", "xyz:https://h/tuiles.png"],
)
def test_invalid_styles_are_refused(env, style):
    app, client, _Session, admin, _reader = env
    _as(app, admin)
    assert client.post("/v1/basemaps", json={"label": "x", "style": style}).status_code == 422


def test_basemap_origins_join_the_csp_allowlist(env):
    app, client, Session, admin, _reader = env
    _as(app, admin)
    client.post("/v1/basemaps", json={"label": "a", "style": STYLE})
    client.post("/v1/basemaps", json={"label": "b", "style": XYZ})
    with Session() as s:
        allow = compute_csp_allowlist(s)
    assert {"https://tiles.exemple.fr", "https://tuiles.exemple.fr"} <= allow.img_hosts
    assert {"https://tiles.exemple.fr", "https://tuiles.exemple.fr"} <= allow.connect_hosts
    assert extract_basemap_hosts([STYLE, "relatif/style.json"]) == {"https://tiles.exemple.fr"}
