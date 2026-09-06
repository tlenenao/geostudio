# SPDX-License-Identifier: Apache-2.0
"""SP-58 Tâche 5 : application du quota de stockage aux 4 points de
confirmation d'upload (attachments/tileset3d/terrain3d/ingestion). Chaque
site connaît déjà (ou apprend, via head_object) la taille du fichier qu'il
vient de confirmer — le quota est vérifié avec cette taille, sans recalcul
S3 complet à chaque requête de lecture (spec §3.1.1 option a)."""

from fastapi.testclient import TestClient

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.tileset3d import routes as tileset3d_routes
from app.users.repository import get_or_create_user


class _FakeS3Client:
    """Double couvrant head_object/delete_object (confirmation d'upload) ET
    list_objects_v2 (usage_for_tenant, appelé par le garde de quota) —
    toujours vide côté list_objects_v2 dans ces tests : seule la taille de
    l'objet fraîchement confirmé (additional_bytes) importe, pas le stock
    déjà présent."""

    def __init__(self):
        self.heads: dict[str, dict] = {}
        self.deleted: list[str] = []
        self.completed_multipart: list[str] = []

    def head_object(self, *, Bucket, Key):
        if Key not in self.heads:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "404", "Message": "x"}}, "HeadObject")
        return self.heads[Key]

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        return {"Contents": [], "IsTruncated": False, "NextContinuationToken": None}

    def create_multipart_upload(self, *, Bucket, Key):
        return {"UploadId": "up1"}

    def complete_multipart_upload(self, *, Bucket, Key, UploadId, MultipartUpload):
        self.completed_multipart.append(Key)

    def create_bucket(self, *, Bucket):
        pass

    def put_bucket_cors(self, *, Bucket, CORSConfiguration):
        pass


def _make_app(s3, *, with_collection=False):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        if with_collection:
            col = Collection(
                id="col1",
                tenant_id=tenant.id,
                owner_id=user.id,
                table_name="col1",
                title="Col 1",
                description="",
                pk_column="id",
                editable=True,
                attachment_fields=[{"key": "photos", "label": "Photos"}],
            )
            s.add(col)
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[tileset3d_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[terrain3d_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: s3
    # Jamais de vrai .defer() procrastinate dans ces tests (pas d'app
    # ouverte) — même patron que les tests propres à chaque module.
    app.dependency_overrides[tileset3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    app.dependency_overrides[terrain3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    return TestClient(app), tenant


# --- attachments ------------------------------------------------------


def test_confirm_attachment_rejects_when_it_would_exceed_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_app(s3, with_collection=True)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/col1/f1/abc-big.bin"
    s3.heads[key] = {"ContentLength": 1001}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": key,
            "fieldKey": "photos",
            "filename": "big.bin",
            "contentType": "application/octet-stream",
        },
    )
    assert res.status_code == 409, res.text
    # Objet orphelin nettoyé (même patron que MAX_ATTACHMENT_BYTES).
    assert key in s3.deleted


def test_confirm_attachment_allows_when_under_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_app(s3, with_collection=True)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/col1/f1/abc-small.bin"
    s3.heads[key] = {"ContentLength": 500}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": key,
            "fieldKey": "photos",
            "filename": "small.bin",
            "contentType": "application/octet-stream",
        },
    )
    assert res.status_code == 201, res.text


def test_confirm_attachment_quota_guard_disappears_when_capacity_disabled(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_app(s3, with_collection=True)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/col1/f1/abc-big.bin"
    s3.heads[key] = {"ContentLength": 1001}

    res = api.post(
        "/collections/col1/items/f1/attachments",
        json={
            "key": key,
            "fieldKey": "photos",
            "filename": "big.bin",
            "contentType": "application/octet-stream",
        },
    )
    assert res.status_code == 201, res.text


# --- tileset3d ----------------------------------------------------------


def _make_tileset3d_env(s3, monkeypatch):
    """Fixture dédiée (pas _make_app) : ce test a besoin de relire
    job.source_key (clé générée par uuid côté route, jamais connue à
    l'avance côté client) via une Session construite sur le même engine
    que l'app — retournée explicitement plutôt que reconstruite.
    CORE_TILESET3D_ENABLED doit être vrai AVANT create_app() : le routeur
    n'est monté qu'à la construction de l'app (main.py), pas par requête."""
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
    app.dependency_overrides[tileset3d_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[tileset3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    return TestClient(app), Session, tenant


def _create_tileset3d_job_and_set_head_size(api, Session, tenant, s3, *, content_length):
    from app.tileset3d import repository as tileset3d_repo

    created = api.post(
        "/tileset3d/uploads", json={"filename": "t.zip", "title": "Mon tileset"}
    ).json()
    job_id = created["jobId"]
    with Session() as s:
        job = tileset3d_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        source_key = job.source_key
    s3.heads[source_key] = {"ContentLength": content_length}
    return job_id


def test_complete_tileset3d_upload_rejects_when_it_would_exceed_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, Session, tenant = _make_tileset3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    job_id = _create_tileset3d_job_and_set_head_size(api, Session, tenant, s3, content_length=1001)

    resp = api.post(
        f"/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": "e1"}]},
    )
    assert resp.status_code == 409, resp.text


def test_complete_tileset3d_upload_allows_when_under_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, Session, tenant = _make_tileset3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    job_id = _create_tileset3d_job_and_set_head_size(api, Session, tenant, s3, content_length=500)

    resp = api.post(
        f"/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": "e1"}]},
    )
    assert resp.status_code == 204, resp.text


def test_complete_tileset3d_upload_quota_guard_disappears_when_capacity_disabled(monkeypatch):
    s3 = _FakeS3Client()
    api, Session, tenant = _make_tileset3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    job_id = _create_tileset3d_job_and_set_head_size(api, Session, tenant, s3, content_length=1001)

    resp = api.post(
        f"/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": "e1"}]},
    )
    assert resp.status_code == 204, resp.text


# --- terrain3d ------------------------------------------------------------


def _make_terrain3d_env(s3, monkeypatch):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
    app.dependency_overrides[terrain3d_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[terrain3d_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    return TestClient(app), tenant


def test_create_terrain3d_upload_rejects_when_it_would_exceed_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_terrain3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/{'x' * 8}/dem.tif"
    s3.heads[key] = {"ContentLength": 1001}

    resp = api.post(
        "/terrain3d/uploads",
        json={"key": key, "filename": "dem.tif", "title": "Mon terrain"},
    )
    assert resp.status_code == 409, resp.text


def test_create_terrain3d_upload_allows_when_under_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_terrain3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/{'x' * 8}/dem.tif"
    s3.heads[key] = {"ContentLength": 500}

    resp = api.post(
        "/terrain3d/uploads",
        json={"key": key, "filename": "dem.tif", "title": "Mon terrain"},
    )
    assert resp.status_code == 201, resp.text


def test_create_terrain3d_upload_quota_guard_disappears_when_capacity_disabled(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_terrain3d_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/{'x' * 8}/dem.tif"
    s3.heads[key] = {"ContentLength": 1001}

    resp = api.post(
        "/terrain3d/uploads",
        json={"key": key, "filename": "dem.tif", "title": "Mon terrain"},
    )
    assert resp.status_code == 201, resp.text


# --- ingestion --------------------------------------------------------


def _make_ingestion_env(s3, monkeypatch):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        ensure_built_in_roles(s, tenant_id=tenant.id)
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
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: s3
    app.dependency_overrides[ingestion_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: None
    )
    return TestClient(app), tenant


def test_create_upload_job_rejects_when_it_would_exceed_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_ingestion_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/abc-data.geojson"
    s3.heads[key] = {"ContentLength": 1001}

    resp = api.post(
        "/uploads",
        json={"key": key, "filename": "data.geojson", "collectionTitle": "Ma collection"},
    )
    assert resp.status_code == 409, resp.text


def test_create_upload_job_allows_when_under_storage_quota(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_ingestion_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/abc-small.geojson"
    s3.heads[key] = {"ContentLength": 500}

    resp = api.post(
        "/uploads",
        json={"key": key, "filename": "small.geojson", "collectionTitle": "Ma collection"},
    )
    assert resp.status_code == 201, resp.text


def test_create_upload_job_quota_guard_disappears_when_capacity_disabled(monkeypatch):
    s3 = _FakeS3Client()
    api, tenant = _make_ingestion_env(s3, monkeypatch)
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "false")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{tenant.id}/abc-data.geojson"
    s3.heads[key] = {"ContentLength": 1001}

    resp = api.post(
        "/uploads",
        json={"key": key, "filename": "data.geojson", "collectionTitle": "Ma collection"},
    )
    assert resp.status_code == 201, resp.text
