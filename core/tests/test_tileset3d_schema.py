# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client(*, username: str, oidc_sub: str, bootstrap_admin: bool = False) -> TestClient:
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub=oidc_sub,
            username=username, email=f"{username}@example.com",
            first_name="Alice", last_name="Doe", bootstrap_admin=bootstrap_admin,
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app)


@pytest.fixture()
def client():
    return _make_client(username="alice", oidc_sub="sub-1")


def test_tileset3d_config_round_trips(client):
    created = client.post(
        "/configs",
        json={
            "title": "Bâtiments du centre-ville",
            "config": {
                "kind": "tileset3d",
                "tileset3d": {
                    "sourceKey": "tenant-1/abc/city.zip",
                    "tilesetJsonPath": "tileset.json",
                    "totalBytes": 123456789,
                    "entryCount": 4200,
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]
    assert body["kind"] == "tileset3d"
    assert body["tileset3d"] == {
        "sourceKey": "tenant-1/abc/city.zip",
        "tilesetJsonPath": "tileset.json",
        "totalBytes": 123456789,
        "entryCount": 4200,
    }


def test_tileset3d_config_requires_tileset3d_payload(client):
    created = client.post(
        "/configs",
        json={"title": "Cassé", "config": {"kind": "tileset3d"}},
    )
    assert created.status_code == 422
