# SPDX-License-Identifier: Apache-2.0
"""run_pipeline_sweep_task (SP-15h) : balayage périodique des pipelines
planifiés. Pure SQLite (pas de postgis) — ce test vérifie la décision
"faut-il créer/déferer un run", pas l'exécution réelle d'un pipeline
(déjà couverte par test_pipeline_jobs.py::run_pipeline_task, postgis-marqué).
run_pipeline_task.defer est monkeypatché : le sweep n'a besoin de PROUVER
que run_pipeline_task a été sollicité avec les bons arguments, jamais de le
laisser tourner pour de vrai ici."""
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _pipeline_body(refresh_policy=None):
    body = {
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }
    if refresh_policy is not None:
        body["pipeline"]["refreshPolicy"] = refresh_policy
    return body


def _seed_due_pipeline(session, *, tenant_id, owner_id, item_id="pipe-1"):
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="pipeline", title="P",
    )
    config = BuilderConfig.model_validate(
        _pipeline_body({"enabled": True, "cron": "*/5 * * * *"})
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_sweep_defers_run_pipeline_task_for_a_due_pipeline(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert len(deferred) == 1
    assert deferred[0]["tenant_id"] == tenant.id
    with Session() as s:
        run = pipelines_repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        assert run is not None
        assert run.status == "queued"
        assert run.id == deferred[0]["run_id"]


def test_sweep_defers_nothing_when_no_pipeline_is_due(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="P",
        )
        config = BuilderConfig.model_validate(_pipeline_body())  # pas de refreshPolicy
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_short_circuits_in_read_only_mode(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_short_circuits_when_etl_disabled(monkeypatch):
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: False)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []
