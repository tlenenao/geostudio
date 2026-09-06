# SPDX-License-Identifier: Apache-2.0
"""sweep_ingestion_jobs_task (GAP-56.3, SP-49) : réclamation périodique des
jobs ingestion_jobs restés "running" (worker tué en cours d'import). Pure
SQLite (pas de postgis) — même patron que test_pipeline_sweep.py : ce test
vérifie que le reclaim a bien lieu et qu'une notification best-effort est
écrite pour chaque job réclamé, pas l'exécution réelle d'un import."""

from datetime import UTC, datetime, timedelta

from app.db import init_db, make_engine, make_session_factory
from app.ingestion import repository as ingestion_repo
from app.ingestion import tasks as ingestion_tasks
from app.notifications import repository as notifications_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def test_sweep_reclaims_a_stuck_job_and_notifies_the_creator(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k",
            filename="f.geojson",
            collection_title="Villes",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        ingestion_repo.mark_running(s, job_id=job.id)
        job.updated_at = datetime.now(UTC) - timedelta(hours=2)
        s.commit()
        job_id = job.id
        tenant_id = tenant.id

    monkeypatch.setattr(ingestion_tasks, "session_factory", lambda: Session)
    monkeypatch.setattr(ingestion_tasks, "is_read_only_mode", lambda: False)

    ingestion_tasks.sweep_ingestion_jobs_task(timestamp=0)

    with Session() as s:
        job = ingestion_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
        assert job.status == "error"
        notifications, total = notifications_repo.list_notifications(
            s,
            tenant_id=tenant_id,
            recipient_user_id=user.id,
            preference="all",
            page=1,
            page_size=10,
        )
        assert total == 1
        assert notifications[0].status == "failure"
        assert notifications[0].kind == "ingestion"


def test_sweep_does_nothing_when_no_job_is_stuck(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k",
            filename="f.geojson",
            collection_title="Villes",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        ingestion_repo.mark_running(s, job_id=job.id)  # updated_at = maintenant
        s.commit()
        job_id = job.id
        tenant_id = tenant.id

    monkeypatch.setattr(ingestion_tasks, "session_factory", lambda: Session)
    monkeypatch.setattr(ingestion_tasks, "is_read_only_mode", lambda: False)

    ingestion_tasks.sweep_ingestion_jobs_task(timestamp=0)

    with Session() as s:
        job = ingestion_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
        assert job.status == "running"


def test_sweep_short_circuits_in_read_only_mode(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        job = ingestion_repo.create_job(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            source_key="k",
            filename="f.geojson",
            collection_title="Villes",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        ingestion_repo.mark_running(s, job_id=job.id)
        job.updated_at = datetime.now(UTC) - timedelta(hours=2)
        s.commit()
        job_id = job.id
        tenant_id = tenant.id

    monkeypatch.setattr(ingestion_tasks, "session_factory", lambda: Session)
    monkeypatch.setattr(ingestion_tasks, "is_read_only_mode", lambda: True)

    ingestion_tasks.sweep_ingestion_jobs_task(timestamp=0)

    with Session() as s:
        job = ingestion_repo.get_job(s, tenant_id=tenant_id, job_id=job_id)
        assert job.status == "running"
