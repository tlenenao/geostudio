# SPDX-License-Identifier: Apache-2.0
from datetime import UTC, datetime, timedelta

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.pipelines import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_session():
    # init_db() (et non Base.metadata.create_all() directement) : elle importe
    # d'abord tous les modules app.*.models pour que Base.metadata connaisse
    # `items`/`tenants`/`users`, cibles des ForeignKey de pipeline_runs — sinon
    # la résolution de la FK vers `items` échoue en lancement isolé de ce
    # fichier (cf. notes d'exécution SP-15a tâche 7).
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    return make_session_factory(engine)


def _make_pipeline_item(session, *, tenant_id):
    # pipeline_runs.pipeline_item_id référence items.id (nullable=False) : il
    # faut un Item réel, pas un identifiant arbitraire, sinon la contrainte
    # FK échoue à l'insertion (PRAGMA foreign_keys=ON, cf. app/db.py).
    user = get_or_create_user(
        session,
        tenant_id=tenant_id,
        oidc_sub="a",
        username="alice",
        email=None,
        first_name="",
        last_name="",
    )
    item = items_repo.create_item(
        session,
        tenant_id=tenant_id,
        owner_id=user.id,
        resource_type="pipeline",
        title="Pipeline de test",
    )
    return item.id


def _make_pipeline_config(session, *, tenant_id, item_id, refresh_policy=None):
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
    config = BuilderConfig.model_validate(body)
    configs_repo.create_config(session, config, item_id=item_id, tenant_id=tenant_id)


def test_create_run_defaults_to_queued():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        assert run.status == "queued"
        assert run.started_at is None


def test_get_run_round_trips():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched is not None
        assert fetched.id == run.id


def test_get_run_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        assert repo.get_run(s, tenant_id="other-tenant", run_id=run.id) is None


def test_list_runs_ordered_most_recent_first():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        first = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        second = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        runs = repo.list_runs(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        assert [r.id for r in runs] == [second.id, first.id] or set(r.id for r in runs) == {
            first.id,
            second.id,
        }


def test_mark_running_then_succeeded():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        repo.mark_running(s, run_id=run.id)
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "running"
        assert fetched.started_at is not None

        repo.mark_succeeded(s, run_id=run.id, node_stats={"r1": {"rowCount": 3}})
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "succeeded"
        assert fetched.node_stats == {"r1": {"rowCount": 3}}
        assert fetched.finished_at is not None


def test_mark_failed_records_error():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        repo.mark_failed(s, run_id=run.id, error="collection not found")
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.status == "failed"
        assert fetched.error == "collection not found"


def test_append_node_stat_merges_into_existing_node_stats():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()

        repo.append_node_stat(
            s,
            tenant_id=tenant.id,
            run_id=run.id,
            node_id="r1",
            stat={"nodeId": "r1", "op": "reader.collection", "rowCount": 3},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {
            "r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 3}
        }

        repo.append_node_stat(
            s,
            tenant_id=tenant.id,
            run_id=run.id,
            node_id="w1",
            stat={"nodeId": "w1", "op": "writer.collection", "rowCount": 3},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {
            "r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 3},
            "w1": {"nodeId": "w1", "op": "writer.collection", "rowCount": 3},
        }


def test_append_node_stat_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        repo.append_node_stat(
            s,
            tenant_id="other-tenant",
            run_id=run.id,
            node_id="r1",
            stat={"rowCount": 1},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {}


def test_get_latest_run_returns_none_when_no_runs():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        assert (
            repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id) is None
        )


def test_get_latest_run_returns_most_recent():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        second = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        latest = repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        assert latest is not None
        assert latest.id == second.id


def test_get_latest_run_scoped_to_tenant():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        pipeline_item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id)
        s.commit()
        assert (
            repo.get_latest_run(s, tenant_id="other-tenant", pipeline_item_id=pipeline_item_id)
            is None
        )


def test_list_due_pipelines_excludes_pipelines_without_refresh_policy():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(s, tenant_id=tenant.id, item_id=item_id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_excludes_disabled_policy():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s,
            tenant_id=tenant.id,
            item_id=item_id,
            refresh_policy={"enabled": False, "cron": "*/5 * * * *"},
        )
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_includes_never_run_enabled_pipeline():
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
        s.commit()
        assert repo.list_due_pipelines(s) == [(item_id, tenant.id)]


def test_list_due_pipelines_excludes_pipeline_not_yet_due():
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_id = _make_pipeline_item(s, tenant_id=tenant.id)
        _make_pipeline_config(
            s,
            tenant_id=tenant.id,
            item_id=item_id,
            # cron quotidien a 02:00 ; le run le plus récent vient d'avoir
            # lieu -> le prochain tick est dans le futur, jamais dû.
            refresh_policy={"enabled": True, "cron": "0 2 * * *"},
        )
        s.commit()
        repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_skips_run_already_in_progress():
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
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        repo.mark_running(s, run_id=run.id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_list_due_pipelines_reclaims_stale_running_run():
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
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        repo.mark_running(s, run_id=run.id)
        # Simule un run planté depuis longtemps : recule created_at ET
        # started_at au-delà du délai de reclaim (même seuil que le
        # moissonnage, 60 min). Reculer created_at seul ne suffit plus depuis
        # le fix "ancre de reclaim" (SP-15h review finding) : l'ancre pour un
        # run "running" est started_at (posé par mark_running), donc un
        # started_at frais ne serait jamais réclamé même avec un created_at
        # ancien — ce serait au contraire le run "juste démarré après un
        # long séjour en file" que le fix protège explicitement (cf.
        # test_list_due_pipelines_does_not_reclaim_run_that_just_started_after_long_queue
        # ci-dessous).
        stale = datetime.now(UTC) - timedelta(minutes=61)
        run.created_at = stale
        run.started_at = stale
        s.commit()
        assert repo.list_due_pipelines(s) == [(item_id, tenant.id)]


def test_list_due_pipelines_does_not_reclaim_run_that_just_started_after_long_queue():
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
        s.commit()
        run = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        # Simule un run resté en file d'attente longtemps (backlog worker)
        # avant de démarrer réellement il y a quelques secondes seulement :
        # created_at très ancien, mais started_at (posé par mark_running)
        # est frais -> ne doit PAS être réclamé.
        run.created_at = datetime.now(UTC) - timedelta(minutes=61)
        s.commit()
        repo.mark_running(s, run_id=run.id)
        s.commit()
        assert repo.list_due_pipelines(s) == []


def test_get_latest_runs_for_items_returns_the_most_recent_run_per_item():
    # GAP-64.1 (SP-49) : batch de get_latest_run pour list_due_pipelines —
    # item A a 3 runs à des created_at DIFFÉRENTS de l'ordre d'insertion
    # (falsifie un ROW_NUMBER() mal ordonné qui retournerait la dernière
    # ligne insérée plutôt que la plus récente par date) ; item B a 1 seul
    # run.
    Session = _make_session()
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        item_a = _make_pipeline_item(s, tenant_id=tenant.id)
        item_b = _make_pipeline_item(s, tenant_id=tenant.id)
        s.commit()
        now = datetime.now(UTC)
        run_a1 = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_a)
        run_a1.created_at = now - timedelta(minutes=30)
        run_a2 = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_a)
        # run_a2 est inséré APRÈS run_a3 mais sa date est plus ancienne que
        # celle de run_a3 : l'ordre d'insertion diffère de l'ordre
        # chronologique attendu.
        run_a2.created_at = now - timedelta(minutes=10)
        run_a3 = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_a)
        run_a3.created_at = now - timedelta(minutes=20)
        run_b1 = repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_b)
        s.commit()

        latest_by_item = repo.get_latest_runs_for_items(s, item_ids=[item_a, item_b])

        assert set(latest_by_item) == {item_a, item_b}
        assert latest_by_item[item_a].id == run_a2.id
        assert latest_by_item[item_b].id == run_b1.id


def test_get_latest_runs_for_items_returns_empty_dict_for_empty_input():
    Session = _make_session()
    with Session() as s:
        assert repo.get_latest_runs_for_items(s, item_ids=[]) == {}
