# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from pytest_httpserver import HTTPServer

from app import db
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Terrain3DPayload
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user


@pytest.fixture()
def env(monkeypatch, httpserver: HTTPServer):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=alice.id, resource_type="terrain3d", title="Relief",
        )
        config = BuilderConfig(
            kind="terrain3d",
            terrain3d=Terrain3DPayload(sourceKey=f"{tenant.id}/x/dem-cog.tif", originalFilename="dem.tif"),
        )
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        s.commit()
        item_id = item.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[terrain3d_routes.get_titiler_url] = lambda: httpserver.url_for("")
    client = TestClient(app)
    return client, item_id, tenant, httpserver


def test_read_tile_proxies_titiler_with_terrarium_algorithm_and_source_key(env):
    client, item_id, tenant, httpserver = env
    httpserver.expect_request(
        "/cog/tiles/5/10/12.png",
        query_string=f"url=s3%3A%2F%2Fgeostudio-terrain3d%2F{tenant.id}%2Fx%2Fdem-cog.tif&algorithm=terrarium",
    ).respond_with_data(b"\x89PNG-fake-tile-bytes", content_type="image/png")

    r = client.get(f"/terrain3d/{item_id}/tiles/5/10/12.png")

    assert r.status_code == 200
    assert r.content == b"\x89PNG-fake-tile-bytes"
    assert r.headers["content-type"] == "image/png"


def test_read_tile_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/terrain3d/does-not-exist/tiles/0/0/0.png")
    assert r.status_code == 404


def test_read_tile_502_when_titiler_unreachable(env):
    client, item_id, *_ = env
    # Aucun handler enregistré sur httpserver pour cette route -> 404 côté
    # TiTiler simulé, que le proxy doit traduire en 502 (pas un 500 opaque).
    r = client.get(f"/terrain3d/{item_id}/tiles/99/99/99.png")
    assert r.status_code == 502
