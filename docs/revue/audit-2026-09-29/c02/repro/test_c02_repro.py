# SPDX-License-Identifier: Apache-2.0
"""Repros de l'audit c02 (lecture seule sur le code : ce fichier ne vit que
dans docs/revue/audit-2026-09-29/c02/). Chaque test ÉCHOUE-t-il ou PASSE-t-il
selon le comportement observé : les assertions décrivent le comportement
ACTUEL (défaut), pas le comportement attendu.

Lancer depuis core/ :
    PYTHONPATH=. uv run pytest ../docs/revue/audit-2026-09-29/c02/repro/test_c02_repro.py \
        -p no:cacheprovider --basetemp=<scratch> -q
"""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as SASession

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _setup(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'c02.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    factory = make_session_factory(engine)
    with factory() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        dataset_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Dataset"
        )
        dataset_cfg = configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "col1"}}
            ),
            item_id=dataset_item.id,
            tenant_id=tenant.id,
        )
        rule_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="alert", title="Rule"
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "kind": "alert",
                    "alert": {
                        "datasetItemId": dataset_item.id,
                        "query": {"agg": "count"},
                        "condition": {"expr": "value > 100"},
                        "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                        "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                    },
                }
            ),
            item_id=rule_item.id,
            tenant_id=tenant.id,
        )
        s.commit()
        ids = (dataset_item.id, dataset_cfg.id, rule_item.id)
    client = TestClient(app, raise_server_exceptions=False)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, ids


def test_c02_delete_config_by_id_skips_reverse_reference_guard(monkeypatch, tmp_path):
    client, (dataset_item_id, dataset_config_id, rule_item_id) = _setup(monkeypatch, tmp_path)
    # La route jumelle refuse (409) :
    assert client.delete(f"/v1/configs/by-item/{dataset_item_id}").status_code == 409
    # ... mais DELETE /configs/{id} supprime le même Dataset encore référencé :
    resp = client.delete(f"/v1/configs/{dataset_config_id}")
    print("DELETE /v1/configs/{id} ->", resp.status_code)
    assert resp.status_code == 204
    assert client.get(f"/v1/items/{dataset_item_id}").status_code == 404
    # l'AlertRule pointe désormais vers un Dataset inexistant :
    rule = client.get(f"/v1/configs/by-item/{rule_item_id}").json()
    assert rule["config"]["alert"]["datasetItemId"] == dataset_item_id


def test_c02_commit_failure_after_2xx_response(monkeypatch, tmp_path):
    client, _ids = _setup(monkeypatch, tmp_path)
    before = client.get("/v1/items").json()
    n_before = len(before["items"] if isinstance(before, dict) else before)

    real_commit = SASession.commit

    def failing_commit(self):  # simule une erreur au COMMIT (coupure, sérialisation, contrainte différée)
        raise RuntimeError("simulated commit failure")

    monkeypatch.setattr(SASession, "commit", failing_commit)
    resp = client.post(
        "/v1/configs",
        json={"title": "Carte perdue", "config": {"kind": "map", "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}}}},
    )
    monkeypatch.setattr(SASession, "commit", real_commit)
    print("POST /v1/configs with failing commit ->", resp.status_code)
    assert resp.status_code == 201  # le client reçoit un succès...
    after = client.get("/v1/items").json()
    n_after = len(after["items"] if isinstance(after, dict) else after)
    assert n_after == n_before  # ... alors que rien n'a été persisté


def test_c02_stale_pipeline_run_is_redispatched_but_never_failed():
    from datetime import UTC, datetime, timedelta

    from app.pipelines import repository as pipelines_repo
    from app.pipelines.models import PipelineRun
    from tests.test_pipeline_repository import (
        _make_pipeline_config,
        _make_pipeline_item,
        _make_session,
    )

    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s,
            tenant_id=tenant.id,
            item_id=item_id,
            refresh_policy={"enabled": True, "cron": "*/5 * * * *"},
        )
        old = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        pipelines_repo.mark_running(s, run_id=old.id)
        stale = datetime.now(UTC) - timedelta(minutes=61)
        old.created_at = stale
        old.started_at = stale
        s.commit()
        # Même séquence que run_pipeline_sweep_task :
        for due_item, due_tenant in pipelines_repo.list_due_pipelines(s):
            pipelines_repo.create_run(s, tenant_id=due_tenant, pipeline_item_id=due_item)
        s.commit()
        statuses = sorted(r.status for r in s.query(PipelineRun).all())
        print("pipeline_runs after sweep:", statuses)
        # l'ancien run n'est jamais marqué failed et un 2e run est lancé à côté :
        assert statuses == ["queued", "running"]


def test_c02_ingestion_reclaim_then_mark_done_flips_error_to_done():
    from datetime import UTC, datetime, timedelta

    from app.ingestion import repository as ingestion_repo
    from app.ingestion.models import IngestionJob
    from tests.test_pipeline_repository import _make_session

    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="u", username="u", email=None,
            first_name="", last_name="",
        )
        job = ingestion_repo.create_job(
            s, tenant_id=tenant.id, created_by=user.id, source_key="k", filename="f.gpkg",
            collection_title="C", lat_field=None, lon_field=None,
        )
        ingestion_repo.mark_running(s, job_id=job.id)
        s.commit()
        # import long (> 60 min) : updated_at n'est jamais rafraîchi pendant run_import
        s.query(IngestionJob).filter_by(id=job.id).update(
            {"updated_at": datetime.now(UTC) - timedelta(minutes=61)}
        )
        s.commit()
        assert ingestion_repo.reclaim_stuck_jobs(s) == [job.id]  # sweep : "error" + notif échec
        s.commit()
        # ... puis le worker, toujours vivant, termine son import :
        ingestion_repo.mark_done(s, job_id=job.id, collection_id="c1", item_id=None)
        s.commit()
        s.refresh(job)
        print("ingestion job final status:", job.status, "| error_message:", job.error_message)
        assert job.status == "done"
        assert job.error_message == "ingestion timed out (worker crashed or hung)"


def test_c02_defer_failure_strands_queued_run(monkeypatch):
    from app.pipelines import routes as pipelines_routes
    from app.pipelines.models import PipelineRun
    from tests.test_pipeline_repository import _make_pipeline_config
    from tests.test_pipeline_routes import _make_app

    client = _make_app(monkeypatch, etl_enabled=True)
    Session = client.session_factory
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=client.tenant.id, owner_id=client.user.id,
            resource_type="pipeline", title="P",
        )
        _make_pipeline_config(s, tenant_id=client.tenant.id, item_id=item.id)
        s.commit()
        item_id = item.id

    def broken_deferrer(run_id, tenant_id):
        raise ConnectionError("procrastinate: connection refused")

    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: broken_deferrer
    client_nr = TestClient(client.app, raise_server_exceptions=False)
    resp = client_nr.post(f"/v1/pipelines/{item_id}/run")
    with Session() as s:
        statuses = [r.status for r in s.query(PipelineRun).all()]
    print("POST run with failing defer ->", resp.status_code, "| pipeline_runs:", statuses)
    assert resp.status_code == 500
    assert statuses == ["queued"]  # run committé, jamais exécuté, jamais réclamé
