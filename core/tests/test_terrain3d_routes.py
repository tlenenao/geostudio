# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user, set_user_role


class _FakeS3Client:
    def __init__(self):
        self.presign_params: list[dict] = []

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        self.presign_params.append(dict(Params))
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
    app.dependency_overrides[get_current_user] = lambda: alice
    fake_s3 = _FakeS3Client()
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[terrain3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: deferred.append((job_id, tenant_id))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3


def test_create_upload_refuses_a_reader_with_no_privilege(env):
    # SP-42, revue des lots de correctifs 2/3bis (point 1, Critical) :
    # create_terrain3d_upload ne consultait jusqu'ici que get_current_user —
    # aucun privilège — alors que le job qu'il amorce aboutit
    # (convert_terrain3d_task) à configs_repo.create_config(kind="terrain3d"),
    # mappé sur catalog.manage. Un rôle « Lecteur » (0 privilège) obtenait
    # donc 201 ici, exactement le trou fermé sur POST /configs par
    # eafb02cc.
    client, Session, tenant, alice, _deferred, _fake_s3 = env
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert roles["reader"].privileges == []
        reader_role_id = roles["reader"].id
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=alice.id,
            role_id=reader_role_id,
            role_slug="reader",
        )
        s.commit()
    # `get_current_user` est ici surchargé par `lambda: alice` (fixture
    # `env`, patron d'origine du fichier) — le MÊME objet Python à chaque
    # requête, jamais re-résolu depuis la base. Sans cette mise à jour en
    # mémoire, require_privilege lirait encore l'ancien role_id (Créateur)
    # de cet objet et le test ne prouverait rien.
    alice.role_id = reader_role_id

    r = client.post(
        "/terrain3d/uploads",
        json={"key": f"{tenant.id}/abc/dem.tif", "filename": "dem.tif", "title": "DEM"},
    )
    assert r.status_code == 403, r.text


def test_presign_returns_upload_url_and_tenant_scoped_key(env):
    client, _, tenant, *_ = env
    r = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "uploadUrl" in body
    assert body["key"].startswith(f"{tenant.id}/")


def test_presign_signs_the_terrain3d_bucket_and_the_caller_content_type(env, monkeypatch):
    # Le type est signé dans l'URL (X-Amz-SignedHeaders) : si on signait
    # "application/octet-stream" en dur alors que le navigateur envoie
    # File.type ("image/tiff" pour un .tif), S3 répondrait 403
    # SignatureDoesNotMatch. Et le bucket doit être celui que le worker lit
    # (S3_TERRAIN3D_BUCKET), pas celui de l'ingestion générique.
    client, _, _tenant, _alice, _deferred, fake_s3 = env
    r = client.post(
        "/terrain3d/uploads/presign",
        json={"filename": "dem.tif", "contentType": "image/tiff"},
    )
    assert r.status_code == 200, r.text
    params = fake_s3.presign_params[-1]
    assert params["ContentType"] == "image/tiff"
    assert params["Bucket"] == "geostudio-terrain3d"


def test_presign_falls_back_to_octet_stream_when_no_content_type_is_given(env):
    client, _, _tenant, _alice, _deferred, fake_s3 = env
    r = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"})
    assert r.status_code == 200, r.text
    assert fake_s3.presign_params[-1]["ContentType"] == "application/octet-stream"


def test_create_upload_job_defers_conversion_task(env):
    client, _, tenant, _, deferred, _fake_s3 = env
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
