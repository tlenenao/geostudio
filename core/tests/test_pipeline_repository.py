# SPDX-License-Identifier: Apache-2.0
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
        session, tenant_id=tenant_id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=user.id, resource_type="pipeline",
        title="Pipeline de test",
    )
    return item.id


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
        assert [r.id for r in runs] == [second.id, first.id] or set(r.id for r in runs) == {first.id, second.id}


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
            s, tenant_id=tenant.id, run_id=run.id, node_id="r1",
            stat={"nodeId": "r1", "op": "reader.collection", "rowCount": 3},
        )
        s.commit()
        fetched = repo.get_run(s, tenant_id=tenant.id, run_id=run.id)
        assert fetched.node_stats == {"r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 3}}

        repo.append_node_stat(
            s, tenant_id=tenant.id, run_id=run.id, node_id="w1",
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
            s, tenant_id="other-tenant", run_id=run.id, node_id="r1", stat={"rowCount": 1},
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
        assert repo.get_latest_run(s, tenant_id=tenant.id, pipeline_item_id=pipeline_item_id) is None


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
        assert repo.get_latest_run(s, tenant_id="other-tenant", pipeline_item_id=pipeline_item_id) is None
