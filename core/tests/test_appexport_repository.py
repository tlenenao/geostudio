# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.appexport import repository as appexport_repo
from app.appexport.models import AppExportJob
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_create_and_get_job():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    fetched = appexport_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched is not None
    assert fetched.status == "pending"
    assert fetched.mode == "static"


def test_get_job_wrong_tenant_returns_none():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    assert appexport_repo.get_job(session, tenant_id="other", job_id=job.id) is None


def test_mark_running_then_done():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    appexport_repo.mark_running(session, job_id=job.id)
    session.commit()
    fetched = appexport_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "running"
    assert fetched.started_at is not None

    appexport_repo.mark_done(session, job_id=job.id, result_key="appexports/x.zip")
    session.commit()
    fetched = appexport_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "done"
    assert fetched.result_key == "appexports/x.zip"
    assert fetched.finished_at is not None


def test_mark_error():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    appexport_repo.mark_error(session, job_id=job.id, error="boom")
    session.commit()
    fetched = appexport_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert fetched.error == "boom"


def test_reclaim_stuck_jobs_anchors_on_started_at():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    appexport_repo.mark_running(session, job_id=job.id)
    # Backdate started_at past the reclaim threshold directly (same
    # pattern as core/tests/test_export_repository.py).
    row = session.get(AppExportJob, job.id)
    row.started_at = datetime.now(timezone.utc) - timedelta(minutes=90)
    session.commit()

    reclaimed = appexport_repo.reclaim_stuck_jobs(session, older_than_minutes=60)
    session.commit()
    assert reclaimed == [job.id]
    fetched = appexport_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"


def test_reclaim_stuck_jobs_ignores_recent_running():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static",
    )
    session.commit()
    appexport_repo.mark_running(session, job_id=job.id)
    session.commit()

    reclaimed = appexport_repo.reclaim_stuck_jobs(session, older_than_minutes=60)
    assert reclaimed == []
