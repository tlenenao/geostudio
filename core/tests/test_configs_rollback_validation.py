# SPDX-License-Identifier: Apache-2.0
"""SP-23, chantier 4.18 : `POST /configs/{id}/rollback` doit revalider la
config restaurée avec exactement la même séquence que `update_config`, avant
d'écrire la version N+1. Patron de fixture copié de `tests/test_routes.py`
(client + dependency_overrides), body d'alerte copié de
`tests/test_alert_validation.py`."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.items.models import Item
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.user = user  # type: ignore[attr-defined]
    test_client.tenant = tenant  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _create_dataset_item(client) -> str:
    with client.session_factory() as s:
        item = items_repo.create_item(
            s,
            tenant_id=client.tenant.id,
            owner_id=client.user.id,
            resource_type="dataset",
            title="My dataset",
        )
        s.commit()
        return item.id


def _alert_body(dataset_item_id: str) -> dict:
    return {
        "title": "High counts",
        "config": {
            "kind": "alert",
            "alert": {
                "datasetItemId": dataset_item_id,
                "query": {"agg": "count"},
                "condition": {"expr": "value > 100"},
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        },
    }


def test_rollback_to_a_version_referencing_a_deleted_dataset_is_rejected(client):
    dataset_item_id = _create_dataset_item(client)
    created = client.post("/v1/configs", json=_alert_body(dataset_item_id)).json()
    assert created["version"] == 1

    # v2 : toujours valide, référence le même dataset.
    update = client.put(f"/v1/configs/{created['id']}", json=_alert_body(dataset_item_id)["config"])
    assert update.status_code == 200
    assert update.json()["version"] == 2

    # Le dataset référencé par v1 (et v2) disparaît.
    with client.session_factory() as s:
        s.execute(delete(Item).where(Item.id == dataset_item_id))
        s.commit()

    rollback = client.post(f"/v1/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 422
    assert "dataset not found" in rollback.json()["detail"]

    # Aucune version n'a été écrite.
    fetched = client.get(f"/v1/configs/{created['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["version"] == 2


def test_rollback_to_a_still_valid_version_succeeds_and_bumps_version(client):
    dataset_item_id = _create_dataset_item(client)
    created = client.post("/v1/configs", json=_alert_body(dataset_item_id)).json()

    update = client.put(f"/v1/configs/{created['id']}", json=_alert_body(dataset_item_id)["config"])
    assert update.status_code == 200
    assert update.json()["version"] == 2

    rollback = client.post(f"/v1/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 200
    assert rollback.json()["version"] == 3

    fetched = client.get(f"/v1/configs/{created['id']}")
    assert fetched.json()["version"] == 3
