# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.harvest import repository as harvest_repo
from app.items import repository as items_repo
from app.main import create_app
from app.users.repository import get_or_create_user


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.delenv("CORE_READ_ONLY_MODE", raising=False)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        from app.tenants.repository import get_or_create_default_tenant

        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


class _Seed:
    pass


@pytest.fixture()
def seed(env):
    app, client, Session, admin, regular = env
    seed = _Seed()
    seed.app = app
    seed.client = client

    with Session() as s:
        source = harvest_repo.create_source(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            type="wms",
            url="https://ows.example.com/wms",
            mode="reference",
            enabled=True,
            interval_minutes=None,
        )

        # (a) item raster visible : possédé par admin, tiles_url non-null.
        visible_item = items_repo.create_item(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            resource_type="external",
            title="Ortho visible",
        )
        harvest_repo.create_record(
            s,
            tenant_id=admin.tenant_id,
            source_id=source.id,
            external_id="a",
            item_id=visible_item.id,
            collection_id=None,
            content_hash=None,
            tiles_url="https://ows.example.com/wms?layer=ortho",
            layer_kind="raster",
        )
        seed.visible_raster_item_id = visible_item.id

        # (b) record "feature" (référence WFS) sans tiles_url : exclu par tiles_url IS NULL.
        feature_item = items_repo.create_item(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            resource_type="external",
            title="Couche vecteur",
        )
        harvest_repo.create_record(
            s,
            tenant_id=admin.tenant_id,
            source_id=source.id,
            external_id="b",
            item_id=feature_item.id,
            collection_id=None,
            content_hash=None,
            tiles_url=None,
            layer_kind="feature",
        )
        seed.feature_item_id = feature_item.id

        # (c) item raster caché : possédé par regular, non publié/non public
        # (valeurs par défaut du modèle) → can(read) refuse l'accès à admin.
        hidden_item = items_repo.create_item(
            s,
            tenant_id=admin.tenant_id,
            owner_id=regular.id,
            resource_type="external",
            title="Ortho cachée",
        )
        harvest_repo.create_record(
            s,
            tenant_id=admin.tenant_id,
            source_id=source.id,
            external_id="c",
            item_id=hidden_item.id,
            collection_id=None,
            content_hash=None,
            tiles_url="https://ows.example.com/wms?hidden",
            layer_kind="raster",
        )
        seed.hidden_raster_item_id = hidden_item.id

        s.commit()

    _as(app, admin)
    return seed


def test_layers_returns_only_raster_records_of_visible_items(seed):
    resp = seed.client.get("/harvest/layers")
    assert resp.status_code == 200
    layers = resp.json()["layers"]
    ids = {layer["id"] for layer in layers}
    assert seed.visible_raster_item_id in ids
    assert seed.feature_item_id not in ids
    assert seed.hidden_raster_item_id not in ids
    layer = next(layer for layer in layers if layer["id"] == seed.visible_raster_item_id)
    assert layer["kind"] == "raster"
    assert layer["tilesUrl"].startswith("https://ows.example.com/")


def test_layers_filters_by_q(seed):
    resp = seed.client.get("/harvest/layers", params={"q": "zzz-nomatch"})
    assert resp.status_code == 200
    assert resp.json()["layers"] == []
