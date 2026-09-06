# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client(*, username: str, oidc_sub: str):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub=oidc_sub,
            username=username,
            email=f"{username}@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), Session, tenant, user


@pytest.fixture()
def client():
    return _make_client(username="alice", oidc_sub="sub-1")[0]


@pytest.fixture()
def client_env():
    return _make_client(username="alice", oidc_sub="sub-1")


def test_terrain3d_config_round_trips(client_env):
    # kind="terrain3d" n'est pas créable via POST /configs (Step 7 de cette
    # tâche + test_terrain3d_config_validation.py) — son unique producteur
    # légitime est convert_terrain3d_task, qui appelle
    # configs_repo.create_config en direct : c'est donc ce chemin qu'on
    # emprunte ici, la lecture restant vérifiée via l'API REST.
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, Terrain3DPayload
    from app.items import repository as items_repo

    client, Session, tenant, user = client_env
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="terrain3d",
            title="Relief du massif",
        )
        configs_repo.create_config(
            s,
            BuilderConfig(
                kind="terrain3d",
                terrain3d=Terrain3DPayload(
                    sourceKey="tenant-1/abc/dem-cog.tif", originalFilename="dem.tif"
                ),
            ),
            item_id=item.id,
            tenant_id=tenant.id,
        )
        s.commit()
        item_id = item.id

    by_item = client.get(f"/v1/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]
    assert body["kind"] == "terrain3d"
    assert body["terrain3d"] == {
        "sourceKey": "tenant-1/abc/dem-cog.tif",
        "originalFilename": "dem.tif",
    }


def test_terrain3d_config_requires_terrain3d_payload(client):
    created = client.post(
        "/v1/configs",
        json={"title": "Cassé", "config": {"kind": "terrain3d"}},
    )
    assert created.status_code == 422
