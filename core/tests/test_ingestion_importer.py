# SPDX-License-Identifier: Apache-2.0
"""Bout en bout sur PostGIS réel : run_import seul (table + collection + item
carte), sans procrastinate ni S3 — même infra que test_features_integration.py."""

import numpy as np
import pytest
import shapely
from pyogrio.raw import write as pyogrio_write
from shapely.geometry import Point
from sqlalchemy import select, text

from app.audit.models import AuditLog
from app.collections import repository as collections_repo
from app.configs import repository as configs_repo
from app.db import Base, make_session_factory
from app.ingestion.importer import run_import
from app.ingestion.parsers import IngestionParseError
from app.tenants.models import Tenant
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
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def test_geojson_import_creates_queryable_collection_and_map_item(env):
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.geojson",
            content=GEOJSON,
            collection_title="Villes",
            lat_field=None,
            lon_field=None,
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
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.csv",
            content=csv_content,
            collection_title="Villes CSV",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        assert result.collection_id is not None
        assert result.item_id is not None


def test_import_stamps_real_tenant_id_on_inserted_rows(env):
    # Finding 1 (revue finale SP-6a) : apply_collection_ddl ajoute la colonne
    # tenant_id APRES l'INSERT (ADD COLUMN ... DEFAULT 'default') — sans le
    # correctif, les lignes importées valent 'default' quel que soit le
    # tenant réel, et deviennent invisibles sous RLS pour tout tenant dont
    # l'id n'est pas littéralement "default".
    Session, tenant, user = env
    with Session() as s:
        tenant_b = Tenant(id="tenant-b", slug="tenant-b", name="Tenant B")
        s.add(tenant_b)
        s.flush()
        user_b = get_or_create_user(
            s,
            tenant_id=tenant_b.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        tenant_b_id = tenant_b.id

    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant_b_id,
            created_by=user_b.id,
            filename="villes.geojson",
            content=GEOJSON,
            collection_title="Villes B",
            lat_field=None,
            lon_field=None,
        )
        s.commit()

    with Session() as s:
        # Requête directe (rôle propriétaire de la session de test, pas
        # gis_rls) : même contournement de RLS que le test existant
        # ci-dessus qui lit `public.{table}` sans SET ROLE.
        rows = (
            s.execute(text(f"SELECT DISTINCT tenant_id FROM public.{result.collection_id}"))
            .scalars()
            .all()
        )
        assert rows == [tenant_b_id]
        assert rows != ["default"]


def test_import_writes_audit_entries_for_collection_and_item(env):
    # Finding 2 (revue finale SP-6a) : seul "ingestion.job_create" était
    # audité (routes.py, au moment de l'upload) — la création réelle de la
    # collection et de l'item par le worker (run_import) ne laissait aucune
    # trace d'audit, contrairement au chemin admin manuel
    # (collections/routes.py::register_collection).
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.geojson",
            content=GEOJSON,
            collection_title="Villes Auditées",
            lat_field=None,
            lon_field=None,
        )
        s.commit()

    with Session() as s:
        col_entries = s.scalars(
            select(AuditLog).where(
                AuditLog.action == "collection.create",
                AuditLog.object_id == result.collection_id,
            )
        ).all()
        assert len(col_entries) == 1
        assert col_entries[0].actor_id == user.id
        assert col_entries[0].actor_kind == "user"

        item_entries = s.scalars(
            select(AuditLog).where(
                AuditLog.action == "item.create",
                AuditLog.object_id == result.item_id,
            )
        ).all()
        assert len(item_entries) == 1
        assert item_entries[0].actor_id == user.id
        assert item_entries[0].actor_kind == "user"


def test_corrupted_geojson_raises_without_creating_anything(env):
    Session, tenant, user = env
    with Session() as s:
        with pytest.raises(IngestionParseError):
            run_import(
                s,
                tenant_id=tenant.id,
                created_by=user.id,
                filename="broken.geojson",
                content=b"not json",
                collection_title="Casse",
                lat_field=None,
                lon_field=None,
            )
        s.rollback()
    with Session() as s:
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, can_see_all=True
        )
        assert cols == []


def _gpkg_bytes(tmp_path, *, layer="entites", crs="EPSG:4326", points=None):
    points = points or [(1.0, 45.0), (2.0, 46.0)]
    path = tmp_path / f"{layer}.gpkg"
    geometry = shapely.to_wkb(np.array([Point(x, y) for x, y in points], dtype=object))
    pyogrio_write(
        str(path),
        geometry=geometry,
        field_data=[np.array(["A", "B"][: len(points)], dtype=object)],
        fields=["nom"],
        layer=layer,
        geometry_type="Point",
        crs=crs,
    )
    return path.read_bytes()


def test_gpkg_import_creates_queryable_collection_and_map_item(env, tmp_path):
    Session, tenant, user = env
    content = _gpkg_bytes(tmp_path)
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.gpkg",
            content=content,
            collection_title="Villes GPKG",
            lat_field=None,
            lon_field=None,
            layer_name="entites",
        )
        s.commit()
    with Session() as s:
        rows = (
            s.execute(text(f"SELECT nom FROM public.{result.collection_id} ORDER BY nom"))
            .scalars()
            .all()
        )
        assert rows == ["A", "B"]


def test_gpkg_import_reprojects_non_wgs84_crs(env, tmp_path):
    import pyproj

    Session, tenant, user = env
    transformer = pyproj.Transformer.from_crs("EPSG:4326", "EPSG:2154", always_xy=True)
    x, y = transformer.transform(2.35, 48.85)
    content = _gpkg_bytes(tmp_path, crs="EPSG:2154", points=[(x, y)])
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="l93.gpkg",
            content=content,
            collection_title="Villes L93",
            lat_field=None,
            lon_field=None,
            layer_name="entites",
        )
        s.commit()
    with Session() as s:
        lon, lat = s.execute(
            text(f"SELECT ST_X(geom), ST_Y(geom) FROM public.{result.collection_id}")
        ).one()
        assert lon == pytest.approx(2.35, abs=1e-6)
        assert lat == pytest.approx(48.85, abs=1e-6)


def test_gpkg_import_requires_layer_name_when_multiple_layers(env, tmp_path):
    Session, tenant, user = env
    path = tmp_path / "multi.gpkg"
    geometry = shapely.to_wkb(np.array([Point(1.0, 1.0)], dtype=object))
    pyogrio_write(
        str(path),
        geometry=geometry,
        field_data=[np.array(["A"], dtype=object)],
        fields=["nom"],
        layer="a",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    pyogrio_write(
        str(path),
        geometry=geometry,
        field_data=[np.array(["B"], dtype=object)],
        fields=["nom"],
        layer="b",
        geometry_type="Point",
        crs="EPSG:4326",
    )
    content = path.read_bytes()
    with Session() as s:
        with pytest.raises(IngestionParseError):
            run_import(
                s,
                tenant_id=tenant.id,
                created_by=user.id,
                filename="multi.gpkg",
                content=content,
                collection_title="Multi",
                lat_field=None,
                lon_field=None,
                layer_name=None,
            )
        s.rollback()
    with Session() as s:
        cols = collections_repo.list_visible_collections(
            s, tenant_id=tenant.id, user_id=user.id, can_see_all=True
        )
        assert cols == []


def test_shapefile_zip_import_creates_queryable_collection(env, tmp_path):
    import zipfile

    Session, tenant, user = env
    shp_path = tmp_path / "villes.shp"
    geometry = shapely.to_wkb(np.array([Point(1.0, 45.0), Point(2.0, 46.0)], dtype=object))
    pyogrio_write(
        str(shp_path),
        geometry=geometry,
        field_data=[np.array(["A", "B"], dtype=object)],
        fields=["nom"],
        geometry_type="Point",
        crs="EPSG:4326",
    )
    zip_path = tmp_path / "villes.zip"
    with zipfile.ZipFile(zip_path, "w") as z:
        for ext in ("shp", "shx", "dbf", "prj", "cpg"):
            p = tmp_path / f"villes.{ext}"
            if p.exists():
                z.write(p, arcname=p.name)
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.zip",
            content=zip_path.read_bytes(),
            collection_title="Villes Shapefile",
            lat_field=None,
            lon_field=None,
            layer_name="villes",
        )
        s.commit()
    with Session() as s:
        rows = (
            s.execute(text(f"SELECT nom FROM public.{result.collection_id} ORDER BY nom"))
            .scalars()
            .all()
        )
        assert rows == ["A", "B"]


def test_geojson_import_stores_feature_count(env):
    Session, tenant, user = env
    with Session() as s:
        result = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename="villes.geojson",
            content=GEOJSON,
            collection_title="Villes",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
    with Session() as s:
        col = collections_repo.get_collection(
            s, tenant_id=tenant.id, collection_id=result.collection_id
        )
        assert col.feature_count == 2  # GEOJSON contient 2 features (A, B)
