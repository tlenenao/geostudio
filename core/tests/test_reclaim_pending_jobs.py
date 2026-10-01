# SPDX-License-Identifier: Apache-2.0
"""P01.04 (j03-003, j09b-010, c02-007) : « commit puis defer » n'est pas atomique.
Un job jamais pris en charge (defer perdu, file non consommée) reste `pending`/
`queued` ; les balayages le clôturent désormais comme un job `running` périmé."""

from datetime import UTC, datetime, timedelta

from app.appexport import repository as appexport_repo
from app.db import init_db, make_engine, make_session_factory
from app.export import repository as export_repo
from app.ingestion import repository as ingestion_repo
from app.items import repository as items_repo
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

OLD = datetime.now(UTC) - timedelta(hours=2)


def _env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session = make_session_factory(engine)()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="u",
        username="u",
        email=None,
        first_name="",
        last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant.id, owner_id=user.id, resource_type="app", title="A"
    )
    session.commit()
    return session, tenant, user, item


def test_old_pending_ingestion_job_is_reclaimed():
    session, tenant, user, _ = _env()
    job = ingestion_repo.create_job(
        session,
        tenant_id=tenant.id,
        created_by=user.id,
        source_key="k",
        filename="f.geojson",
        collection_title="V",
        lat_field=None,
        lon_field=None,
    )
    session.commit()
    assert ingestion_repo.reclaim_stuck_jobs(session) == []  # récent : intact
    job.updated_at = OLD
    session.commit()
    assert ingestion_repo.reclaim_stuck_jobs(session) == [job.id]
    assert job.status == "error"


def test_old_pending_export_job_is_reclaimed():
    session, tenant, user, item = _env()
    job = export_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, format="png"
    )
    job.created_at = OLD
    session.commit()
    assert export_repo.reclaim_stuck_jobs(session) == [job.id]
    assert job.status == "error"


def test_old_pending_appexport_job_is_reclaimed():
    session, tenant, user, item = _env()
    job = appexport_repo.create_job(
        session, tenant_id=tenant.id, item_id=item.id, user_id=user.id, mode="static"
    )
    job.created_at = OLD
    session.commit()
    assert appexport_repo.reclaim_stuck_jobs(session) == [job.id]
    assert job.status == "error"


def test_old_queued_pipeline_run_is_reclaimed_and_recent_is_not():
    session, tenant, _, item = _env()
    old = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
    old.created_at = OLD
    recent = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
    session.commit()
    assert pipelines_repo.reclaim_stuck_runs(session) == 1
    session.commit()
    session.refresh(old)
    session.refresh(recent)
    assert (old.status, recent.status) == ("failed", "queued")
