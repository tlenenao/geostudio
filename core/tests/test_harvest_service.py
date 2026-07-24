# SPDX-License-Identifier: Apache-2.0
from unittest.mock import Mock

import pytest
from sqlalchemy import text

from app.db import Base, init_db, make_engine, make_session_factory
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.base import HarvestedRecord
from app.harvest.models import HarvestRecord
from app.ingestion.importer import ImportResult
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
RASTER_REC = HarvestedRecord(
    external_id="wms#topp:states", title="USA", abstract="", keywords=[],
    bbox=[-124.7, 24.9, -66.9, 49.4],
    external_url="https://ows.example.com/wms?request=GetCapabilities",
    items_url=None,
    raster_tiles_url="https://ows.example.com/wms?service=WMS&request=GetMap&layers=topp:states&bbox={bbox-epsg-3857}",
)
METADATA_ONLY_REC = HarvestedRecord(
    external_id="csw#iso-1", title="Batiments", abstract="", keywords=[],
    bbox=[-180.0, -90.0, 180.0, 90.0],
    external_url="https://geonetwork.example.com/csw?request=GetRecordById&id=iso-1",
    items_url=None,
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


def _fake_connector(records, *, copy_bytes=None, copy_error=None):
    connector = Mock()
    connector.fetch = Mock(return_value=records)
    if copy_error is not None:
        connector.fetch_copy_geojson = Mock(side_effect=copy_error)
    else:
        connector.fetch_copy_geojson = Mock(return_value=copy_bytes)
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


def test_reference_persists_tiles_url_and_layer_kind(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RASTER_REC]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="wms",
        url="https://ows.example.com/wms", mode="reference", enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="wms#topp:states")
    assert rec.tiles_url == RASTER_REC.raster_tiles_url
    assert rec.layer_kind == "raster"
    assert rec.external_url == RASTER_REC.external_url


def test_reference_metadata_only_record_has_null_tiles_and_layer_kind(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([METADATA_ONLY_REC]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="csw",
        url="https://geonetwork.example.com/csw", mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(session, tenant_id=tenant.id, source_id=source.id, external_id="csw#iso-1")
    assert rec.tiles_url is None
    assert rec.layer_kind is None


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


def test_copy_mode_fetch_copy_failure_sets_error_status_without_raising(session, tenant_and_user, monkeypatch):
    # En mode copy, connector.fetch_copy_geojson est appelé DANS la boucle
    # par-enregistrement, pas dans le bloc try du fetch initial. Échoue avant
    # tout run_import → toujours SQLite (jamais postgis-gated).
    tenant, user = tenant_and_user
    monkeypatch.setattr(
        service, "get_connector",
        lambda t: _fake_connector([RECORD_A], copy_error=RuntimeError("network boom")),
    )
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    assert "network boom" in source.last_error
    count = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0


def test_reference_mode_internal_url_is_blocked_by_egress_guard(session, tenant_and_user):
    # Pas de monkeypatch de get_connector : le vrai StacConnector construit son
    # client gardé (Task 1/2). L'URL vise le loopback → EgressBlockedError levée
    # par le transport AVANT toute connexion, propagée jusqu'au moteur → error.
    tenant, user = tenant_and_user
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="http://127.0.0.1:9/collections", mode="reference",
        enabled=True, interval_minutes=None,
    )
    session.commit()
    service.harvest_source(session, source)  # ne doit pas lever
    assert source.last_status == "error"
    count = session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0


def test_loop_poisoned_transaction_is_rolled_back_before_error_status(session, tenant_and_user, monkeypatch):
    # Reproduit le zombie visé par le fix de revue finale : si l'exception
    # sortant de la boucle par-enregistrement empoisonne la transaction
    # SQLAlchemy (échec réel au flush, ex. IntegrityError — pas une simple
    # exception Python), l'ancien code faisait directement
    # `source.last_status = "error"; session.flush()` sur une transaction
    # déjà invalidée : ce flush lève à son tour (PendingRollbackError), la
    # source reste bloquée au statut "running" committé par mark_running.
    tenant, user = tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    harvest_repo.mark_running(session, tenant_id=tenant.id, source_id=source.id)
    session.commit()  # comme jobs.run_harvest_task : "running" est committé avant harvest_source

    def poison_create_record(sess, **kwargs):
        # Insère un HarvestRecord sans ses colonnes NOT NULL : provoque une
        # vraie IntegrityError au flush(), qui empoisonne la transaction
        # SQLAlchemy exactement comme le ferait un IntegrityError de
        # production (ex. contrainte unique heurtée par une exécution
        # concurrente, ou un échec DB à l'intérieur de run_import).
        sess.add(HarvestRecord(id="poison"))
        sess.flush()

    monkeypatch.setattr(harvest_repo, "create_record", poison_create_record)

    service.harvest_source(session, source)  # ne doit pas lever

    reloaded = harvest_repo.get_source(session, tenant_id=tenant.id, source_id=source.id)
    assert reloaded is not None
    assert reloaded.last_status == "error"
    assert "NOT NULL" in reloaded.last_error


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
    monkeypatch.setattr(
        service, "get_connector",
        lambda t: _fake_connector([RECORD_A], copy_bytes=GEOJSON_ITEMS),
    )
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)

    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id="buildings")
    assert rec.collection_id is not None
    assert rec.item_id is not None


@pytest.mark.postgis
def test_copy_mode_reharvest_does_not_reimport(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    connector = _fake_connector([RECORD_A], copy_bytes=GEOJSON_ITEMS)
    monkeypatch.setattr(service, "get_connector", lambda t: connector)
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)
    service.harvest_source(pg_session, source)

    assert connector.fetch_copy_geojson.call_count == 1  # jamais ré-importé
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1


@pytest.mark.postgis
def test_loop_real_integrity_error_is_rolled_back_before_error_status(pg_session, pg_tenant_and_user, monkeypatch):
    # Version la plus forte du test SQLite ci-dessus (test_loop_poisoned_
    # transaction_is_rolled_back_before_error_status) : reproduit une VRAIE
    # IntegrityError Postgres, exactement la race documentée dans le
    # commentaire de _upsert_reference (« contrainte unique heurtée par une
    # exécution concurrente ») — une autre exécution a déjà inséré le
    # HarvestRecord entre notre get_record() et notre create_record(),
    # heurtant la contrainte unique réelle uq_harvest_records_tenant_source_
    # external. Contrairement à SQLite, Postgres abandonne réellement la
    # transaction entière jusqu'à ROLLBACK : c'est le cas d'empoisonnement
    # authentique que le fix de revue finale (session.rollback() avant de
    # réécrire le statut d'erreur) vise à couvrir.
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _fake_connector([RECORD_A]))
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="reference", enabled=True, interval_minutes=None,
    )
    harvest_repo.mark_running(pg_session, tenant_id=tenant.id, source_id=source.id)
    # Simule la course : un enregistrement portant déjà le même external_id
    # existe en base (comme si une autre exécution venait de l'insérer),
    # mais get_record() sera forcé à ne pas le voir.
    harvest_repo.create_record(
        pg_session, tenant_id=tenant.id, source_id=source.id, external_id=RECORD_A.external_id,
        item_id=None, collection_id=None, content_hash="already-there",
    )
    pg_session.commit()  # comme jobs.run_harvest_task : "running" est committé avant harvest_source

    monkeypatch.setattr(harvest_repo, "get_record", lambda *a, **kw: None)

    service.harvest_source(pg_session, source)  # ne doit pas lever

    reloaded = harvest_repo.get_source(pg_session, tenant_id=tenant.id, source_id=source.id)
    assert reloaded is not None
    assert reloaded.last_status == "error"
    assert reloaded.last_status != "running"


def test_upsert_copy_passes_copy_filename_to_run_import(session, tenant_and_user, monkeypatch):
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c1", item_id="i1"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    monkeypatch.setattr(harvest_repo, "create_record", Mock())
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="ckan",
        url="https://data.example.com", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    rec = HarvestedRecord(
        external_id="pkg-1", title="Sentiers", abstract="", keywords=[], bbox=[0, 0, 1, 1],
        external_url="https://data.example.com/dataset/pkg-1",
        items_url="https://data.example.com/dataset/pkg-1/resource/x.gpkg",
        copy_filename="harvest.gpkg",
    )
    connector = _fake_connector([rec], copy_bytes=b"gpkg-bytes")
    service._upsert_copy(
        session, source, rec, existing=None, digest="d1", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.gpkg"


def test_upsert_copy_defaults_filename_when_copy_filename_is_none(session, tenant_and_user, monkeypatch):
    # Régression : STAC/ArcGIS ne renseignent jamais copy_filename (défaut
    # None) — le littéral "harvest.geojson" doit rester inchangé pour eux.
    tenant, user = tenant_and_user
    fake_run_import = Mock(return_value=ImportResult(collection_id="c2", item_id="i2"))
    monkeypatch.setattr(service, "run_import", fake_run_import)
    monkeypatch.setattr(harvest_repo, "create_record", Mock())
    source = harvest_repo.create_source(
        session, tenant_id=tenant.id, owner_id=user.id, type="stac",
        url="https://a", mode="copy", enabled=True, interval_minutes=None,
    )
    session.commit()
    connector = _fake_connector([RECORD_A], copy_bytes=b"geojson-bytes")
    service._upsert_copy(
        session, source, RECORD_A, existing=None, digest="d2", connector=connector, http_get=lambda u: None,
    )
    assert fake_run_import.call_args.kwargs["filename"] == "harvest.geojson"
