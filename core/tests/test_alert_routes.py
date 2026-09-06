# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _setup(monkeypatch, tmp_path, *, extra_evaluations: int = 0):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'alert_routes.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        # app.auth.dependency.get_current_user's mock-mode branch always
        # resolves to this fixed identity (oidc_sub="mock-sub",
        # username="mockuser"), ignoring the bearer token's content beyond
        # the "Bearer " prefix — so the acting user for real HTTP requests
        # must be created with this exact oidc_sub for ownership checks
        # (app.sharing.authorization.can) to line up with items created
        # directly through the repository below (same idiom as
        # test_alert_validation.py).
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
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="Dataset",
        )
        rule_item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="alert",
            title="High counts",
        )
        config = BuilderConfig.model_validate(
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
        )
        configs_repo.create_config(s, config, item_id=rule_item.id, tenant_id=tenant.id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant.id, alert_rule_item_id=rule_item.id
        )
        alerts_repo.mark_evaluated(
            s, evaluation_id=evaluation.id, value=150.0, state="firing", transitioned=True
        )
        for _ in range(extra_evaluations):
            alerts_repo.create_evaluation(s, tenant_id=tenant.id, alert_rule_item_id=rule_item.id)
        s.commit()
        dataset_item_id, rule_item_id = dataset_item.id, rule_item.id
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, dataset_item_id, rule_item_id


def test_list_alerts_for_dataset_returns_the_rule(monkeypatch, tmp_path):
    client, dataset_item_id, rule_item_id = _setup(monkeypatch, tmp_path)
    resp = client.get(f"/datasets/{dataset_item_id}/alerts")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["itemId"] == rule_item_id
    assert body[0]["title"] == "High counts"


def test_list_alerts_for_dataset_is_empty_for_an_unrelated_dataset(monkeypatch, tmp_path):
    client, _dataset_item_id, _rule_item_id = _setup(monkeypatch, tmp_path)
    resp = client.get("/datasets/unrelated-id/alerts")
    assert resp.status_code == 200
    assert resp.json() == []


def test_get_alert_evaluations_returns_history_most_recent_first(monkeypatch, tmp_path):
    client, _dataset_item_id, rule_item_id = _setup(monkeypatch, tmp_path)
    resp = client.get(f"/alerts/{rule_item_id}/evaluations")
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 1
    assert body[0]["state"] == "firing"
    assert body[0]["value"] == 150.0


def test_get_alert_evaluations_accepts_limit_and_offset(monkeypatch, tmp_path):
    client, _dataset_item_id, rule_item_id = _setup(monkeypatch, tmp_path, extra_evaluations=4)
    resp = client.get(f"/alerts/{rule_item_id}/evaluations?limit=2&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 2

    resp2 = client.get(f"/alerts/{rule_item_id}/evaluations?limit=2&offset=4")
    assert len(resp2.json()) == 1


def test_get_alert_evaluations_404s_for_an_unknown_rule(monkeypatch, tmp_path):
    client, *_ = _setup(monkeypatch, tmp_path)
    resp = client.get("/alerts/does-not-exist/evaluations")
    assert resp.status_code == 404
