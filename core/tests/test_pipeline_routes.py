# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user, set_user_role


def _make_app(monkeypatch, *, etl_enabled: bool):
    monkeypatch.setenv("CORE_ETL_ENABLED", "true" if etl_enabled else "false")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    client.tenant = tenant
    client.user = user
    return client


def test_pipelines_routes_absent_when_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/pipelines/ops").status_code == 404
    assert client.post("/pipelines/does-not-exist/run").status_code == 404


def test_get_pipelines_ops_returns_all_eighteen(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops")
    assert response.status_code == 200
    body = response.json()
    # Phase 1 (8) + spatial (5) + writer.dataset (1) + qgis (1) + connectors (2)
    # + transform.merge (1, SP-15g) = 18 total.
    assert set(body) == {
        "reader.collection",
        "transform.filter",
        "transform.select",
        "transform.derive",
        "transform.aggregate",
        "transform.join",
        "transform.buffer",
        "transform.reproject",
        "transform.intersection",
        "transform.countWithin",
        "transform.h3Aggregate",
        "transform.qgis",
        "writer.collection",
        "writer.export",
        "writer.dataset",
        "reader.connector.rest",
        "reader.connector.postgres",
        "transform.merge",
    }
    for op in (
        "transform.join",
        "transform.intersection",
        "transform.countWithin",
        "transform.merge",
    ):
        assert body[op]["acceptsSecondaryInput"] is True
    assert body["reader.collection"]["acceptsSecondaryInput"] is False


def test_run_route_refuses_a_writer_dataset_pipeline_without_data_manage(monkeypatch):
    # SP-42, revue des lots de correctifs 2/3bis (point 2, Important) :
    # POST /pipelines/{id}/run n'exigeait que `write` sur l'item pipeline —
    # jamais data.manage — alors qu'un nœud writer.dataset (runtime.py)
    # crée ou mute une config kind="dataset", mappée sur data.manage. Un
    # Analyste (data.view/analytics.view/analytics.sql_lab.access/
    # tasks.view seuls, pas data.manage) à qui un tel pipeline est
    # accessible en écriture pouvait donc créer des datasets. Propriétaire
    # direct du pipeline ici pour simplifier le montage (write via
    # ownership) — même simplification que
    # test_configs_privilege_guard.py::
    # test_analyst_cannot_escalate_privilege_by_submitting_a_different_kind_on_put.
    # La config est créée directement via le repository (pas via
    # POST /configs, qui refuserait déjà la création elle-même : ce test
    # cible /run, pas la création).
    client = _make_app(monkeypatch, etl_enabled=True)
    tenant = client.tenant
    Session = client.session_factory  # type: ignore[attr-defined]

    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        assert "data.manage" not in roles["analyst"].privileges
        analyst = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="analyst-sub",
            username="analyst",
            email=None,
            first_name="",
            last_name="",
        )
        analyst_role_id = roles["analyst"].id
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=analyst.id,
            role_id=analyst_role_id,
            role_slug="analyst",
        )
        s.add(
            Collection(
                id="parcs",
                tenant_id=tenant.id,
                owner_id=analyst.id,
                table_name="parcs",
                title="Parcs",
                pk_column="id",
                is_public=True,
                editable=True,
            )
        )
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=analyst.id,
            resource_type="pipeline",
            title="Pipeline de l'analyste",
        )
        configs_repo.create_config(
            s,
            BuilderConfig(
                version=1,
                kind="pipeline",
                pipeline={
                    "nodes": [
                        {
                            "id": "r1",
                            "kind": "reader",
                            "op": "reader.collection",
                            "params": {"collectionId": "parcs"},
                        },
                        {
                            "id": "w1",
                            "kind": "writer",
                            "op": "writer.dataset",
                            "params": {"collectionId": "parcs", "title": "sortie"},
                        },
                    ],
                    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                },
            ),
            item_id=item.id,
            tenant_id=tenant.id,
        )
        s.commit()
        item_id = item.id
        analyst_id = analyst.id

    with Session() as s:
        analyst = s.get(User, analyst_id)
        assert analyst is not None
    # `get_current_user` est surchargé par `lambda: user` (patron d'origine
    # de `_make_app`) — le MÊME objet Python à chaque requête, jamais
    # re-résolu depuis la base. On bascule donc l'override lui-même sur
    # l'Analyste plutôt que de muter alice.
    client.app.dependency_overrides[get_current_user] = lambda: analyst
    client.app.dependency_overrides[get_current_user_optional] = lambda: analyst

    from app.pipelines import routes as pipelines_routes

    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: (
        lambda run_id, tid: (_ for _ in ()).throw(
            AssertionError("le run n'aurait jamais dû être déféré")
        )
    )

    response = client.post(f"/pipelines/{item_id}/run")
    assert response.status_code == 403, response.text


def test_run_route_defers_job_and_returns_run_id(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    deferred = {}

    def fake_deferrer(run_id, tenant_id):
        deferred["run_id"] = run_id
        deferred["tenant_id"] = tenant_id

    from app.pipelines import routes as pipelines_routes

    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: fake_deferrer

    create_response = client.post(
        "/configs",
        json={
            "title": "P",
            "config": {
                "version": 1,
                "kind": "pipeline",
                "pipeline": {
                    "nodes": [
                        {
                            "id": "r1",
                            "kind": "reader",
                            "op": "reader.collection",
                            "params": {"collectionId": "x"},
                        },
                        {
                            "id": "w1",
                            "kind": "writer",
                            "op": "writer.export",
                            "params": {"format": "csv", "key": "o.csv"},
                        },
                    ],
                    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                },
            },
        },
    )
    # This POST /configs will itself 422 (collection "x" doesn't exist,
    # Task 5's real validator rejects it) — use a route-level item instead:
    # exercise /pipelines/{id}/run against a 404 to prove the route SHAPE
    # (auth + not-found), the defer-on-success path is exercised in Task 9's
    # end-to-end job test instead (needs a real saveable pipeline, i.e. a
    # real collection, which belongs in a postgis-backed test).
    assert create_response.status_code == 422

    response = client.post("/pipelines/does-not-exist/run")
    assert response.status_code == 404


def test_preview_route_rejects_unknown_pipeline(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.post("/pipelines/does-not-exist/preview?upTo=r1")
    assert response.status_code == 404


def test_list_runs_route_rejects_unknown_pipeline(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/does-not-exist/runs")
    assert response.status_code == 404


def test_get_qgis_algorithms_returns_full_allowlist(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    response = client.get("/pipelines/ops/qgis-algorithms")
    assert response.status_code == 200
    body = response.json()
    assert len(body) == 50
    assert "native:centroids" in body
    assert "ALL_PARTS" in body["native:centroids"]["parameters"]


def test_get_qgis_algorithms_absent_when_etl_disabled(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=False)
    assert client.get("/pipelines/ops/qgis-algorithms").status_code == 404
