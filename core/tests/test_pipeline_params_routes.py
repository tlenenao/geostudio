# SPDX-License-Identifier: Apache-2.0
"""ARC-K2/F3 : paramètres de run au niveau REST/webhook (sqlite, sans exécution)."""

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.pipelines import routes as pipelines_routes
from tests.test_pipeline_routes import _make_app, _promote_owner_to_admin


def _seed(client, parameters):
    Session = client.session_factory
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=client.tenant.id,
            owner_id=client.user.id,
            resource_type="pipeline",
            title="P",
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "version": 1,
                    "kind": "pipeline",
                    "pipeline": {
                        "parameters": parameters,
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
                                "params": {"format": "csv", "key": "o-{{param.suffix}}.csv"},
                            },
                        ],
                        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
                    },
                }
            ),
            item_id=item.id,
            tenant_id=client.tenant.id,
        )
        s.commit()
        return item.id


_PARAMS = [{"name": "suffix", "type": "string", "required": True}]


def test_run_with_missing_required_param_is_422_and_defers_nothing(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed(client, _PARAMS)
    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: (
        lambda *_: (_ for _ in ()).throw(AssertionError("deferred"))
    )
    r = client.post(f"/v1/pipelines/{item_id}/run")
    assert r.status_code == 422
    assert "suffix" in r.text
    r = client.post(f"/v1/pipelines/{item_id}/run", json={"params": {"suffix": 3}})
    assert r.status_code == 422  # mal typé
    r = client.post(f"/v1/pipelines/{item_id}/run", json={"params": {"nope": "x"}})
    assert r.status_code == 422  # non déclaré


def test_run_historizes_params(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed(client, _PARAMS)
    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: lambda *_: None
    r = client.post(f"/v1/pipelines/{item_id}/run", json={"params": {"suffix": "a'b"}})
    assert r.status_code == 202, r.text
    runs = client.get(f"/v1/pipelines/{item_id}/runs").json()
    assert runs[0]["params"] == {"suffix": "a'b"}


def test_trigger_webhook_accepts_params(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed(client, _PARAMS)
    _promote_owner_to_admin(client)
    token = client.post(f"/v1/pipelines/{item_id}/webhook-tokens").json()["token"]
    client.app.dependency_overrides[pipelines_routes.get_task_deferrer] = lambda: lambda *_: None
    h = {"Authorization": f"Bearer {token}"}
    assert client.post(f"/v1/pipelines/{item_id}/trigger", headers=h).status_code == 422
    r = client.post(f"/v1/pipelines/{item_id}/trigger", headers=h, json={"params": {"suffix": "z"}})
    assert r.status_code == 202, r.text
    assert client.get(f"/v1/pipelines/{item_id}/runs").json()[0]["params"] == {"suffix": "z"}


def test_reader_state_routes_list_and_reset(monkeypatch):
    from app.pipelines import repository as pipelines_repo

    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed(client, _PARAMS)
    with client.session_factory() as s:
        pipelines_repo.upsert_reader_states(
            s,
            tenant_id=client.tenant.id,
            pipeline_item_id=item_id,
            cursors={"r1": "5", "r2": "7"},
        )
        s.commit()
    assert client.get(f"/v1/pipelines/{item_id}/reader-state").json() == [
        {"nodeId": "r1", "cursor": "5"},
        {"nodeId": "r2", "cursor": "7"},
    ]
    assert client.delete(f"/v1/pipelines/{item_id}/reader-state?nodeId=r1").status_code == 204
    states = client.get(f"/v1/pipelines/{item_id}/reader-state").json()
    assert [e["nodeId"] for e in states] == ["r2"]
    assert client.delete(f"/v1/pipelines/{item_id}/reader-state").status_code == 204
    assert client.get(f"/v1/pipelines/{item_id}/reader-state").json() == []
