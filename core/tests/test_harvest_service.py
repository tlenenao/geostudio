# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.base import HarvestedRecord
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

RECORD_A = HarvestedRecord(
    external_id="buildings", title="Bâtiments", abstract="Empreintes",
    keywords=["bati"], bbox=[1.0, 45.0, 2.0, 46.0],
    external_url="https://stac.example.com/collections/buildings",
    items_url="https://stac.example.com/collections/buildings/items",
)
RECORD_B = HarvestedRecord(
    external_id="roads", title="Routes", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0],
    external_url="https://stac.example.com/collections/roads", items_url=None,
)


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


def _fake_connector(records):
    connector = Mock()
    connector.fetch = Mock(return_value=records)
    return connector


def test_reference_mode_first_harvest_creates_external_items(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(
        service, "get_connector", lambda t: _fake_connector([RECORD_A, RECORD_B]),
    )
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://stac.example.com/collections", mode="reference",
        enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)

    assert source.last_status == "ok"
    assert source.last_run_at is not None
    rec_a = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec_a is not None
    item = items_repo.get_item(session, tenant_id=tenant.id, item_id=rec_a.item_id)
    assert item.resourceType == "external"
    assert item.title == "Bâtiments"
    assert item.keywords == ["bati"]
    assert item.isPublished is False


def test_reference_mode_reharvest_updates_without_duplicating(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)
    first_item_id = harvest_repo.get_record(
        session, tenant_id=tenant.id, source_id=source.id, external_id="buildings"
    ).item_id

    updated = HarvestedRecord(
        external_id="buildings", title="Bâtiments (v2)", abstract="Empreintes",
        keywords=["bati"], bbox=RECORD_A.bbox, external_url=RECORD_A.external_url,
        items_url=RECORD_A.items_url,
    )
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([updated]))
    service.harvest_source(session, source)

    all_records = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert all_records == 1
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.item_id == first_item_id
    item = items_repo.get_item(session, tenant_id=tenant.id, item_id=first_item_id)
    assert item.title == "Bâtiments (v2)"


def test_missing_entity_is_marked_stale_not_deleted(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A, RECORD_B]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)

    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    service.harvest_source(session, source)

    stale = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="roads")
    assert stale.is_stale is True
    kept = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert kept.is_stale is False


def test_connector_fetch_failure_sets_error_status_without_raising(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user

    def _raise(t):
        connector = Mock()
        connector.fetch = Mock(side_effect=RuntimeError("boom"))
        return connector

    monkeypatch.setattr(service, "get_connector", _raise)
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    assert "boom" in source.last_error


GEOJSON_ITEMS = (
    b'{"type":"FeatureCollection","features":['
    b'{"type":"Feature","properties":{"nom":"A"},'
    b'"geometry":{"type":"Point","coordinates":[1.0,45.0]}}]}'
)


@pytest.fixture()
def pg_session(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        yield s
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE harvest_records, harvest_sources, items, configs, "
            "config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.fixture()
def pg_tenant_and_user(pg_session):
    tenant = get_or_create_default_tenant(pg_session)
    user = get_or_create_user(
        pg_session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


@pytest.mark.postgis
def test_copy_mode_first_harvest_creates_local_collection(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source, items_fetcher=lambda url: GEOJSON_ITEMS)

    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.collection_id is not None
    assert rec.item_id is not None


@pytest.mark.postgis
def test_copy_mode_reharvest_does_not_reimport(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    fetch_calls = []

    def counting_fetcher(url):
        fetch_calls.append(url)
        return GEOJSON_ITEMS

    service.harvest_source(pg_session, source, items_fetcher=counting_fetcher)
    service.harvest_source(pg_session, source, items_fetcher=counting_fetcher)

    assert len(fetch_calls) == 1
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1
