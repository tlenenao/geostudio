# SPDX-License-Identifier: Apache-2.0
"""Hygiène des exports de collection (REV-283e) : purge TTL, reprise des
`pending` (defer perdu) et des `running` bloqués, quotas."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import update

from app.dataexport import jobs as dx_jobs
from app.dataexport import repository as dx_repo
from app.dataexport.models import CollectionExportJob
from tests.test_dataexport_jobs import _FakeS3, _job, _new_job
from tests.test_dataexport_jobs import env as _env  # noqa: F401

env = _env


def _set(factory, job_id, **vals):
    with factory() as s:
        s.execute(
            update(CollectionExportJob).where(CollectionExportJob.id == job_id).values(**vals)
        )
        s.commit()


def _ago(**kw):
    return datetime.now(UTC) - timedelta(**kw)


class _DelS3(_FakeS3):
    def __init__(self):
        super().__init__()
        self.deleted = []

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)


def test_purge_ttl_deletes_s3_object_and_row_but_never_a_running_job(env, monkeypatch):
    factory, ids, _s3, _ = env
    s3 = _DelS3()
    monkeypatch.setattr(dx_jobs, "s3_client_from_env", lambda: s3)
    done = _new_job(factory, ids)
    running = _new_job(factory, ids)
    fresh = _new_job(factory, ids)
    _set(
        factory,
        done,
        status="done",
        result_key="t/data-exports/a.geojson",
        expires_at=_ago(hours=1),
    )
    _set(factory, running, status="running", expires_at=_ago(hours=1))
    _set(factory, fresh, status="done", result_key="t/data-exports/b.geojson")
    dx_jobs.purge_expired_exports_task(0)
    assert s3.deleted == ["t/data-exports/a.geojson"]
    assert _job(factory, ids, done) is None
    assert _job(factory, ids, running) is not None
    assert _job(factory, ids, fresh) is not None


def test_delete_job_never_deletes_a_running_job(env):
    factory, ids, _s3, _ = env
    running = _new_job(factory, ids)
    _set(factory, running, status="running")
    with factory() as s:
        dx_repo.delete_job(s, running)
        s.commit()
    assert _job(factory, ids, running) is not None


def test_purge_ttl_keeps_row_when_s3_delete_fails(env, monkeypatch):
    factory, ids, _s3, _ = env

    class _Boom(_FakeS3):
        def delete_object(self, **kw):
            raise RuntimeError("s3 down")

    monkeypatch.setattr(dx_jobs, "s3_client_from_env", lambda: _Boom())
    jid = _new_job(factory, ids)
    _set(factory, jid, status="done", result_key="k", expires_at=_ago(hours=1))
    dx_jobs.purge_expired_exports_task(0)
    assert _job(factory, ids, jid) is not None


def test_sweep_redefers_stale_pending_and_fails_stuck_running(env, monkeypatch):
    factory, ids, _s3, _ = env
    calls = []
    monkeypatch.setattr(
        dx_jobs.run_collection_export, "defer", lambda **kw: calls.append(kw), raising=False
    )
    stale = _new_job(factory, ids)
    recent = _new_job(factory, ids)
    stuck = _new_job(factory, ids)
    ok = _new_job(factory, ids)
    _set(factory, stale, created_at=_ago(minutes=10))
    _set(factory, stuck, status="running", started_at=_ago(hours=2))
    _set(factory, ok, status="running", started_at=_ago(minutes=2))
    dx_jobs.sweep_collection_exports_task(0)
    assert calls == [{"job_id": stale, "tenant_id": ids[0]}]
    assert _job(factory, ids, stuck).status == "failed"
    # REV-323 B : l'abandon est notifié au demandeur
    from sqlalchemy import select

    from app.notifications.models import Notification

    with factory() as s:
        notif = s.scalars(select(Notification)).one()
    assert notif.status == "failure" and "timed out" in (notif.error_message or "")
    assert _job(factory, ids, ok).status == "running"
    assert _job(factory, ids, recent).status == "pending"


def test_reclaim_is_compare_and_swap_on_started_at(env):
    factory, ids, _s3, _ = env
    jid = _new_job(factory, ids)
    old = _ago(hours=2)
    _set(factory, jid, status="running", started_at=old)
    with factory() as s:
        # le job est repris (nouveau started_at) entre la lecture et l'écriture
        real = s.execute

        def racing(stmt, *a, **k):
            if getattr(stmt, "is_update", False):
                _set(factory, jid, started_at=_ago(minutes=1))
            return real(stmt, *a, **k)

        s.execute = racing  # type: ignore[method-assign]
        assert dx_repo.reclaim_stuck_running(s) == []
    assert _job(factory, ids, jid).status == "running"


def test_usage_counts_data_exports_prefix(monkeypatch):
    from app.quotas import service

    seen = []
    monkeypatch.setattr(service, "job_output_storage_bytes", lambda s, t: 0)
    monkeypatch.setattr(service, "count_items_for_tenant", lambda s, t: 0)
    monkeypatch.setattr(service, "count_collections_for_tenant", lambda s, t: 0)
    monkeypatch.setattr(service, "count_users_for_tenant", lambda s, t: 0)
    monkeypatch.setattr(
        service,
        "tenant_prefixed_storage_bytes",
        lambda s3, bucket, tenant, prefix=None: seen.append(prefix) or 0,
    )
    service.usage_for_tenant(None, None, "t1")
    assert "t1/data-exports/" in seen
