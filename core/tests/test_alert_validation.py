# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _client_and_user(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'alert_validation.db'}"
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
        # directly through the repository in tests below.
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="mock-sub",
            username="mockuser",
            email=None,
            first_name="Mock",
            last_name="User",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, tenant, user, Session


def _alert_body(dataset_item_id: str, *, query: dict | None = None) -> dict:
    return {
        "title": "High counts",
        "config": {
            "kind": "alert",
            "alert": {
                "datasetItemId": dataset_item_id,
                "query": query or {"agg": "count"},
                "condition": {"expr": "value > 100"},
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        },
    }


def test_create_alert_rule_rejects_a_nonexistent_dataset(monkeypatch, tmp_path):
    client, *_ = _client_and_user(monkeypatch, tmp_path)
    resp = client.post("/v1/configs", json=_alert_body("does-not-exist"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dataset not found"


def test_create_alert_rule_rejects_a_non_dataset_item(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="pipeline",
            title="Not a dataset",
        )
        s.commit()
        other_item_id = item.id
    resp = client.post("/v1/configs", json=_alert_body(other_item_id))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "dataset not found"


def test_create_alert_rule_succeeds_against_a_readable_dataset(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="My dataset",
        )
        s.commit()
        dataset_item_id = item.id
    resp = client.post("/v1/configs", json=_alert_body(dataset_item_id))
    assert resp.status_code == 201
    assert resp.json()["kind"] == "alert"


def test_create_alert_rule_rejects_a_percentile_query_without_p(monkeypatch, tmp_path):
    """Sans validation de `p` à la sauvegarde, la règle s'enregistre puis
    échoue à chaque tick de son cron, pour toujours (revue finale SP-23, I4)."""
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    with Session() as s:
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            resource_type="dataset",
            title="My dataset",
        )
        s.commit()
        dataset_item_id = item.id

    resp = client.post(
        "/v1/configs",
        json=_alert_body(dataset_item_id, query={"agg": "percentile", "field": "amount"}),
    )
    assert resp.status_code == 422

    resp = client.post(
        "/v1/configs",
        json=_alert_body(
            dataset_item_id,
            query={"measures": [{"agg": "percentile", "field": "amount", "label": "value"}]},
        ),
    )
    assert resp.status_code == 422

    # Le même agrégat avec un `p` valide reste acceptable.
    resp = client.post(
        "/v1/configs",
        json=_alert_body(dataset_item_id, query={"agg": "percentile", "field": "amount", "p": 90}),
    )
    assert resp.status_code == 201
