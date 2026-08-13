# SPDX-License-Identifier: Apache-2.0
import io
import json
import os
import zipfile

import pytest
from botocore.exceptions import ClientError

from app.configs import repository as configs_repo
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import jobs as tileset3d_jobs
from app.tileset3d import repository as tileset3d_repo
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
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


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_MAX_ENTRIES", "1000")
    monkeypatch.setenv("CORE_TILESET3D_MAX_TOTAL_BYTES", "10000000")
    monkeypatch.setenv("CORE_TILESET3D_MAX_ENTRY_BYTES", "10000000")
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


def _make_engine_conn_env(monkeypatch, tmp_path):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    return db_path


def test_finalize_task_creates_item_and_config_on_success(env, monkeypatch, tmp_path):
    Session, tenant, alice = env
    db_path = _make_engine_conn_env(monkeypatch, tmp_path)
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    real_session_factory = make_session_factory(engine)
    with request_scoped_session(real_session_factory) as s:
        get_or_create_default_tenant(s)
        # Capture the real-engine user, not the outer `env` fixture's
        # in-memory `alice`: get_or_create_user() mints a fresh random
        # uuid4 id (app/users/repository.py) whenever no row with a
        # matching (tenant_id, oidc_sub) exists yet in the *target*
        # session's DB, so the two engines' "alice" users have different
        # ids even with identical oidc_sub/username. Passing the wrong one
        # as created_by violates tileset3d_jobs' FK to users.id (unlike
        # tenant.id, which is deterministic — get_or_create_default_tenant
        # always uses the fixed slug "default").
        real_alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        job = tileset3d_repo.create_job(
            s, tenant_id=tenant.id, created_by=real_alice.id, source_key="k",
            upload_id="mpu-1", filename="city.zip", title="Ville",
        )
        s.commit()
        job_id = job.id

    fake_s3 = _FakeS3Client({"k": _valid_zip_bytes()})
    monkeypatch.setattr(tileset3d_jobs, "s3_client_from_env", lambda: fake_s3)

    tileset3d_jobs.finalize_tileset3d_task(job_id=job_id, tenant_id=tenant.id)

    with request_scoped_session(real_session_factory) as s:
        job = tileset3d_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id is not None
        item = items_repo.get_item(s, tenant_id=tenant.id, item_id=job.item_id)
        assert item.resourceType == "tileset3d"
        assert item.title == "Ville"
        config = configs_repo.get_config_by_item(s, job.item_id)
        assert config.config.kind == "tileset3d"
        assert config.config.tileset3d.sourceKey == "k"
        assert config.config.tileset3d.tilesetJsonPath == "tileset.json"
        assert config.config.tileset3d.entryCount == 2


def test_finalize_task_marks_error_on_invalid_zip_without_creating_an_item(env, monkeypatch, tmp_path):
    Session, tenant, alice = env
    db_path = _make_engine_conn_env(monkeypatch, tmp_path)
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    real_session_factory = make_session_factory(engine)
    with request_scoped_session(real_session_factory) as s:
        get_or_create_default_tenant(s)
        # See matching comment in the success test above: must use the
        # real-engine user's id for created_by, not the outer fixture's.
        real_alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        job = tileset3d_repo.create_job(
            s, tenant_id=tenant.id, created_by=real_alice.id, source_key="k",
            upload_id="mpu-1", filename="bad.zip", title="Cassé",
        )
        s.commit()
        job_id = job.id

    fake_s3 = _FakeS3Client({"k": b"not a zip"})
    monkeypatch.setattr(tileset3d_jobs, "s3_client_from_env", lambda: fake_s3)

    tileset3d_jobs.finalize_tileset3d_task(job_id=job_id, tenant_id=tenant.id)

    with request_scoped_session(real_session_factory) as s:
        job = tileset3d_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert "zip invalide" in job.error_message
        assert job.item_id is None


def test_finalize_task_is_a_noop_for_an_unknown_job(env, monkeypatch, tmp_path, caplog):
    Session, tenant, alice = env
    # DATABASE_URL must point at an initialized DB, same as the other two
    # tests: finalize_tileset3d_task() builds its own engine internally from
    # DATABASE_URL (see _session_factory in app.tileset3d.jobs), which is a
    # different connection than the `env` fixture's in-memory one even when
    # both default to "sqlite+pysqlite:///:memory:" — each :memory: URL is
    # its own empty, uninitialized database unless routed through the same
    # engine/connection. Matches the established db_session fixture pattern
    # in tests/test_export_jobs.py (test_render_export_task_missing_job_is_a_noop),
    # which always sets DATABASE_URL to a file-backed, init_db()-ed SQLite
    # DB even for its analogous missing-job test.
    _make_engine_conn_env(monkeypatch, tmp_path)
    engine = make_engine(os.environ["DATABASE_URL"])
    init_db(engine)

    tileset3d_jobs.finalize_tileset3d_task(job_id="does-not-exist", tenant_id=tenant.id)
    # No exception — mirrors app.ingestion.tasks.run_ingestion_task's behavior
    # for a job that vanished (should never happen, but must not crash the worker).
