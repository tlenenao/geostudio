# SPDX-License-Identifier: Apache-2.0
import httpx
import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.collections.ddl import quote_ident
from app.db import Base, make_session_factory
from app.harvest import repository as harvest_repo
from app.harvest import service
from app.harvest.connectors.arcgis import ArcgisConnector
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

SERVICE = "https://gis.example.com/arcgis/rest/services/Foo/FeatureServer"
SERVICE_META = {"layers": [{"id": 0, "name": "Bâtiments"}], "documentInfo": {"Keywords": "bati"}}
LAYER_0 = {"id": 0, "name": "Bâtiments", "description": "Empreintes", "extent": None}


def _fc(features, *, exceeded=False):
    return {"type": "FeatureCollection", "features": features, "exceededTransferLimit": exceeded}


def _feature(i):
    return {"type": "Feature", "properties": {"n": i}, "geometry": {"type": "Point", "coordinates": [float(i), float(i)]}}


def _arcgis_handler(request: httpx.Request) -> httpx.Response:
    # Handler unique partagé par le client du connecteur (fetch() des
    # métadonnées) ET par le http_get injecté pour fetch_copy_geojson() —
    # les deux doivent servir exactement les mêmes routes fictives, sinon la
    # pagination en mode copy (qui NE passe PAS par le client du connecteur,
    # cf. rapport de tâche : http_get est un paramètre séparé de
    # service.harvest_source, découplé de ArcgisConnector._client) tape le
    # vrai réseau au lieu du double de test.
    url = str(request.url)
    base = url.split("?")[0]
    if base == SERVICE:
        return httpx.Response(200, json=SERVICE_META)
    if base == f"{SERVICE}/0":
        return httpx.Response(200, json=LAYER_0)
    if base == f"{SERVICE}/0/query":
        if "resultOffset=0" in url:
            return httpx.Response(200, json=_fc([_feature(0), _feature(1)], exceeded=True))
        return httpx.Response(200, json=_fc([_feature(2)], exceeded=False))
    return httpx.Response(404)


def _arcgis_connector():
    return ArcgisConnector(client=httpx.Client(transport=httpx.MockTransport(_arcgis_handler)))


def _arcgis_http_get():
    """http_get de test pour service.harvest_source(..., http_get=...) — sert
    les pages de copie ArcGIS via le MÊME handler que _arcgis_connector(),
    au lieu du guarded_get réel (qui tenterait une vraie résolution DNS de
    gis.example.com)."""
    client = httpx.Client(transport=httpx.MockTransport(_arcgis_handler))
    return lambda url: client.get(url)


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
def test_arcgis_reference_creates_external_items_and_reharvest_no_duplicate(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _arcgis_connector())
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="arcgis",
        url=SERVICE, mode="reference", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source)
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id=f"{SERVICE}/0")
    assert rec is not None and rec.item_id is not None

    service.harvest_source(pg_session, source)  # re-moissonnage
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 1


@pytest.mark.postgis
def test_arcgis_copy_creates_local_collection_with_full_paginated_geojson(pg_session, pg_tenant_and_user, monkeypatch):
    tenant, user = pg_tenant_and_user
    monkeypatch.setattr(service, "get_connector", lambda t: _arcgis_connector())
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type="arcgis",
        url=SERVICE, mode="copy", enabled=True, interval_minutes=None,
    )
    service.harvest_source(pg_session, source, http_get=_arcgis_http_get())
    assert source.last_status == "ok"
    rec = harvest_repo.get_record(pg_session, tenant_id=tenant.id, source_id=source.id, external_id=f"{SERVICE}/0")
    assert rec.collection_id is not None
    # 3 entités sur 2 pages → 3 lignes dans la collection PostGIS locale.
    n = pg_session.execute(text('SELECT COUNT(*) FROM items')).scalar()  # au moins l'item carte
    assert n >= 1
    # Preuve bout-en-bout, plus forte que n>=1 : la collection PostGIS créée
    # par run_import contient bien les 3 entités des 2 pages GeoJSON servies
    # par le mock (2 sur la première page exceededTransferLimit=true, 1 sur
    # la seconde exceededTransferLimit=false) — pas seulement "au moins 1".
    collection = collections_repo.get_collection(pg_session, tenant_id=tenant.id, collection_id=rec.collection_id)
    assert collection is not None
    table = quote_ident(pg_session, collection.table_name)
    feature_count = pg_session.execute(text(f"SELECT COUNT(*) FROM public.{table}")).scalar()
    assert feature_count == 3


@pytest.mark.postgis
@pytest.mark.parametrize("source_type", ["stac", "arcgis"])
def test_internal_url_blocked_by_shared_egress_guard(pg_session, pg_tenant_and_user, source_type):
    # Pas de monkeypatch : le vrai connecteur construit son client gardé.
    tenant, user = pg_tenant_and_user
    source = harvest_repo.create_source(
        pg_session, tenant_id=tenant.id, owner_id=user.id, type=source_type,
        url="http://169.254.169.254/latest/meta-data/", mode="reference",
        enabled=True, interval_minutes=None,
    )
    pg_session.commit()
    service.harvest_source(pg_session, source)  # ne doit pas lever
    assert source.last_status == "error"
    count = pg_session.execute(text("SELECT COUNT(*) FROM harvest_records")).scalar()
    assert count == 0
