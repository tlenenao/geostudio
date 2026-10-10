# SPDX-License-Identifier: Apache-2.0
"""run_pipeline_sweep_task (SP-15h) : balayage périodique des pipelines
planifiés. Pure SQLite (pas de postgis) — ce test vérifie la décision
"faut-il créer/déferer un run", pas l'exécution réelle d'un pipeline
(déjà couverte par test_pipeline_jobs.py::run_pipeline_task, postgis-marqué).
run_pipeline_task.defer est monkeypatché : le sweep n'a besoin de PROUVER
que run_pipeline_task a été sollicité avec les bons arguments, jamais de le
laisser tourner pour de vrai ici."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import select, update

from app.configs import repository as configs_repo
from app.configs.models import Config, ConfigRevision
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
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.collection",
                    "params": {"collectionId": "villes"},
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.collection",
                    "params": {"collectionId": "villes_propres"},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }
    if refresh_policy is not None:
        body["pipeline"]["refreshPolicy"] = refresh_policy
    return body


def _seed_due_pipeline(session, *, tenant_id, owner_id, item_id="pipe-1"):
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=owner_id,
        resource_type="pipeline",
        title="P",
    )
    config = BuilderConfig.model_validate(_pipeline_body({"enabled": True, "cron": "*/5 * * * *"}))
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    # REV-312 : sans run antérieur la cadence part de la création/activation de la
    # config ; on l'antidate pour que le cron `*/5` soit échu (« dû »).
    _backdate_config(session, item.id, datetime.now(UTC) - timedelta(hours=1))
    return item.id


def _backdate_config(session, item_id, when):
    config_id = session.execute(select(Config.id).where(Config.item_id == item_id)).scalar_one()
    session.execute(
        update(ConfigRevision).where(ConfigRevision.config_id == config_id).values(created_at=when)
    )


def test_sweep_defers_run_pipeline_task_for_a_due_pipeline(monkeypatch):
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
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="pipeline",
            title="P",
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
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_commits_run_before_deferring(monkeypatch, tmp_path):
    # sqlite ":memory:" partage UNE connexion physique unique via StaticPool
    # (cf. _make_session/app.db.make_engine) : une seconde Session() issue de
    # la même factory verrait alors la MÊME transaction non validée, ce qui
    # rendrait ce test aveugle au bug (il passerait même sans le fix). On
    # utilise donc un fichier sqlite temporaire avec DEUX engines distincts
    # (deux vraies connexions) pour obtenir une isolation transactionnelle
    # réelle, comparable à deux connexions Postgres séparées en production.
    db_url = f"sqlite+pysqlite:///{tmp_path / 'sweep.db'}"

    main_engine = make_engine(db_url)
    init_db(main_engine)
    Session = make_session_factory(main_engine)

    separate_engine = make_engine(db_url)
    SeparateSession = make_session_factory(separate_engine)

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
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    seen_from_separate_session = []

    def fake_defer(**kw):
        # Au moment où defer() est appelé, le run doit déjà être visible
        # depuis une session INDÉPENDANTE (preuve que le commit a bien eu
        # lieu avant, pas seulement flush() dans la même transaction).
        with SeparateSession() as s2:
            run = pipelines_repo.get_run(s2, tenant_id=tenant.id, run_id=kw["run_id"])
            seen_from_separate_session.append(run is not None)

    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", fake_defer)
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert seen_from_separate_session == [True]


def test_sweep_short_circuits_when_etl_disabled(monkeypatch):
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
        _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: False)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []


def test_sweep_fails_the_stale_running_run_it_replaces(monkeypatch):
    """c02-005 : le run « running » périmé ne reste pas zombie à côté du nouveau."""
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import select

    from app.pipelines.models import PipelineRun

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
        item_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        old = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        old.status = "running"
        old.started_at = old.created_at = datetime.now(UTC) - timedelta(hours=3)
        old_id = old.id
        s.commit()

    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: None)
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    with Session() as s:
        runs = {r.id: r for r in s.scalars(select(PipelineRun))}
    assert len(runs) == 2
    assert runs[old_id].status == "failed"
    assert runs[old_id].finished_at is not None
    assert sorted(r.status for r in runs.values()) == ["failed", "queued"]


def test_sweep_writes_pipeline_run_audit_with_schedule_actor(monkeypatch):
    # c03-003 : un run planifié laisse la même trace audit que POST /run.
    from sqlalchemy import select

    from app.audit.models import AuditLog

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
        item_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        s.commit()
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: None)
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    with Session() as s:
        row = s.execute(select(AuditLog).where(AuditLog.action == "pipeline.run")).scalar_one()
        assert (row.tenant_id, row.actor_id, row.actor_kind) == (tenant.id, user.id, "schedule")
        assert row.payload == {"pipelineItemId": item_id}


def test_sweep_does_not_create_a_run_when_one_became_active_after_the_due_check(monkeypatch):
    """REV-310 (jumelle cron) : le balayage passe par la même création atomique
    que POST /run — un run actif apparu entre le calcul « dû » et l'insertion
    (déclenchement manuel concurrent) est respecté, pas doublé."""
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
        item_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)  # actif
        s.commit()

    deferred = []
    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: deferred.append(kw))
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)
    # Le calcul « dû » (instantané périmé) désigne quand même le pipeline.
    monkeypatch.setattr(
        pipelines_repo, "list_due_pipelines", lambda session: [(item_id, tenant.id)]
    )

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    assert deferred == []
    with Session() as s:
        runs = pipelines_repo.list_runs(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        assert len(runs) == 1


def test_never_run_yearly_cron_waits_for_its_first_occurrence_not_the_first_sweep():
    """REV-312 (j06b-013) : « 1er janvier 3h », horloge figée — un pipeline sans run
    antérieur n'est pas exécuté au premier balayage mais à son échéance, comptée
    depuis la création/activation de la config."""
    Session = _make_session()
    created = datetime(2026, 10, 10, 12, 0, tzinfo=UTC)
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
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="Annuel"
        )
        body = _pipeline_body({"enabled": True, "cron": "0 3 1 1 *"})
        configs_repo.create_config(
            s, BuilderConfig.model_validate(body), item_id=item.id, tenant_id=tenant.id
        )
        _backdate_config(s, item.id, created)
        s.commit()
        due = pipelines_repo.list_due_pipelines
        assert due(s, now=created + timedelta(minutes=5)) == []  # 1er balayage : pas dû
        assert due(s, now=datetime(2027, 1, 1, 2, 59, tzinfo=UTC)) == []
        assert due(s, now=datetime(2027, 1, 1, 3, 0, 1, tzinfo=UTC)) == [(item.id, tenant.id)]


def test_sweep_keeps_stale_reclaim_when_first_due_pipeline_conflicts(monkeypatch):
    """Le rollback sur PipelineRunActive n'annule pas la clôture des runs périmés."""
    from app.pipelines.models import PipelineRun

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
        due_id = _seed_due_pipeline(s, tenant_id=tenant.id, owner_id=user.id)
        pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=due_id)  # actif
        other = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="O"
        )
        stale = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=other.id)
        stale.created_at = datetime.now(UTC) - timedelta(hours=3)
        stale_id = stale.id
        s.commit()

    monkeypatch.setattr(pipeline_jobs.run_pipeline_task, "defer", lambda **kw: None)
    monkeypatch.setattr(pipeline_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(pipeline_jobs, "is_read_only_mode", lambda: False)
    monkeypatch.setattr(pipeline_jobs, "is_etl_enabled", lambda: True)
    monkeypatch.setattr(pipelines_repo, "list_due_pipelines", lambda session: [(due_id, tenant.id)])

    pipeline_jobs.run_pipeline_sweep_task(timestamp=0)

    with Session() as s:
        assert s.get(PipelineRun, stale_id).status == "failed"
