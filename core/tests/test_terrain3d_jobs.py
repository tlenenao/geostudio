# SPDX-License-Identifier: Apache-2.0
import os

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.configs import repository as configs_repo
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import jobs as terrain3d_jobs
from app.terrain3d import repository as repo
from app.users.repository import get_or_create_user


def _write_test_geotiff_bytes() -> bytes:
    import io

    buf = io.BytesIO()
    data = np.linspace(0, 1000, 64 * 64, dtype="float32").reshape(64, 64)
    # Origine non nulle : (0, 0, 1, 1) produit une matrice affine égale à
    # l'identité inversée, que GDAL refuse d'écrire silencieusement
    # (NotGeoreferencedWarning promu en erreur par filterwarnings=["error"]
    # dans ce dépôt) — même défaut déjà rencontré et corrigé dans
    # tests/test_terrain3d_conversion.py (Task 3), même fix appliqué ici.
    transform = from_origin(2.0, 45.0, 0.001, 0.001)
    with rasterio.io.MemoryFile() as mem:
        with mem.open(
            driver="GTiff", width=64, height=64, count=1, dtype="float32",
            crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(data, 1)
        buf.write(mem.read())
    return buf.getvalue()


class _FakeBody:
    def __init__(self, data: bytes):
        import io

        self._buf = io.BytesIO(data)

    def iter_chunks(self, chunk_size: int):
        while True:
            chunk = self._buf.read(chunk_size)
            if not chunk:
                return
            yield chunk


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.deleted: list[str] = []

    def head_object(self, Bucket, Key):  # noqa: N803
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": _FakeBody(self.objects[Key])}

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        with open(Filename, "rb") as f:
            self.objects[Key] = f.read()

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
    monkeypatch.setattr(terrain3d_jobs, "_TERRAIN3D_SCRATCH_ROOT", str(tmp_path))
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
    return Session, tenant, alice


def _make_job(Session, tenant, alice, *, source_key: str, title: str = "Relief"):
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key=source_key, filename="dem.tif", title=title,
        )
        s.commit()
        return job.id


def test_convert_success_creates_item_and_config_and_purges_raw_upload(env, monkeypatch):
    Session, tenant, alice = env
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": _write_test_geotiff_bytes()})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id is not None
        assert job.converted_key is not None

        item = items_repo.get_access_facts(s, tenant_id=tenant.id, item_id=job.item_id)
        assert item is not None

        config = configs_repo.get_config_by_item(s, job.item_id)
        assert config.config.kind == "terrain3d"
        assert config.config.terrain3d.sourceKey == job.converted_key
        assert config.config.terrain3d.originalFilename == "dem.tif"

    assert f"{tenant.id}/x/dem.tif" not in fake_s3.objects  # raw upload purged
    assert job.converted_key in fake_s3.objects  # converted COG present


def test_convert_failure_marks_error_and_purges_raw_upload_never_creates_item(env, monkeypatch):
    Session, tenant, alice = env
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": b"not a geotiff at all"})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.item_id is None
        assert job.error_message

    assert f"{tenant.id}/x/dem.tif" not in fake_s3.objects  # purged even on rejection
    assert fake_s3.deleted == [f"{tenant.id}/x/dem.tif"]


def test_convert_cleans_up_scratch_files_on_success_and_failure(env, monkeypatch, tmp_path):
    Session, tenant, alice = env

    def assert_scratch_empty_after():
        assert list(tmp_path.iterdir()) == [] or all(
            not any(p.iterdir()) for p in tmp_path.iterdir() if p.is_dir()
        )

    fake_s3_ok = _FakeS3Client({f"{tenant.id}/x/dem.tif": _write_test_geotiff_bytes()})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3_ok)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif", title="OK")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)
    assert_scratch_empty_after()

    fake_s3_bad = _FakeS3Client({f"{tenant.id}/y/dem.tif": b"garbage"})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3_bad)
    job_id_2 = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/y/dem.tif", title="Bad")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id_2, tenant_id=tenant.id)
    assert_scratch_empty_after()


def test_convert_missing_job_is_a_noop(env, monkeypatch):
    Session, tenant, _alice = env
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    terrain3d_jobs.convert_terrain3d_task(job_id="does-not-exist", tenant_id=tenant.id)  # must not raise


def test_convert_marks_error_and_cleans_scratch_when_s3_client_creation_fails(env, monkeypatch, tmp_path):
    # Finding 1: s3_client_from_env()/_terrain3d_bucket() used to run before
    # the try/finally — a KeyError from a missing S3 env var would propagate
    # straight out of the task, leaving the job stuck "converting" and the
    # scratch dir never cleaned up.
    Session, tenant, alice = env
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)

    def _boom():
        raise KeyError("S3_ENDPOINT_URL")

    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", _boom)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.item_id is None

    # scratch dir created for this job must not survive the failure
    assert list(tmp_path.iterdir()) == [] or all(
        not any(p.iterdir()) for p in tmp_path.iterdir() if p.is_dir()
    )


def test_purge_raw_upload_never_raises_when_audit_write_fails(env, monkeypatch):
    # Finding 2: a DB error during the purge's write_audit() used to
    # propagate out of _purge_raw_upload, get caught by the caller's generic
    # except Exception, and downgrade an already-committed "done" job back
    # to "error" even though the item/config/COG were all genuinely fine.
    Session, tenant, alice = env
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": b"whatever"})

    def _boom_write_audit(*args, **kwargs):
        raise RuntimeError("transient db error")

    monkeypatch.setattr(terrain3d_jobs, "write_audit", _boom_write_audit)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")

    # Must not raise despite delete_object succeeding and write_audit failing.
    terrain3d_jobs._purge_raw_upload(
        fake_s3, bucket="geostudio-terrain3d", source_key=f"{tenant.id}/x/dem.tif",
        tenant_id=tenant.id, job_id=job_id, session_factory=Session,
    )

    assert f"{tenant.id}/x/dem.tif" not in fake_s3.objects  # delete still happened
    assert fake_s3.deleted == [f"{tenant.id}/x/dem.tif"]


def test_convert_rejects_upload_over_max_bytes_without_downloading(env, monkeypatch):
    Session, tenant, alice = env
    oversized = _write_test_geotiff_bytes() * 1000  # comfortably over the 1-byte cap set below
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": oversized})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(terrain3d_jobs, "_max_upload_bytes", lambda: 1)
    download_calls = []
    monkeypatch.setattr(
        terrain3d_jobs, "download_to_file",
        lambda *a, **k: download_calls.append((a, k)),
    )

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert "volumineux" in job.error_message
    assert download_calls == []  # rejected before streaming a single byte
