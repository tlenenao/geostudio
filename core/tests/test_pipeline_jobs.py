# SPDX-License-Identifier: Apache-2.0
import geopandas as gpd
import pytest
from procrastinate import testing
from shapely.geometry import Point
from sqlalchemy import select, text

from app.collections.ddl import apply_collection_ddl
from app.db import Base, make_session_factory
from app.items import repository as items_repo  # noqa: F401 -- enregistre Item sur Base.metadata
from app.notifications import repository as notifications_repo
from app.notifications.models import Notification
from app.pipelines import jobs as pipeline_jobs
from app.pipelines import repository as pipelines_repo
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role

pytestmark = pytest.mark.postgis


def _write_partition(base_dir, *, tenant_id, collection_id="villes", rows):
    partition_dir = (
        base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-05"
    )
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


@pytest.fixture()
def env(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
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
        item_id = "item-1"
        s.execute(
            text(
                "INSERT INTO items (id, tenant_id, owner_id, resource_type, title, abstract, "
                "is_published, is_public, keywords, created_at, updated_at) "
                "VALUES (:id, :t, :o, 'pipeline', 'P', '', false, false, '[]', now(), now())"
            ),
            {"id": item_id, "t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, description, "
                "pk_column, geometry_column, is_public, editable, created_at, updated_at) "
                "VALUES ('villes_propres', :t, :o, 'villes_propres', 'V', '', 'id', 'geometry', "
                "false, true, now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE villes_propres (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
            )
        )
        # Sans ceci, l'INSERT du run échoue "permission denied" : gis_rls
        # n'a aucun droit sur une table créée à la main (le CREATE TABLE brut
        # ci-dessus ne fait pas ce qu'une vraie inscription de collection
        # ferait) — même GRANTs/RLS/politique que
        # app.collections.ddl.apply_collection_ddl, déjà nécessaire dans
        # test_pipeline_runtime.py::test_run_pipeline_writes_into_target_collection
        # (Task 8) pour ce même scénario writer.collection.
        apply_collection_ddl(s, "villes_propres")
        s.commit()

    _write_partition(
        tmp_path,
        tenant_id=tenant.id,
        rows=[
            {
                "id": 1,
                "region": "Nord",
                "pop": 10,
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": Point(1.0, 45.0),
            },
        ],
    )
    monkeypatch.setenv("DATABASE_URL", pg_engine.url.render_as_string(hide_password=False))
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    monkeypatch.setenv("S3_CDC_BUCKET_BASE_URI", str(tmp_path))

    from app.configs.schemas import PipelinePayload

    payload = PipelinePayload.model_validate(
        {
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
        }
    )
    # Patch the runtime's collection lookups the same way Task 8's own tests do
    # (run_pipeline_task calls app.pipelines.runtime.run_pipeline, so the seams
    # to patch live on that module, not on pipeline_jobs itself).
    from app.collections.introspection import ColumnInfo, TableInfo
    from app.pipelines import runtime as pipeline_runtime

    table_info = TableInfo(
        table_name="villes",
        pk_column="id",
        geometry_column="geometry",
        geometry_type="Point",
        srid=4326,
        columns=[
            ColumnInfo(name="region", type="string", required=True),
            ColumnInfo(name="pop", type="integer", required=True),
        ],
    )
    monkeypatch.setattr(
        pipeline_runtime,
        "_table_info_for_collection",
        lambda session, collection_id: (
            table_info
            if collection_id == "villes"
            else pipeline_runtime.introspect_table(session, collection_id)
        ),
    )
    monkeypatch.setattr(
        pipeline_runtime,
        "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: (
            "villes" if collection_id == "villes" else collection_id
        ),
    )
    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: payload)

    in_memory = testing.InMemoryConnector()
    with pipeline_jobs.app.replace_connector(in_memory) as app:
        yield app, Session, tenant, user, item_id
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "DROP TABLE villes_propres; "
                "TRUNCATE pipeline_runs, items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_run_pipeline_task_marks_run_succeeded(env):
    app, Session, tenant, user, item_id = env
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "succeeded"
        count = s.execute(text("SELECT count(*) FROM villes_propres")).scalar()
        assert count == 1


def test_run_pipeline_task_marks_run_failed_never_zombie(env, monkeypatch):
    app, Session, tenant, user, item_id = env

    def _boom(session, *, item_id):
        raise ValueError("bad config")

    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error is not None


def test_success_writes_a_notification_for_the_item_owner(env):
    app, Session, tenant, user, item_id = env
    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.recipient_user_id == user.id
        assert notification.kind == "pipeline"
        assert notification.status == "success"
        assert notification.item_id == item_id
        assert notification.item_resource_type == "pipeline"


def test_failure_writes_a_notification(env, monkeypatch):
    app, Session, tenant, user, item_id = env

    def _boom(session, *, item_id):
        raise ValueError("bad config")

    monkeypatch.setattr(pipeline_jobs, "_get_pipeline_payload", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is not None
        assert notification.status == "failure"
        assert notification.error_message is not None


def test_notification_write_failure_does_not_affect_run_status(env, monkeypatch):
    """I2 (revue finale SP-39) : une erreur dans l'écriture de la
    notification ne doit jamais affecter le statut du run lui-même. Boom
    réel (viole une contrainte NOT NULL, SAWarning-as-error sous pytest ou
    IntegrityError hors pytest) plutôt qu'une exception Python qui ne
    toucherait jamais la session — cf. test_report_jobs.py pour la même
    falsification."""
    app, Session, tenant, user, item_id = env

    def _boom(session, **kwargs):
        session.add(
            Notification(
                tenant_id=tenant.id,
                recipient_user_id=user.id,
                kind="x",
                status="failure",
                item_title="x",
            )
        )
        session.flush()

    monkeypatch.setattr(notifications_repo, "create_notification", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "succeeded"
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is None


def test_early_failure_before_item_id_bound_does_not_crash(env, monkeypatch):
    """Régression (trouvée en écrivant cette tâche, même piège que Task 4/
    app.ingestion.tasks._notify) : si get_run/mark_running lève avant que
    item_id ne soit affecté, les handlers `except` de run_pipeline_task
    appelaient _notify(item_id=...) sur cette locale jamais liée ->
    UnboundLocalError levée APRÈS que mark_failed a déjà committé, donc le
    run finit bien "failed" (jamais zombie) mais la tâche procrastinate
    elle-même plantait au lieu d'avaler l'échec best-effort de la
    notification. Appel direct de la fonction (pas de passage par le
    worker procrastinate) : c'est cette levée qu'on veut voir absente ici."""
    app, Session, tenant, user, item_id = env

    def _boom(session, *, run_id):
        raise RuntimeError("connectivité DB perdue")

    monkeypatch.setattr(pipelines_repo, "mark_running", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task(run_id=run_id, tenant_id=tenant.id)

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error is not None

        # Pas de destinataire connu (item_id jamais lié) : aucune
        # notification de repli n'est écrite — le run est déjà marqué
        # "failed" ci-dessus, la garantie best-effort porte sur la
        # notification, pas sur le statut du run.
        notification = s.scalar(select(Notification).where(Notification.tenant_id == tenant.id))
        assert notification is None


def test_run_pipeline_task_writes_node_stats_incrementally_before_failure(env, monkeypatch):
    """Régression du callback de progression (SP-15g §3.5) : node_stats doit
    être visible en base dès qu'un nœud se termine, pas seulement au dernier
    commit de mark_succeeded/mark_failed. Prouvé en faisant échouer le run
    APRÈS que le callback ait déjà écrit un NodeStat — si l'écriture était
    différée à la fin, ce test ne verrait rien avant le statut 'failed'."""
    app, Session, tenant, user, item_id = env
    from app.pipelines.runtime import NodeStat

    def _fake_run_pipeline(session, *, on_node_complete, **kwargs):
        on_node_complete(NodeStat("r1", "reader.collection", 5))
        raise ValueError("boom after first node")

    monkeypatch.setattr(pipeline_jobs, "run_pipeline", _fake_run_pipeline)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.node_stats == {
            "r1": {"nodeId": "r1", "op": "reader.collection", "rowCount": 5}
        }


def test_run_pipeline_task_marks_run_failed_on_unexpected_exception_never_zombie(env, monkeypatch):
    # Reproduit le cas relevé en revue de la Tâche 8 : run_pipeline() peut
    # lever une AssertionError "nue" (pas PipelineRuntimeError/ValueError) —
    # par ex. la branche writer.export si s3_client/exports_bucket sont None
    # (`assert s3_client is not None and exports_bucket is not None`,
    # app/pipelines/runtime.py). AssertionError est une sous-classe
    # d'Exception : le clause `except Exception` de run_pipeline_task doit
    # donc, elle aussi, marquer le run "failed" — jamais de zombie, même pour
    # une erreur totalement inattendue qui ne passe pas par le clause
    # (PipelineRuntimeError, ValueError) plus étroit.
    app, Session, tenant, user, item_id = env

    def _boom(*args, **kwargs):
        raise AssertionError("s3_client is not None and exports_bucket is not None")

    monkeypatch.setattr(pipeline_jobs, "run_pipeline", _boom)

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error is not None


def test_run_pipeline_task_refuses_writer_dataset_without_data_manage(env, monkeypatch):
    # SP-42, revue de la dernière passe de correctifs (point 1, Critical) :
    # POST /pipelines/{id}/run et le tool MCP run_pipeline gardaient déjà
    # data.manage avant de déférer un pipeline writer.dataset — mais
    # run_pipeline_sweep_task (cron */5, app.pipelines.jobs) défère
    # run_pipeline_task directement, sans passer par AUCUNE des deux
    # routes gardées. Un propriétaire de pipeline dont le rôle ne porte pas
    # data.manage (ex. rétrogradé après la planification, ou un rôle sur
    # mesure automation.manage seul) voyait donc son pipeline continuer
    # d'écrire des configs "dataset" indéfiniment via le cron. La garde
    # doit vivre dans app.pipelines.runtime::_write_dataset — le point
    # d'écriture réel, commun aux TROIS entrées (REST, MCP, sweep) — pas
    # sur une quatrième route.
    app, Session, tenant, user, item_id = env

    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert "data.manage" not in roles["analyst"].privileges
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=user.id,
            role_id=roles["analyst"].id,
            role_slug="analyst",
        )
        s.commit()

    from app.configs.schemas import PipelinePayload

    dataset_payload = PipelinePayload.model_validate(
        {
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
                    "op": "writer.dataset",
                    "params": {"collectionId": "villes_propres", "title": "Sortie"},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )
    monkeypatch.setattr(
        pipeline_jobs, "_get_pipeline_payload", lambda session, item_id: dataset_payload
    )

    with Session() as s:
        run = pipelines_repo.create_run(s, tenant_id=tenant.id, pipeline_item_id=item_id)
        s.commit()
        run_id = run.id

    pipeline_jobs.run_pipeline_task.defer(run_id=run_id, tenant_id=tenant.id)
    app.run_worker(wait=False, queues=["etl"])

    with Session() as s:
        fetched = pipelines_repo.get_run(s, tenant_id=tenant.id, run_id=run_id)
        assert fetched.status == "failed"
        assert fetched.error is not None and "data.manage" in fetched.error
        # Jamais de dataset créé, jamais de ligne écrite dans la collection
        # cible : la garde doit s'exécuter avant TOUTE écriture (même
        # patron que _write_dataset, qui appelle _write_collection AVANT de
        # créer/muter l'item dataset).
        count = s.execute(text("SELECT count(*) FROM villes_propres")).scalar()
        assert count == 0
        from app.items.models import Item

        dataset_items = (
            s.execute(
                select(Item).where(Item.tenant_id == tenant.id, Item.resource_type == "dataset")
            )
            .scalars()
            .all()
        )
        assert dataset_items == []
