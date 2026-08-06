# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.configs import pipeline_validation as pipeline_validation_module
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _linear_pipeline(**overrides) -> dict:
    body = {
        "title": "Nettoyer villes",
        "config": {
            "version": 1,
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {"id": "r1", "kind": "reader", "op": "reader.collection",
                     "params": {"collectionId": "villes"}},
                    {"id": "w1", "kind": "writer", "op": "writer.collection",
                     "params": {"collectionId": "villes_propres"}},
                ],
                "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
            },
        },
    }
    body.update(overrides)
    return body


@pytest.fixture()
def env(monkeypatch):
    # Fake validators, isolating THIS task's structural (cycle/edge-count)
    # logic from Task 5's real op-catalog/collection checks. Using
    # monkeypatch.setitem (not a direct register_pipeline_node_validator
    # call) matters: _node_validators is a module-level global dict with no
    # reset between tests — a direct call here would permanently overwrite
    # whatever app.pipelines.config_validation registered at import time
    # (Task 5), and that overwrite would leak into test_pipeline_node_validation.py's
    # tests if this file happens to run first in the same pytest session
    # (it does, alphabetically: "config_validation" < "node_validation").
    # monkeypatch.setitem restores the previous value automatically at
    # teardown, so this file can never leak state into another test file
    # regardless of execution order.
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "reader.collection",
        lambda session, node, user: None,
    )
    monkeypatch.setitem(
        pipeline_validation_module._node_validators, "writer.collection",
        lambda session, node, user: None,
    )

    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    return TestClient(app)


def test_valid_linear_pipeline_saves(env):
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 201


def test_disabled_capability_refuses_pipeline_creation(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json=_linear_pipeline())
    assert response.status_code == 403


def test_disabled_capability_does_not_affect_other_kinds(monkeypatch, env):
    monkeypatch.setenv("CORE_ETL_ENABLED", "false")
    response = env.post("/configs", json={
        "title": "App", "config": {"kind": "app", "layout": {"type": "grid", "items": []}},
    })
    assert response.status_code == 201


def test_cyclic_graph_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "1=1"}}
    )
    body["config"]["pipeline"]["edges"] = [
        {"id": "e1", "from": "r1", "to": "t1"},
        {"id": "e2", "from": "t1", "to": "w1"},
        {"id": "e3", "from": "w1", "to": "t1"},
    ]
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "acyclic" in response.json()["detail"]


def test_node_with_two_incoming_edges_rejected(env):
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append(
        {"id": "r2", "kind": "reader", "op": "reader.collection",
         "params": {"collectionId": "quartiers"}}
    )
    body["config"]["pipeline"]["edges"].append({"id": "e2", "from": "r2", "to": "w1"})
    response = env.post("/configs", json=body)
    assert response.status_code == 422
    assert "one incoming edge" in response.json()["detail"]


def test_reader_connector_node_saves_without_secret_or_query_check(env):
    # Design §6 : seule la FORME des params est vérifiée à la sauvegarde —
    # ni l'existence de "does-not-exist" comme secret, ni la validité SQL de
    # "not even sql" sont vérifiées ici (elles échoueraient proprement à
    # l'EXÉCUTION, cf. test_pipeline_runtime.py). Une sauvegarde réussie ici
    # n'est pas un bug.
    body = _linear_pipeline()
    body["config"]["pipeline"]["nodes"].append({
        "id": "r2", "kind": "reader", "op": "reader.connector.postgres",
        "params": {"secretName": "does-not-exist", "query": "not even sql"},
    })
    response = env.post("/configs", json=body)
    assert response.status_code == 201
