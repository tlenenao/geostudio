# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


@pytest.fixture()
def env(monkeypatch):
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
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: _FakeS3Client()
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[terrain3d_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred


def test_presign_returns_upload_url_and_tenant_scoped_key(env):
    client, _, tenant, *_ = env
    r = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "uploadUrl" in body
    assert body["key"].startswith(f"{tenant.id}/")


def test_create_upload_job_defers_conversion_task(env):
    client, _, tenant, _, deferred = env
    presigned = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"}).json()
    r = client.post(
        "/terrain3d/uploads",
        json={"key": presigned["key"], "filename": "dem.tif", "title": "Relief du massif"},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["jobId"]
    assert deferred == [(job_id, tenant.id)]
    status = client.get(f"/terrain3d/uploads/{job_id}").json()
    assert status["status"] == "uploaded"


def test_create_upload_job_rejects_key_outside_caller_tenant(env):
    client, *_ = env
    r = client.post(
        "/terrain3d/uploads",
        json={"key": "some-other-tenant/x/dem.tif", "filename": "dem.tif", "title": "T"},
    )
    assert r.status_code == 400


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    r = client.get("/terrain3d/uploads/does-not-exist")
    assert r.status_code == 404
