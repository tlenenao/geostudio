# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.appexport import repository as appexport_repo
from app.appexport import routes as appexport_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.items.repository import create_item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


def _fake_deferrer():
    calls = []

    def deferrer(job_id, tenant_id):
        calls.append((job_id, tenant_id))

    return deferrer, calls


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        stranger = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=False,
        )
        item = create_item(
            s, tenant_id=tenant.id, owner_id=owner.id, resource_type="app", title="App"
        )
        configs_repo.create_config(
            s,
            BuilderConfig(
                kind="app",
                dataSources=[],
                pages=[],
                layout={"type": "grid", "breakpoints": {}, "items": []},
            ),
            item.id,
            tenant_id=tenant.id,
        )
        s.commit()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    fake_s3 = _FakeS3Client()

    def make_client():
        app = create_app()
        app.dependency_overrides[db.get_session] = override_session
        app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
        deferrer, calls = _fake_deferrer()
        app.dependency_overrides[appexport_routes.get_task_deferrer] = lambda: deferrer
        return TestClient(app), calls

    return make_client, owner, stranger, item.id, Session


def test_post_app_export_requires_flag_enabled(env, monkeypatch):
    make_client, _owner, _stranger, item_id, _Session = env
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "false")
    client, _calls = make_client()
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 404


def test_post_app_export_creates_job_and_returns_202(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 202
    assert "jobId" in response.json()
    assert len(calls) == 1


def test_post_app_export_denies_user_without_read_access(env):
    make_client, _owner, stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: stranger
    client.app.dependency_overrides[get_current_user_optional] = lambda: stranger
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 404


def test_post_app_export_rejects_invalid_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "bogus"})
    assert response.status_code == 422


def test_get_app_export_job_reports_status(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"}).json()
    response = client.get(f"/v1/app-exports/jobs/{created['jobId']}")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["resultUrl"] is None


def test_post_app_export_allowed_in_read_only_demo_mode(env, monkeypatch):
    # Garde démo (core/app/main.py::read_only_guard) : déclencher un export
    # d'app est une action de lecture (aucune écriture de donnée métier),
    # doit rester utilisable en CORE_READ_ONLY_MODE=true — même raisonnement
    # que POST /export, déjà exempté via _EXPORT_PATH_RE (SP-17a). Régression
    # trouvée en revue de tâche SP-18a : /app-exports ne matchait pas le
    # regex du garde et recevait un 403 avant même d'atteindre ce routeur.
    make_client, owner, _stranger, item_id, _Session = env
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"})
    assert response.status_code == 202


def test_get_app_export_job_done_status_includes_result_url(env):
    make_client, owner, _stranger, item_id, Session = env
    client, _calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    created = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "static"}).json()
    job_id = created["jobId"]
    with Session() as s:
        appexport_repo.mark_running(s, job_id=job_id)
        appexport_repo.mark_done(s, job_id=job_id, result_key=f"appexports/{job_id}.zip")
        s.commit()
    response = client.get(f"/v1/app-exports/jobs/{job_id}")
    body = response.json()
    assert body["status"] == "done"
    assert body["resultUrl"] == f"https://minio.test/geostudio-appexports/appexports/{job_id}.zip"


def test_post_app_export_accepts_connected_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "connected"})
    assert response.status_code == 202
    assert len(calls) == 1


def test_post_app_export_accepts_standalone_mode(env):
    make_client, owner, _stranger, item_id, _Session = env
    client, calls = make_client()
    client.app.dependency_overrides[get_current_user] = lambda: owner
    client.app.dependency_overrides[get_current_user_optional] = lambda: owner
    response = client.post("/v1/app-exports", json={"itemId": item_id, "mode": "standalone"})
    assert response.status_code == 202
    assert len(calls) == 1
