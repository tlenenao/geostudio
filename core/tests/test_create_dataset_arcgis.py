# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
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
        alice = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        bob = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-2",
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            last_name="Doe",
        )
        source = harvest_repo.create_source(
            setup_session,
            tenant_id=tenant.id,
            owner_id=alice.id,
            type="arcgis",
            url="https://gis.example.com/FeatureServer",
            mode="reference",
            enabled=True,
            interval_minutes=None,
        )
        visible_item = items_repo.create_item(
            setup_session,
            tenant_id=tenant.id,
            owner_id=alice.id,
            resource_type="external",
            title="Bâtiments",
        )
        harvest_repo.create_record(
            setup_session,
            tenant_id=tenant.id,
            source_id=source.id,
            external_id="layer-0",
            item_id=visible_item.id,
            collection_id=None,
            content_hash=None,
            external_url="https://gis.example.com/FeatureServer/0",
            layer_kind="feature",
        )
        hidden_item = items_repo.create_item(
            setup_session,
            tenant_id=tenant.id,
            owner_id=bob.id,
            resource_type="external",
            title="Couche privée de Bob",
        )
        harvest_repo.create_record(
            setup_session,
            tenant_id=tenant.id,
            source_id=source.id,
            external_id="layer-1",
            item_id=hidden_item.id,
            collection_id=None,
            content_hash=None,
            external_url="https://gis.example.com/FeatureServer/1",
            layer_kind="feature",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice

    test_client = TestClient(app)
    test_client.visible_item_id = visible_item.id  # type: ignore[attr-defined]
    test_client.hidden_item_id = hidden_item.id  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _dataset_body(arcgis_item_id: str, title: str = "Bâtiments (live)") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1,
            "kind": "dataset",
            "dataset": {"source": "arcgis", "arcgisItemId": arcgis_item_id, "columns": {}},
        },
    }


def test_create_dataset_arcgis_avec_couche_moissonnee_visible(client):
    res = client.post("/v1/configs", json=_dataset_body(client.visible_item_id))
    assert res.status_code == 201, res.text
    item = client.get(f"/v1/items/{res.json()['itemId']}").json()
    assert item["resourceType"] == "dataset"


def test_create_dataset_arcgis_item_inexistant_rejete(client):
    res = client.post("/v1/configs", json=_dataset_body("no-such-item"))
    assert res.status_code == 422
    assert res.json()["detail"] == "arcgis layer not found"


def test_create_dataset_arcgis_couche_non_lisible_rejete_avec_meme_message(client):
    # visible_item appartient à alice, hidden_item à bob (non public, non
    # partagé) : alice ne doit pas pouvoir distinguer "inexistant" de "pas à
    # elle" dans le message d'erreur.
    res = client.post("/v1/configs", json=_dataset_body(client.hidden_item_id))
    assert res.status_code == 422
    assert res.json()["detail"] == "arcgis layer not found"
