# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timedelta, timezone

from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)()


def test_create_job_starts_pending():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    assert job.status == "pending"
    assert job.error is None
    assert job.result_key is None
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched is not None
    assert fetched.format == "png"


def test_mark_running_then_done():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_done(session, job_id=job.id, result_key="exports/item-1/x.pdf")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "done"
    assert fetched.result_key == "exports/item-1/x.pdf"
    assert fetched.started_at is not None
    assert fetched.finished_at is not None


def test_mark_error_never_leaves_status_running():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    export_repo.mark_error(session, job_id=job.id, error="render timeout")
    session.commit()
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert fetched.error == "render timeout"


def test_get_job_scoped_to_tenant():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    assert export_repo.get_job(session, tenant_id="other-tenant", job_id=job.id) is None


# Finding I7 (revue finale) : reclaim_stuck_jobs — pas d'appelant périodique
# encore câblé (TODO dans app/export/jobs.py), mais la fonction elle-même
# doit fonctionner correctement, testée directement ici.


def test_reclaim_stuck_jobs_marks_old_running_jobs_as_error():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    # Simule un job démarré il y a 2h (au-delà du seuil par défaut de 60min) —
    # écrase directement started_at, aucun setter public ne permet d'antidater.
    job.started_at = datetime.now(timezone.utc) - timedelta(hours=2)
    session.commit()

    reclaimed = export_repo.reclaim_stuck_jobs(session)
    session.commit()

    assert reclaimed == [job.id]
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "error"
    assert fetched.error is not None
    assert fetched.finished_at is not None


def test_reclaim_stuck_jobs_leaves_recent_running_jobs_alone():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)  # started_at = maintenant
    session.commit()

    reclaimed = export_repo.reclaim_stuck_jobs(session)
    session.commit()

    assert reclaimed == []
    fetched = export_repo.get_job(session, tenant_id=tenant.id, job_id=job.id)
    assert fetched.status == "running"


def test_reclaim_stuck_jobs_ignores_pending_and_done_jobs():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    pending_job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    done_job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf")
    session.commit()
    export_repo.mark_running(session, job_id=done_job.id)
    export_repo.mark_done(session, job_id=done_job.id, result_key="x")
    done_job.finished_at = datetime.now(timezone.utc) - timedelta(hours=2)
    session.commit()

    reclaimed = export_repo.reclaim_stuck_jobs(session)
    session.commit()

    assert reclaimed == []
    assert export_repo.get_job(session, tenant_id=tenant.id, job_id=pending_job.id).status == "pending"
    assert export_repo.get_job(session, tenant_id=tenant.id, job_id=done_job.id).status == "done"


def test_create_job_accepts_optional_page_id_and_ctx():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="pdf",
        page_id="page-2", ctx="eyJ0aW1lUmFuZ2UiOm51bGx9",
    )
    session.commit()
    assert job.page_id == "page-2"
    assert job.ctx == "eyJ0aW1lUmFuZ2UiOm51bGx9"


def test_create_job_defaults_page_id_and_ctx_to_none():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    assert job.page_id is None
    assert job.ctx is None


def test_reclaim_stuck_jobs_respects_custom_threshold():
    session = _session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(session, tenant_id=tenant.id, oidc_sub="user-1", username="user1", email="user1@test.com", first_name="User", last_name="One")
    item = items_repo.create_item(session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="Test App")
    session.commit()
    job = export_repo.create_job(session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png")
    session.commit()
    export_repo.mark_running(session, job_id=job.id)
    job.started_at = datetime.now(timezone.utc) - timedelta(minutes=10)
    session.commit()

    # 10 minutes-old running job is NOT stuck under the default 60min
    # threshold, but IS stuck under a tighter 5min threshold.
    assert export_repo.reclaim_stuck_jobs(session, older_than_minutes=60) == []
    assert export_repo.reclaim_stuck_jobs(session, older_than_minutes=5) == [job.id]
