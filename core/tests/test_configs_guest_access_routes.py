# SPDX-License-Identifier: Apache-2.0
"""GET /configs/by-item/{item_id} accepte un jeton invité (GAP-19, Tâche 3) —
premier chemin HTTP de bout en bout prouvant qu'un GuestActor (app.configs.
guest_access, Tâche 1) peut lire un config sans Authorization, seulement via
X-Share-Link-Token. Patron `.pop()` réutilisé de
test_features_routes_read.py::test_anonymous_reads_public_only."""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as collections_repo
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

_SECRET = "test-configs-guest-access-secret-pad0"


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _SECRET)


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        # test_guest_token_for_a_non_app_dashboard_item_gets_404 crée un
        # config kind="dataset" référençant cette collection : le
        # validateur app.collections.dataset_validation exige qu'elle
        # existe réellement (get_collection), sinon POST /v1/configs
        # échoue en 422 avant même d'atteindre la route sous test — écart
        # trouvé par rapport au texte du brief, corrigé ici plutôt que
        # dans un fichier de config à part (patron
        # tests/test_dataset_source_pipeline_validation.py::_seed_collection).
        collections_repo.create_collection(
            s,
            tenant_id=tenant.id,
            owner_id=owner.id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: owner
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    client.tenant_id = tenant.id  # type: ignore[attr-defined]
    return app, client


def _create_app_config(client, *, data_sources):
    body = {
        "kind": "app",
        "dataSources": data_sources,
        "layout": {"type": "grid", "items": []},
    }
    created = client.post("/v1/configs", json={"title": "App", "config": body}).json()
    return created["itemId"]


def _create_link_token(client, item_id: str) -> str:
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    return created["url"].rsplit("/", 1)[-1]


def test_guest_token_grants_access_to_the_root_app_config(env):
    app, client = env
    item_id = _create_app_config(
        client,
        data_sources=[
            {
                "id": "ds1",
                "type": "features",
                "service": "core",
                "layer": "incidents",
                "query": {},
            },
        ],
    )
    token = _create_link_token(client, item_id)

    # Retire les overrides posés pour la préparation : la requête suivante
    # doit être traitée par le VRAI get_current_user_optional (aucune
    # Authorization envoyée, seul le header invité compte).
    app.dependency_overrides.pop(get_current_user)
    response = client.get(f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token})

    assert response.status_code == 200
    assert response.json()["itemId"] == item_id


def test_guest_token_for_a_non_app_dashboard_item_gets_404(env):
    app, client = env
    body = {
        "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
    }
    created = client.post("/v1/configs", json={"title": "D", "config": body}).json()
    item_id = created["itemId"]
    token = _create_link_token(client, item_id)

    app.dependency_overrides.pop(get_current_user)
    response = client.get(f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token})

    assert response.status_code == 404
    # La résolution publique de métadonnées, elle, continue de fonctionner :
    # inchangée par ce chantier.
    resolved = client.get(f"/v1/share-links/{token}")
    assert resolved.status_code == 200
    assert resolved.json()["itemId"] == item_id


def test_revoked_token_behaves_exactly_like_no_token(env):
    app, client = env
    item_id = _create_app_config(client, data_sources=[])
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    link_id = client.get(f"/v1/items/{item_id}/share-links").json()[0]["id"]
    client.delete(f"/v1/items/{item_id}/share-links/{link_id}")

    app.dependency_overrides.pop(get_current_user)
    with_token = client.get(f"/v1/configs/by-item/{item_id}", headers={"X-Share-Link-Token": token})
    without_token = client.get(f"/v1/configs/by-item/{item_id}")

    assert with_token.status_code == without_token.status_code == 404


def test_authenticated_user_unaffected_by_guest_wiring(env):
    app, client = env
    item_id = _create_app_config(client, data_sources=[])
    # Utilisateur réel, AUCUN jeton invité : le comportement doit être
    # strictement celui d'avant ce chantier.
    app.dependency_overrides[get_current_user_optional] = lambda: client.app.dependency_overrides[
        get_current_user
    ]()
    response = client.get(f"/v1/configs/by-item/{item_id}")
    assert response.status_code == 200
    assert response.json()["itemId"] == item_id
