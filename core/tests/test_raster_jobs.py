# SPDX-License-Identifier: Apache-2.0
import io
from datetime import UTC, datetime, timedelta

import pytest

from app.db import init_db, make_engine, make_session_factory
from app.raster import jobs
from app.raster import repository as repo
from app.raster.models import RasterAsset, RasterJob
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.raster_fixtures import write_tif

BUCKET = "geostudio-raster"


class _Body:
    def __init__(self, data):
        self._b = io.BytesIO(data)

    def iter_chunks(self, n):
        while chunk := self._b.read(n):
            yield chunk


class _FakeS3:
    def __init__(self, objects):
        self.objects = objects
        self.deleted = []

    def head_object(self, Bucket, Key):  # noqa: N803
        return {"ContentLength": len(self.objects[(Bucket, Key)])}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": _Body(self.objects[(Bucket, Key)])}

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        with open(Filename, "rb") as f:
            self.objects[(Bucket, Key)] = f.read()

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append((Bucket, Key))
        self.objects.pop((Bucket, Key), None)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_RASTER_BUCKET", BUCKET)
    monkeypatch.setattr(jobs, "_RASTER_SCRATCH_ROOT", str(tmp_path / "scratch"))
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice", email=None,
            first_name="", last_name="",
        )  # fmt: skip
        s.commit()
    return Session, tenant, alice


def _job(Session, tenant, alice, key):
    with Session() as s:
        j = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key=key,
            filename="o.tif", title="Ortho", limit_collection_id=None,
        )  # fmt: skip
        s.commit()
        return j.id


def test_ingest_creates_item_asset_and_purges_raw(env, tmp_path):
    Session, tenant, alice = env
    raw = tmp_path / "raw.tif"
    write_tif(str(raw), size=600)  # non tuilé > 512 px : doit être converti
    key = f"{tenant.id}/x/o.tif"
    s3 = _FakeS3({(BUCKET, key): raw.read_bytes()})
    job_id = _job(Session, tenant, alice, key)

    jobs.run_ingest(Session, s3, job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done", job.error_message
        asset = s.get(RasterAsset, job.item_id)
        assert asset.srid == 4326 and asset.width == 600 and asset.bands[0]["index"] == 1
        assert asset.bounds == pytest.approx([2.0, 43.0, 8.0, 49.0])
    assert (BUCKET, f"{tenant.id}/{job_id}/cog.tif") in s3.objects
    assert (BUCKET, key) in s3.deleted


def test_ingest_garbage_ends_in_error_never_zombie(env):
    Session, tenant, alice = env
    key = f"{tenant.id}/x/junk.tif"
    s3 = _FakeS3({(BUCKET, key): b"not a raster"})
    job_id = _job(Session, tenant, alice, key)
    jobs.run_ingest(Session, s3, job_id=job_id, tenant_id=tenant.id)
    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error" and job.item_id is None and job.error_message
    assert (BUCKET, key) in s3.deleted


def test_ingest_oversize_rejected(env, monkeypatch):
    Session, tenant, alice = env
    monkeypatch.setenv("CORE_RASTER_MAX_UPLOAD_BYTES", "5")
    key = f"{tenant.id}/x/big.tif"
    s3 = _FakeS3({(BUCKET, key): b"0123456789"})
    job_id = _job(Session, tenant, alice, key)
    jobs.run_ingest(Session, s3, job_id=job_id, tenant_id=tenant.id)
    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error" and "trop volumineux" in job.error_message


def test_sweep_reclaims_stuck_jobs_only(env):
    Session, tenant, alice = env
    stuck = _job(Session, tenant, alice, "k1")
    fresh = _job(Session, tenant, alice, "k2")
    with Session() as s:
        s.get(RasterJob, stuck).updated_at = datetime.now(UTC) - timedelta(hours=2)
        s.commit()
        assert [j.id for j in repo.reclaim_stuck_jobs(s)] == [stuck]
        s.commit()
        assert s.get(RasterJob, stuck).status == "error"
        assert s.get(RasterJob, fresh).status == "uploaded"


def test_sweep_purges_raw_upload_of_reclaimed_job(env, monkeypatch):
    Session, tenant, alice = env
    key = f"{tenant.id}/x/stuck.tif"
    s3 = _FakeS3({(BUCKET, key): b"raw"})
    stuck = _job(Session, tenant, alice, key)
    with Session() as s:
        s.get(RasterJob, stuck).updated_at = datetime.now(UTC) - timedelta(hours=2)
        s.commit()
    monkeypatch.setattr(jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(jobs, "s3_client_from_env", lambda: s3)
    jobs.sweep_raster_jobs_task(0)
    assert (BUCKET, key) in s3.deleted and (BUCKET, key) not in s3.objects


def test_converted_cog_is_rechecked_against_storage_quota(env, tmp_path, monkeypatch):
    Session, tenant, alice = env
    raw = tmp_path / "raw.tif"
    write_tif(str(raw), size=600)
    key = f"{tenant.id}/x/o.tif"
    s3 = _FakeS3({(BUCKET, key): raw.read_bytes()})
    s3.list_objects_v2 = lambda **kw: {"Contents": [{"Size": 10**9}], "IsTruncated": False}
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    job_id = _job(Session, tenant, alice, key)
    jobs.run_ingest(Session, s3, job_id=job_id, tenant_id=tenant.id)
    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error" and "quota" in job.error_message
        assert s.query(RasterAsset).count() == 0
    assert (BUCKET, f"{tenant.id}/{job_id}/cog.tif") not in s3.objects
