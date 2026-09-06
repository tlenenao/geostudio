# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app.alerts import repository as alerts_repo
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_mcp_tools_create import call_tool, call_tool_expecting_error


@pytest.fixture()
def app_client(monkeypatch, tmp_path):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")
    db_url = f"sqlite+pysqlite:///{tmp_path / 'test.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        mock_user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        setup_session.commit()
        tenant_id, user_id = tenant.id, mock_user.id

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    from app.db import get_session

    app.dependency_overrides[get_session] = override_session
    client = TestClient(app, base_url="http://localhost:8200")
    return client, Session, tenant_id, user_id


def _seed_alert_rule(Session, *, tenant_id, owner_id, expr="value > 100"):
    with Session() as s:
        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant_id,
            owner_id=owner_id,
            resource_type="dataset",
            title="Dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant_id)

        alert_item = items_repo.create_item(
            s,
            tenant_id=tenant_id,
            owner_id=owner_id,
            resource_type="alert",
            title="Trop d'incidents",
        )
        alert_config = BuilderConfig.model_validate(
            {
                "kind": "alert",
                "alert": {
                    "datasetItemId": dataset_item.id,
                    "query": {"agg": "count"},
                    "condition": {"expr": expr},
                    "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                    "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                },
            }
        )
        configs_repo.create_config(s, alert_config, item_id=alert_item.id, tenant_id=tenant_id)
        evaluation = alerts_repo.create_evaluation(
            s, tenant_id=tenant_id, alert_rule_item_id=alert_item.id
        )
        alerts_repo.mark_evaluated(
            s, evaluation_id=evaluation.id, value=150.0, state="firing", transitioned=True
        )
        s.commit()
        return alert_item.id, dataset_item.id


def test_explain_alert_rule_returns_the_rule_shape(app_client):
    client, Session, tenant_id, user_id = app_client
    alert_item_id, dataset_item_id = _seed_alert_rule(
        Session, tenant_id=tenant_id, owner_id=user_id
    )

    with client:
        result = call_tool(client, "explain_alert_rule", {"alertRuleId": alert_item_id})

    assert result["datasetItemId"] == dataset_item_id
    assert result["condition"] == "value > 100"
    assert result["currentState"] == "firing"
    assert result["channels"] == ["webhook"]


def test_explain_alert_rule_404s_for_an_unreadable_rule(app_client):
    client, Session, tenant_id, user_id = app_client
    with client:
        error_text = call_tool_expecting_error(
            client, "explain_alert_rule", {"alertRuleId": "does-not-exist"}
        )
    assert "alert rule not found" in error_text


def _seed_dataset(Session, *, tenant_id, owner_id):
    with Session() as s:
        dataset_item = items_repo.create_item(
            s,
            tenant_id=tenant_id,
            owner_id=owner_id,
            resource_type="dataset",
            title="Dataset",
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(s, dataset_config, item_id=dataset_item.id, tenant_id=tenant_id)
        s.commit()
        return dataset_item.id


def test_create_alert_rule_creates_a_config_kind_alert(app_client):
    client, Session, tenant_id, user_id = app_client
    dataset_item_id = _seed_dataset(Session, tenant_id=tenant_id, owner_id=user_id)

    with client:
        result = call_tool(
            client,
            "create_alert_rule",
            {
                "title": "R1",
                "datasetItemId": dataset_item_id,
                "query": {"agg": "count"},
                "condition": {"expr": "value > 10"},
                "refreshPolicy": {"enabled": True, "cron": "*/15 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
                "messageTemplate": "Alert {ruleName}: value={value} ({state})",
            },
        )

    assert result["resourceType"] == "alert"
    with Session() as s:
        config = configs_repo.get_config_by_item(s, result["pk"])
        assert config is not None
        assert config.config.kind == "alert"
        assert config.config.alert.datasetItemId == dataset_item_id


def test_create_alert_rule_refuses_in_read_only_mode(app_client, monkeypatch):
    client, Session, tenant_id, user_id = app_client
    dataset_item_id = _seed_dataset(Session, tenant_id=tenant_id, owner_id=user_id)
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")

    with client:
        error_text = call_tool_expecting_error(
            client,
            "create_alert_rule",
            {
                "title": "R1",
                "datasetItemId": dataset_item_id,
                "query": {"agg": "count"},
                "condition": {"expr": "value > 10"},
                "refreshPolicy": {"enabled": True, "cron": "*/15 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        )
    assert "lecture seule" in error_text


def test_run_alert_rule_creates_a_pending_evaluation_and_defers(app_client, monkeypatch):
    client, Session, tenant_id, user_id = app_client
    alert_item_id, _dataset_item_id = _seed_alert_rule(
        Session, tenant_id=tenant_id, owner_id=user_id
    )

    from app.alerts import jobs as alerts_jobs

    deferred = []
    monkeypatch.setattr(
        alerts_jobs.evaluate_alert_task,
        "defer",
        lambda **kw: deferred.append(kw),
    )

    with client:
        result = call_tool(client, "run_alert_rule", {"alertRuleId": alert_item_id})

    assert "evaluationId" in result
    assert deferred == [{"evaluation_id": result["evaluationId"], "tenant_id": tenant_id}]
    with Session() as s:
        evaluation = alerts_repo.get_evaluation(
            s, tenant_id=tenant_id, evaluation_id=result["evaluationId"]
        )
        assert evaluation is not None
        assert evaluation.state == "pending"


def test_run_alert_rule_404s_for_an_unreadable_rule(app_client):
    client, Session, tenant_id, user_id = app_client
    with client:
        error_text = call_tool_expecting_error(
            client, "run_alert_rule", {"alertRuleId": "does-not-exist"}
        )
    assert "alert rule not found" in error_text
