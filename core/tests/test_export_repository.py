# SPDX-License-Identifier: Apache-2.0
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
