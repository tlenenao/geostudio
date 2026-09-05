# SPDX-License-Identifier: Apache-2.0
# Fixture pattern copied from test_public_sites.py / test_public_routes.py —
# entirely SQLite, including the tenant-isolation leakage test (it only needs
# a second Tenant/User row, no Postgres-specific feature).
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as repo
from app.main import create_app
from app.tenants.models import Tenant
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
            email=None,
            first_name="",
            last_name="",
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
    yield test_client
    engine.dispose()


def _create_item(client, title: str, kind: str = "app") -> str:
    response = client.post(
        "/configs",
        json={"title": title, "config": {"kind": kind, "layout": {"type": "grid", "items": []}}},
    )
    assert response.status_code == 201, response.text
    return response.json()["itemId"]


def _publish(client, item_id: str) -> None:
    response = client.patch(f"/items/{item_id}", json={"isPublished": True})
    assert response.status_code == 200, response.text


def test_anonymous_can_list_published_items(client):
    item_id = _create_item(client, "Publie")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Publie"]


def test_unpublished_item_is_absent(client):
    _create_item(client, "Brouillon")

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    assert response.json()["items"] == []


def test_filters_by_type(client):
    app_id = _create_item(client, "Une app", kind="app")
    _publish(client, app_id)
    dash_id = _create_item(client, "Un dashboard", kind="dashboard")
    _publish(client, dash_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?type=dashboard")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Un dashboard"]


def test_filters_by_tag(client):
    tagged_id = _create_item(client, "Avec tag")
    client.patch(f"/items/{tagged_id}", json={"keywords": ["risques"]})
    _publish(client, tagged_id)
    untagged_id = _create_item(client, "Sans tag")
    _publish(client, untagged_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?tag=risques")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Avec tag"]


def test_paginates(client):
    for i in range(3):
        item_id = _create_item(client, f"Item {i}")
        _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?page=1&pageSize=2")
    assert response.status_code == 200
    body = response.json()
    assert body["total"] == 3
    assert len(body["items"]) == 2
    assert body["page"] == 1
    assert body["pageSize"] == 2


def test_page_zero_is_rejected_instead_of_silently_wrong(client):
    # Regression (SP-42, F-coeur-contenu-02): list_published_items pages by
    # Python slicing (rows[(page-1)*page_size : ...]) — page=0 gave a
    # negative start index instead of an error, returning silently wrong
    # (empty, here) results rather than a clear 422.
    for i in range(3):
        item_id = _create_item(client, f"Item {i}")
        _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?page=0&pageSize=2")
    assert response.status_code == 422


def test_page_size_zero_is_rejected(client):
    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items?pageSize=0")
    assert response.status_code == 422


def test_leakage_matrix_unpublished_other_tenant_and_default_published(client):
    # (1) Item non publié → absent.
    _create_item(client, "Non publie")

    # (2) Item publie d'un autre tenant → absent (aucun header/parametre de
    # tenant n'existe cote route publique ; seul le tenant "default" est
    # jamais servi).
    with client.session_factory() as session:
        other_tenant = Tenant(id="other", slug="other", name="Other")
        session.add(other_tenant)
        session.flush()
        bob = get_or_create_user(
            session,
            tenant_id="other",
            oidc_sub="sub-other",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        other_item = repo.create_item(
            session,
            tenant_id="other",
            owner_id=bob.id,
            resource_type="app",
            title="Autre tenant",
        )
        other_item.is_published = True
        session.commit()

    # (3) Item publie du tenant default → present.
    published_id = _create_item(client, "Publie default")
    _publish(client, published_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    assert response.status_code == 200
    titles = [i["title"] for i in response.json()["items"]]
    assert titles == ["Publie default"]


def test_never_exposes_a_sensitive_field(client):
    item_id = _create_item(client, "Publie")
    _publish(client, item_id)

    del client.app.dependency_overrides[get_current_user]
    response = client.get("/public/items")
    body = response.json()["items"][0]
    assert set(body.keys()) == {
        "pk",
        "resourceType",
        "slug",
        "title",
        "abstract",
        "owner",
        "thumbnailUrl",
        "date",
        # updatedAt (SP-42/F-shell-api-07) : même famille que `date`
        # (created_at) déjà whitelisté ci-dessus — un horodatage de
        # dernière modification n'est pas plus sensible qu'un horodatage de
        # création, et /public/items sert le même ItemRead que /items (pas
        # de projection publique séparée qui choisirait d'exclure l'un
        # plutôt que l'autre). Même décision que license/language (SP-41) :
        # métadonnée publique par conception.
        "updatedAt",
        "configId",
        "isPublished",
        "keywords",
        "permissions",
        # license/language (SP-41) : métadonnées publiques par conception,
        # pas des champs sensibles.
        "license",
        "language",
    }
