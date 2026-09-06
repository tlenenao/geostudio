# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
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
        collection = Collection(
            id="parcs",
            tenant_id=tenant.id,
            owner_id=user.id,
            table_name="parcs",
            title="Parcs",
            pk_column="id",
            is_public=True,
            editable=True,
        )
        setup_session.add(collection)
        bob = get_or_create_user(
            setup_session,
            tenant_id=tenant.id,
            oidc_sub="sub-2",
            username="bob",
            email="bob@example.com",
            first_name="Bob",
            last_name="Doe",
        )
        private_collection = Collection(
            id="prives",
            tenant_id=tenant.id,
            owner_id=bob.id,
            table_name="prives",
            title="Privées",
            pk_column="id",
            is_public=False,
            editable=True,
        )
        setup_session.add(private_collection)
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _dataset_body(collection_id: str, title: str = "Parcs partagés") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1,
            "kind": "dataset",
            "dataset": {"source": "collection", "collectionId": collection_id, "columns": {}},
        },
    }


def test_create_dataset_avec_collection_existante(client):
    res = client.post("/v1/configs", json=_dataset_body("parcs"))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/v1/items/{item_id}").json()
    assert item["resourceType"] == "dataset"


def test_create_dataset_collection_inexistante_rejete(client):
    res = client.post("/v1/configs", json=_dataset_body("inexistante"))
    assert res.status_code == 422


def test_update_dataset_collection_inexistante_rejete(client):
    created = client.post("/v1/configs", json=_dataset_body("parcs"))
    item_id = created.json()["itemId"]
    bad_config = {
        "version": 1,
        "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": "inexistante", "columns": {}},
    }
    res = client.put(f"/v1/configs/by-item/{item_id}", json=bad_config)
    assert res.status_code == 422


def test_create_dataset_collection_non_lisible_rejete_avec_meme_message(client):
    # "prives" existe (owner = bob) mais alice (l'appelante) n'y a aucun accès :
    # ni owner, ni publique, ni rôle de groupe. Le message doit être identique
    # à celui de la collection inexistante, pour ne pas révéler son existence.
    res = client.post("/v1/configs", json=_dataset_body("prives"))
    assert res.status_code == 422
    assert res.json()["detail"] == "collection not found"
