# SPDX-License-Identifier: Apache-2.0
"""Tests de app.configs.guest_access (GAP-19, Tâche 1) : résolution de la
portée d'un jeton de lien de partage (SP-54) en GuestActor scopé — invariant
de sécurité central du chantier « embed SDK » : un jeton valide pour l'item
X ne doit jamais autoriser une collection non référencée par X, y compris
via une référence cross-tenant."""

import pytest

from app.configs import repository as configs_repo
from app.configs.guest_access import (
    GuestActor,
    authorize_guest_collection_read,
    authorize_guest_item_read,
    get_share_link_actor,
    resolve_guest_scope,
)
from app.configs.schemas import BuilderConfig
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.sharing import repository as sharing_repo
from app.sharing.share_links import ShareLinkTokenClaims, mint_share_link_token
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_data_source_accepts_a_dataset_id():
    config = BuilderConfig.model_validate(
        {
            "kind": "app",
            "dataSources": [
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "",
                    "datasetId": "item-dataset-1",
                    "query": {},
                }
            ],
            "layout": {"type": "grid", "items": []},
        }
    )
    assert config.dataSources[0].datasetId == "item-dataset-1"


def _guest(**overrides) -> GuestActor:
    defaults = dict(
        tenant_id="t1",
        item_id="app-1",
        share_link_id="link-1",
        created_by="sharer-1",
        allowed_item_ids=frozenset({"app-1"}),
        allowed_collection_ids=frozenset({"col-a"}),
    )
    defaults.update(overrides)
    return GuestActor(**defaults)


def test_authorize_guest_item_read_true_for_allowed_id():
    assert authorize_guest_item_read(_guest(), "app-1") is True


def test_authorize_guest_item_read_false_for_other_id():
    assert authorize_guest_item_read(_guest(), "app-2") is False


def test_authorize_guest_item_read_false_when_guest_is_none():
    assert authorize_guest_item_read(None, "app-1") is False


def test_authorize_guest_collection_read_true_for_allowed_id():
    assert authorize_guest_collection_read(_guest(), "col-a") is True


def test_authorize_guest_collection_read_false_for_other_id():
    assert authorize_guest_collection_read(_guest(), "col-b") is False


def test_authorize_guest_collection_read_false_when_guest_is_none():
    assert authorize_guest_collection_read(None, "col-a") is False


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _create_app_item(session, *, tenant_id, owner_id, data_sources):
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="app", title="App"
    )
    config = BuilderConfig.model_validate(
        {
            "kind": "app",
            "dataSources": data_sources,
            "layout": {"type": "grid", "items": []},
        }
    )
    configs_repo.create_config(session, config, item.id, tenant_id=tenant_id)
    session.commit()
    return item.id


def test_resolve_guest_scope_collects_direct_layer_references(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
            data_sources=[
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "incidents",
                    "query": {},
                },
                {
                    "id": "ds2",
                    "type": "static",
                    "service": "core",
                    "layer": "",
                    "query": {"records": []},
                },
            ],
        )
        claims = ShareLinkTokenClaims(
            share_link_id="link-1", tenant_id=tenant.id, item_id=app_item_id
        )

        guest = resolve_guest_scope(session, claims, created_by="sharer-1")

        assert guest is not None
        assert guest.allowed_item_ids == frozenset({app_item_id})
        assert guest.allowed_collection_ids == frozenset({"incidents"})


def test_resolve_guest_scope_returns_none_for_unknown_item(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        claims = ShareLinkTokenClaims(
            share_link_id="l", tenant_id=tenant.id, item_id="does-not-exist"
        )
        assert resolve_guest_scope(session, claims, created_by="sharer-1") is None


def test_resolve_guest_scope_returns_none_for_non_app_dashboard_kind(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "incidents", "columns": {}},
            }
        )
        configs_repo.create_config(session, config, item.id, tenant_id=tenant.id)
        session.commit()
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=item.id)
        assert resolve_guest_scope(session, claims, created_by="sharer-1") is None


def test_resolve_guest_scope_follows_dataset_id_to_its_collection(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        dataset_item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "communes", "columns": {}},
            }
        )
        configs_repo.create_config(session, dataset_config, dataset_item.id, tenant_id=tenant.id)
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
            data_sources=[
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "",
                    "datasetId": dataset_item.id,
                    "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims, created_by="sharer-1")

        assert guest is not None
        assert guest.allowed_item_ids == frozenset({app_item_id, dataset_item.id})
        assert guest.allowed_collection_ids == frozenset({"communes"})


def test_resolve_guest_scope_ignores_an_arcgis_dataset(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        dataset_item = items_repo.create_item(
            session, tenant_id=tenant.id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        dataset_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "arcgis", "arcgisItemId": "arcgis-1", "columns": {}},
            }
        )
        configs_repo.create_config(session, dataset_config, dataset_item.id, tenant_id=tenant.id)
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
            data_sources=[
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "",
                    "datasetId": dataset_item.id,
                    "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims, created_by="sharer-1")

        assert guest is not None
        # Le dataset ArcGIS est bien listé comme item lisible (résolution de
        # son itemClient.getDatasetConfig continuera de fonctionner), mais
        # n'ajoute AUCUNE collection : source arcgis, hors modèle collection.
        assert guest.allowed_item_ids == frozenset({app_item_id, dataset_item.id})
        assert guest.allowed_collection_ids == frozenset()


def test_resolve_guest_scope_rejects_a_dataset_id_from_another_tenant(session_factory):
    with session_factory() as session:
        tenant_a = get_or_create_default_tenant(session)
        owner_a = get_or_create_user(
            session,
            tenant_id=tenant_a.id,
            oidc_sub="oa",
            username="ownera",
            email=None,
            first_name="",
            last_name="",
        )
        # Pas de create_tenant() dans app.tenants.repository (piège CLAUDE.md
        # n°3 — le brief supposait cette fonction, elle n'existe pas) :
        # même patron que tests/test_compliance_purge_routes.py, insertion
        # directe du modèle ORM.
        tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        session.add(tenant_b)
        session.flush()
        owner_b = get_or_create_user(
            session,
            tenant_id=tenant_b.id,
            oidc_sub="ob",
            username="ownerb",
            email=None,
            first_name="",
            last_name="",
        )
        # Un dataset appartenant au tenant B, référençant une collection
        # privée du tenant B ("secret-b").
        foreign_dataset = items_repo.create_item(
            session,
            tenant_id=tenant_b.id,
            owner_id=owner_b.id,
            resource_type="dataset",
            title="D-B",
        )
        foreign_config = BuilderConfig.model_validate(
            {
                "kind": "dataset",
                "dataset": {"source": "collection", "collectionId": "secret-b", "columns": {}},
            }
        )
        configs_repo.create_config(
            session, foreign_config, foreign_dataset.id, tenant_id=tenant_b.id
        )
        # Une App du tenant A qui référence (par construction de test, comme
        # si un import/copier-coller malencontreux avait recopié un id) ce
        # dataset du tenant B via datasetId.
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant_a.id,
            owner_id=owner_a.id,
            data_sources=[
                {
                    "id": "ds1",
                    "type": "features",
                    "service": "core",
                    "layer": "",
                    "datasetId": foreign_dataset.id,
                    "query": {},
                },
            ],
        )
        claims = ShareLinkTokenClaims(share_link_id="l", tenant_id=tenant_a.id, item_id=app_item_id)

        guest = resolve_guest_scope(session, claims, created_by="sharer-1")

        assert guest is not None
        assert foreign_dataset.id not in guest.allowed_item_ids
        assert "secret-b" not in guest.allowed_collection_ids


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    # >=32 bytes, même contrainte que test_share_links_routes.py.
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", "test-guest-access-secret-padding0")


def test_get_share_link_actor_returns_none_without_a_header(session_factory):
    with session_factory() as session:
        assert get_share_link_actor(x_share_link_token=None, session=session) is None


def test_get_share_link_actor_returns_none_for_a_garbage_token(session_factory):
    with session_factory() as session:
        assert get_share_link_actor(x_share_link_token="not-a-jwt", session=session) is None


def test_get_share_link_actor_resolves_a_valid_token(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
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
        link = sharing_repo.create_share_link(
            session, tenant_id=tenant.id, item_id=app_item_id, created_by=owner.id, ttl_seconds=3600
        )
        session.commit()
        token = mint_share_link_token(
            share_link_id=link.id, tenant_id=tenant.id, item_id=app_item_id, ttl_seconds=3600
        )

        guest = get_share_link_actor(x_share_link_token=token, session=session)

        assert guest is not None
        assert guest.allowed_collection_ids == frozenset({"incidents"})


def test_get_share_link_actor_returns_none_for_a_revoked_link(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        app_item_id = _create_app_item(
            session,
            tenant_id=tenant.id,
            owner_id=owner.id,
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
        link = sharing_repo.create_share_link(
            session, tenant_id=tenant.id, item_id=app_item_id, created_by=owner.id, ttl_seconds=3600
        )
        session.commit()
        token = mint_share_link_token(
            share_link_id=link.id, tenant_id=tenant.id, item_id=app_item_id, ttl_seconds=3600
        )
        sharing_repo.revoke_share_link(session, tenant_id=tenant.id, link_id=link.id)
        session.commit()

        assert get_share_link_actor(x_share_link_token=token, session=session) is None
