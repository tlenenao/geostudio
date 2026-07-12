import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


@pytest.fixture()
def env():
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
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred


def test_presign_returns_upload_url_and_key(env):
    client, *_ = env
    r = client.post("/uploads/presign", json={"filename": "villes.geojson", "contentType": "application/geo+json"})
    assert r.status_code == 200
    body = r.json()
    assert body["key"].endswith("-villes.geojson")
    assert body["uploadUrl"].startswith("https://minio.test/")


def test_create_upload_job_defers_task_and_returns_job_id(env):
    client, Session, tenant, alice, deferred = env
    r = client.post("/uploads", json={
        "key": "default/abc-villes.geojson", "filename": "villes.geojson",
        "collectionTitle": "Villes",
    })
    assert r.status_code == 201
    job_id = r.json()["jobId"]
    assert deferred == [(job_id, tenant.id)]

    r2 = client.get(f"/uploads/{job_id}")
    assert r2.status_code == 200
    assert r2.json() == {
        "status": "pending", "errorMessage": None, "collectionId": None, "itemId": None,
    }


def test_create_upload_job_rejects_key_with_foreign_tenant_prefix(env):
    client, *_ = env
    r = client.post("/uploads", json={
        "key": "other-tenant/abc-villes.geojson", "filename": "villes.geojson",
        "collectionTitle": "Villes",
    })
    assert r.status_code == 400


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    assert client.get("/uploads/does-not-exist").status_code == 404


def test_create_upload_job_is_audited(env):
    client, Session, tenant, alice, _ = env
    client.post("/uploads", json={
        "key": "default/abc.csv", "filename": "villes.csv", "collectionTitle": "Villes CSV",
        "latField": "y", "lonField": "x",
    })
    with Session() as s:
        from sqlalchemy import select
        from app.audit.models import AuditLog
        rows = s.scalars(select(AuditLog).where(AuditLog.action == "ingestion.job_create")).all()
        assert len(rows) == 1
        assert rows[0].payload["collectionTitle"] == "Villes CSV"
