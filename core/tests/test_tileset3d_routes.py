# SPDX-License-Identifier: Apache-2.0
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import routes as tileset3d_routes
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self._next_upload_id = 0

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def create_multipart_upload(self, Bucket, Key):  # noqa: N803
        self._next_upload_id += 1
        return {"UploadId": f"mpu-{self._next_upload_id}"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}?part={Params.get('PartNumber')}"

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):  # noqa: N803
        self.objects[Key] = b"".join(b"part" for _ in MultipartUpload["Parts"])

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")
        data = self.objects[Key]
        if Range is not None:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start):int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(data)}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
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

    fake_s3 = _FakeS3Client()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[tileset3d_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3


def test_create_upload_returns_job_id(env):
    client, *_ = env
    r = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"})
    assert r.status_code == 201, r.text
    assert "jobId" in r.json()


def test_presign_part_returns_upload_url(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/parts/1/presign")
    assert r.status_code == 200, r.text
    assert "uploadUrl" in r.json()


def test_presign_part_404_for_unknown_job(env):
    client, *_ = env
    r = client.post("/tileset3d/uploads/does-not-exist/parts/1/presign")
    assert r.status_code == 404


def test_presign_part_rejects_part_number_below_one(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/parts/0/presign")
    assert r.status_code == 422


def test_complete_upload_marks_finalizing_and_defers_task(env):
    client, Session, tenant, alice, deferred, _fake_s3 = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(
        f"/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": "\"abc\""}]},
    )
    assert r.status_code == 204, r.text
    assert deferred == [(job_id, tenant.id)]
    status = client.get(f"/tileset3d/uploads/{job_id}").json()
    assert status["status"] == "finalizing"


def test_complete_upload_rejects_empty_parts_list(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/complete", json={"parts": []})
    assert r.status_code == 422


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    r = client.get("/tileset3d/uploads/does-not-exist")
    assert r.status_code == 404


import io
import json
import zipfile

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


def _seed_hosted_tileset_item(session, *, tenant_id, owner_id, fake_s3, key="tenant/x/city.zip"):
    fake_s3.objects[key] = _valid_zip_bytes()
    from app.items import repository as items_repo
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="tileset3d", title="Ville",
    )
    config = BuilderConfig(
        kind="tileset3d",
        tileset3d=Tileset3DPayload(sourceKey=key, tilesetJsonPath="tileset.json", totalBytes=100, entryCount=2),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_read_tileset3d_entry_returns_tileset_json(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert json.loads(r.content)["asset"]["version"] == "1.0"


def test_read_tileset3d_entry_returns_tile_binary(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tiles/0.b3dm")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.content == b"\x00" * 16


def test_read_tileset3d_entry_404_for_missing_entry(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/does-not-exist.b3dm")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/tileset3d/does-not-exist/tileset.json")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        bob = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=bob.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 404
