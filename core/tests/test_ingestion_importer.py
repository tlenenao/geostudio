"""Bout en bout sur PostGIS réel : run_import seul (table + collection + item
carte), sans procrastinate ni S3 — même infra que test_features_integration.py."""
import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.db import Base, make_session_factory
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

GEOJSON = (
    b'{"type":"FeatureCollection","features":['
    b'{"type":"Feature","properties":{"nom":"A","population":100},'
    b'"geometry":{"type":"Point","coordinates":[1.0,45.0]}},'
    b'{"type":"Feature","properties":{"nom":"B","population":200},'
    b'"geometry":{"type":"Point","coordinates":[2.0,46.0]}}]}'
)


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def test_geojson_import_creates_queryable_collection_and_map_item(env):
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.geojson",
            content=GEOJSON, collection_title="Villes", lat_field=None, lon_field=None,
        )
        s.commit()
        config = configs_repo.get_config_by_item(s, item_id=result.item_id)
        assert config is not None
        assert config.config.kind == "map"
        assert len(config.config.map.layers) == 1
        assert result.collection_id in config.config.map.layers[0].url

    with Session() as s:
        rows = s.execute(
            text(f"SELECT nom, population FROM public.{result.collection_id} ORDER BY nom")
        ).all()
        assert [tuple(r) for r in rows] == [("A", 100), ("B", 200)]


def test_csv_import_with_auto_detected_lat_lon(env):
    Session, tenant, user = env
    csv_content = b"nom,lat,lon\nParis,48.85,2.35\nLyon,45.76,4.83\n"
    with Session() as s:
        result = run_import(
            s, tenant_id=tenant.id, created_by=user.id, filename="villes.csv",
            content=csv_content, collection_title="Villes CSV",
            lat_field=None, lon_field=None,
        )
        s.commit()
        assert result.collection_id is not None
        assert result.item_id is not None


def test_corrupted_geojson_raises_without_creating_anything(env):
    Session, tenant, user = env
    with Session() as s:
        with pytest.raises(IngestionParseError):
            run_import(
                s, tenant_id=tenant.id, created_by=user.id, filename="broken.geojson",
                content=b"not json", collection_title="Casse",
                lat_field=None, lon_field=None,
            )
        s.rollback()
    with Session() as s:
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, is_admin=True
        )
        assert cols == []
