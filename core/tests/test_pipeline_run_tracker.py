# SPDX-License-Identifier: Apache-2.0
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _seed_run(factory):
    with factory() as session:
        tenant = get_or_create_default_tenant(session)
        user = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="u1",
            username="u1",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            session,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="pipeline",
            title="P",
        )
        session.commit()
        run = pipelines_repo.create_run(session, tenant_id=tenant.id, pipeline_item_id=item.id)
        session.commit()
        return tenant.id, run.id


def test_postgres_run_tracker_mark_running_sets_status_and_started_at():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_running()

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "running"
        assert run.started_at is not None


def test_postgres_run_tracker_mark_succeeded_stores_node_stats():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_succeeded({"n1": {"rows": 3}})

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "succeeded"
        assert run.node_stats == {"n1": {"rows": 3}}


def test_postgres_run_tracker_mark_failed_stores_error():
    factory = _session_factory()
    tenant_id, run_id = _seed_run(factory)
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id=run_id, tenant_id=tenant_id)

    tracker.mark_failed("boom")

    with factory() as session:
        run = pipelines_repo.get_run(session, tenant_id=tenant_id, run_id=run_id)
        assert run.status == "failed"
        assert run.error == "boom"


def test_postgres_run_tracker_mark_running_on_unknown_run_is_a_noop():
    # pipelines_repo.mark_running/mark_succeeded/mark_failed font un
    # session.get(...) et ne font rien silencieusement si le run est
    # introuvable (pas d'exception) — ancre ce contrat pour les 3 méthodes
    # de PostgresRunTracker, pas seulement pour un run existant.
    factory = _session_factory()
    tracker = pipeline_jobs.PostgresRunTracker(factory, run_id="does-not-exist", tenant_id="t1")

    tracker.mark_running()  # ne doit lever aucune exception
    tracker.mark_succeeded({})  # ne doit lever aucune exception
    tracker.mark_failed("boom")  # ne doit lever aucune exception
