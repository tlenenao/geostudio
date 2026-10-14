# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: E501
"""ARC-25 : widget « Analyse » — outils d'analyse spatiale = op de pipeline sur un dataset."""

import dataclasses
import time

import geopandas as gpd
import pytest
from fastapi.testclient import TestClient
from shapely.geometry import Point, box
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.main import create_app
from app.pipelines import analysis, runtime
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

VILLES = TableInfo(
    table_name="villes",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)
ZONES = TableInfo(
    table_name="zones",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Polygon",
    srid=4326,
    columns=[ColumnInfo(name="nom", type="string", required=True)],
)
INFOS = {"villes": VILLES, "zones": ZONES}


def fake_introspector(session, table_name):
    if table_name not in INFOS:
        raise TableNotFound(table_name)
    return INFOS[table_name]


def _write_partition(base_dir, *, tenant_id, collection_id, rows):
    d = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-10-12"
    d.mkdir(parents=True, exist_ok=True)
    gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326").to_parquet(d / "part-1.parquet")


def _ville(i, region, pop, x, y):
    return {
        "id": i,
        "region": region,
        "pop": pop,
        "_op": "insert",
        "_lsn": 1,
        "_ts": 1.0,
        "geometry": Point(x, y),
    }


@pytest.fixture()
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "x")
    monkeypatch.setenv("S3_SECRET_KEY", "y")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
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
        s.commit()
        tenant_id = tenant.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table, tenant_id=None: None
    )
    app.dependency_overrides[features_routes.get_analytics_base_uri] = lambda: str(tmp_path)
    # le runtime de pipeline introspecte lui-même la table (pg_catalog réel) : même substitut
    monkeypatch.setattr(
        runtime,
        "_table_info_for_collection",
        lambda session, table_name: dataclasses.replace(INFOS[table_name], table_name=table_name),
    )
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    client = TestClient(app)
    cols = {}
    for table in ("villes", "zones"):
        r = client.post("/v1/collections", json={"tableName": table})
        assert r.status_code == 201, r.text
        cols[table] = r.json()["id"]
    return app, client, tmp_path, tenant_id, cols


def _seed(env):
    _app, _client, tmp_path, tenant_id, cols = env
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=cols["villes"],
        rows=[
            _ville(1, "Nord", 10, 0.5, 0.5),
            _ville(2, "Sud", 5, 5.5, 5.5),
            _ville(3, "Nord", 7, 0.6, 0.4),
        ],
    )
    zones = [
        {
            "id": 1,
            "nom": "Z1",
            "_op": "insert",
            "_lsn": 1,
            "_ts": 1.0,
            "geometry": box(0, 0, 1, 1),
        }
    ]
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=cols["zones"], rows=zones)


def _post(env, body, source="villes"):
    _app, client, _p, _t, cols = env
    return client.post(f"/v1/collections/{cols[source]}/analysis", json=body)


# --- catalogue ---------------------------------------------------------------------------------------


def test_catalog_has_8_to_12_tools_each_with_schema_help_and_a_real_pipeline_op():
    from app.pipelines.ops.contracts import OPERATIONS

    tools = analysis.tool_catalog()
    assert 8 <= len(tools) <= 12
    for t in tools:
        assert t["help"] and t["label"]
        assert t["paramsSchema"]["type"] == "object"
    # aucune nouvelle op : chaque outil est une op existante du registre OperationContract
    assert all(tool.op in OPERATIONS for tool in analysis.TOOLS.values())


def test_catalog_route(env):
    _app, client, *_ = env
    r = client.get("/v1/analysis/tools")
    assert r.status_code == 200
    assert {t["name"] for t in r.json()["tools"]} == {
        n for n, t in analysis.TOOLS.items() if t.enabled()
    }


# --- statistiques raster par zone (ARC-33 × ARC-25) ---------------------------------------------------


def _raster_item(env, tmp_path, monkeypatch):
    """Item raster lisible par l'admin + COG local (ouverture S3 remplacée)."""
    from contextlib import contextmanager

    import rasterio

    from app.items import repository as items_repo
    from app.pipelines.ops import raster as raster_op
    from app.raster.models import RasterAsset
    from tests.raster_fixtures import write_tif

    app, _client, _p, tenant_id, cols = env
    tif = str(tmp_path / "r.tif")
    write_tif(tif)

    @contextmanager
    def opener(asset):
        with rasterio.open(tif) as ds:
            yield ds

    monkeypatch.setattr(raster_op, "open_asset", opener)
    admin = app.dependency_overrides[get_current_user]()
    gen = app.dependency_overrides[db.get_session]()
    s = next(gen)
    item = items_repo.create_item(
        s, tenant_id=tenant_id, owner_id=admin.id, resource_type="raster", title="R"
    )
    s.add(
        RasterAsset(
            item_id=item.id,
            tenant_id=tenant_id,
            source_key="k",
            srid=4326,
            bounds=[2.0, 48.36, 2.64, 49.0],
            width=64,
            height=64,
            dtype="float32",
            nodata=-9999.0,
            bands=[],
            size_bytes=1,
        )
    )
    s.commit()
    item_id = item.id
    gen.close()
    _write_partition(
        tmp_path,
        tenant_id=tenant_id,
        collection_id=cols["zones"],
        rows=[
            {
                "id": 1,
                "nom": "Z1",
                "_op": "insert",
                "_lsn": 1,
                "_ts": 1.0,
                "geometry": box(2.1, 48.7, 2.3, 48.9),
            }
        ],
    )
    return item_id


def test_zonal_stats_tool_hidden_and_refused_when_raster_is_off(env, monkeypatch):
    monkeypatch.delenv("CORE_RASTER_ENABLED", raising=False)
    assert "zonalStats" not in {t["name"] for t in analysis.tool_catalog()}
    r = _post(env, {"tool": "zonalStats", "params": {"rasterItemId": "x"}}, source="zones")
    assert r.status_code == 422


def test_zonal_stats_tool_runs_on_polygons(env, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    item_id = _raster_item(env, tmp_path, monkeypatch)
    assert "zonalStats" in {t["name"] for t in analysis.tool_catalog()}
    r = _post(
        env,
        {"tool": "zonalStats", "params": {"rasterItemId": item_id, "stats": ["count", "mean"]}},
        source="zones",
    )
    assert r.status_code == 200, r.text
    (feat,) = r.json()["featureCollection"]["features"]
    assert feat["properties"]["nom"] == "Z1"
    assert feat["properties"]["zonal_count"] == 400 and feat["properties"]["zonal_mean"] > 0


def test_zonal_stats_tool_refuses_an_unreadable_raster(env, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    _raster_item(env, tmp_path, monkeypatch)
    r = _post(env, {"tool": "zonalStats", "params": {"rasterItemId": "inconnu"}}, source="zones")
    assert r.status_code == 422 and "not found" in r.text


# --- sortie éphémère ---------------------------------------------------------------------------------


def test_buffer_ephemeral_returns_polygons(env):
    _seed(env)
    r = _post(env, {"tool": "buffer", "params": {"distance": 500}})
    assert r.status_code == 200, r.text
    body = r.json()
    feats = body["featureCollection"]["features"]
    assert len(feats) == 3 and body["truncated"] is False and body["srid"] == 4326
    assert {f["geometry"]["type"] for f in feats} == {"Polygon"}
    assert {f["properties"]["region"] for f in feats} == {"Nord", "Sud"}


def test_count_within_and_spatial_selection_use_the_other_collection(env):
    _seed(env)
    _app, _c, _p, _t, cols = env
    r = _post(env, {"tool": "countWithin", "otherCollectionId": cols["villes"]}, source="zones")
    assert r.status_code == 200, r.text
    (feat,) = r.json()["featureCollection"]["features"]
    assert feat["properties"]["count"] == 2  # 2 villes dans Z1
    r = _post(env, {"tool": "spatialJoin", "otherCollectionId": cols["zones"]})
    feats = r.json()["featureCollection"]["features"]
    assert sorted(f["properties"]["pop"] for f in feats) == [7, 10]


def test_dissolve_groups_and_keeps_only_group_fields(env):
    _seed(env)
    r = _post(env, {"tool": "dissolve", "params": {"groupBy": ["region"]}})
    assert r.status_code == 200, r.text
    feats = r.json()["featureCollection"]["features"]
    assert {f["properties"]["region"] for f in feats} == {"Nord", "Sud"}
    assert all(set(f["properties"]) == {"region"} for f in feats)


def test_limit_truncates(env):
    _seed(env)
    r = _post(env, {"tool": "centroid", "limit": 2})
    body = r.json()
    assert len(body["featureCollection"]["features"]) == 2 and body["truncated"] is True


def test_validation_errors_are_422_not_500(env):
    _seed(env)
    _app, _c, _p, _t, cols = env
    for body in (
        {"tool": "nope"},
        {"tool": "buffer", "params": {"distance": -1}},
        {"tool": "countWithin"},  # second jeu manquant
        {"tool": "buffer", "params": {"distance": 1}, "otherCollectionId": cols["zones"]},
        {"tool": "dissolve", "params": {"groupBy": ["inconnu"]}},
        {
            "tool": "countWithin",
            "otherCollectionId": cols["zones"],
            "params": {"countColumn": "pop; drop"},
        },
        {"tool": "buffer", "params": {"distance": 1}, "output": "collection"},  # sans title
    ):
        assert _post(env, body).status_code == 422, body


def test_masked_fields_are_never_readable_through_analysis(env, monkeypatch):
    """GAP-22 : même masquage que /aggregate — le champ n'est ni rendu ni utilisable pour regrouper."""
    _seed(env)
    monkeypatch.setattr(
        "app.pipelines.analysis_routes.masked_fields_for", lambda *a, **k: frozenset({"pop"})
    )
    monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset({"pop"}))
    r = _post(env, {"tool": "centroid"})
    assert r.status_code == 200, r.text
    props = [f["properties"] for f in r.json()["featureCollection"]["features"]]
    assert props and all("pop" not in p for p in props)
    assert _post(env, {"tool": "dissolve", "params": {"groupBy": ["pop"]}}).status_code == 422


def test_geo_limited_collection_is_refused_fail_closed(env):
    _seed(env)
    app, *_ = env
    app.dependency_overrides[get_request_geo_limits] = lambda: {"villes": [{"any": "limit"}]}
    r = _post(env, {"tool": "centroid"})
    assert r.status_code in (403, 422) and r.status_code != 200


def test_unreadable_collection_is_404(env):
    _seed(env)
    _app, client, *_ = env
    assert (
        client.post("/v1/collections/inconnue/analysis", json={"tool": "centroid"}).status_code
        == 404
    )


# --- bornes ------------------------------------------------------------------------------------------


def test_too_large_collection_is_refused(env, monkeypatch):
    _seed(env)
    monkeypatch.setenv("CORE_ANALYSIS_MAX_FEATURES", "5")
    app, client, _p, _t, cols = env
    # feature_count d'une collection enregistrée = None (SQLite) : on le pose comme le ferait le comptage PG
    Session = None
    for dep, fn in app.dependency_overrides.items():
        if dep is db.get_session:
            Session = fn
    gen = Session()
    session = next(gen)
    session.execute(
        text("UPDATE collections SET feature_count = 50 WHERE id = :i"), {"i": cols["villes"]}
    )
    session.commit()
    gen.close()
    r = _post(env, {"tool": "centroid"})
    assert r.status_code == 422 and "trop volumineuse" in r.text


def test_buffer_500m_on_10000_points_under_10s(env):
    """Critère d'acceptation ARC-25 n°1, MESURÉ (lac GeoParquet local, DuckDB réel)."""
    _app, _c, tmp_path, tenant_id, cols = env
    import numpy as np

    rng = np.random.default_rng(1)
    xs, ys = rng.uniform(-5, 9, 10_000), rng.uniform(41, 51, 10_000)
    rows = [
        _ville(i, "R", i, float(x), float(y)) for i, (x, y) in enumerate(zip(xs, ys, strict=True))
    ]
    _write_partition(tmp_path, tenant_id=tenant_id, collection_id=cols["villes"], rows=rows)
    t0 = time.perf_counter()
    r = _post(env, {"tool": "buffer", "params": {"distance": 500}, "limit": 5000})
    elapsed = time.perf_counter() - t0
    print(f"\nARC-25 buffer 500 m x 10000 points : {elapsed:.2f} s")
    assert r.status_code == 200, r.text
    assert len(r.json()["featureCollection"]["features"]) == 5000 and r.json()["truncated"] is True
    assert elapsed < 10


# --- sortie collection (PostGIS réel) ----------------------------------------------------------------


@pytest.mark.postgis
def test_output_collection_creates_a_writable_collection_with_rows(
    pg_engine, monkeypatch, tmp_path
):
    from app.collections.ddl import apply_collection_ddl
    from app.collections.introspection_pg import introspect_table
    from app.collections.provisioning import create_empty_collection
    from app.collections.schemas import EmptyCollectionColumn
    from app.db import Base

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
            bootstrap_admin=True,
        )
        src = create_empty_collection(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            title="Villes",
            columns=[
                EmptyCollectionColumn(name="region", sqlType="text"),
                EmptyCollectionColumn(name="pop", sqlType="integer"),
            ],
            geometry_type="Point",
            srid=4326,
            introspect=introspect_table,
            apply_ddl=apply_collection_ddl,
        )
        s.commit()
        _write_partition(
            tmp_path,
            tenant_id=tenant.id,
            collection_id=src.id,
            rows=[_ville(1, "Nord", 10, 0.5, 0.5), _ville(2, "Sud", 5, 5.5, 5.5)],
        )
        out = analysis.run_analysis(
            s,
            user=user,
            source=src,
            other=None,
            req=analysis.AnalysisRequest(
                tool="buffer", params={"distance": 500}, output="collection", title="Tampons"
            ),
            introspect=introspect_table,
            masked_source=frozenset(),
            masked_other=frozenset(),
            endpoint_url="http://localhost:9000",
            access_key="x",
            secret_key="y",
            base_uri=str(tmp_path),
            apply_ddl=apply_collection_ddl,
        )
        s.commit()
        assert out["rowCount"] == 2 and out["srid"] == 4326
        table = s.execute(
            text("SELECT table_name, feature_count FROM collections WHERE id = :i"),
            {"i": out["collectionId"]},
        ).one()
        assert table.feature_count == 2
        n, gtypes = s.execute(
            text(
                f"SELECT count(*), array_agg(DISTINCT ST_GeometryType(geom)) FROM {table.table_name}"
            )
        ).one()
        assert n == 2 and gtypes == ["ST_MultiPolygon"]
        audit = s.execute(
            text("SELECT count(*) FROM audit_log WHERE action = 'analysis.run' AND object_id = :i"),
            {"i": out["collectionId"]},
        ).scalar()
        assert audit == 1
        # un lecteur sans data.manage ne peut pas créer de collection de sortie
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        from app.roles.repository import ensure_built_in_roles
        from app.users.repository import set_user_role

        reader_role = ensure_built_in_roles(s, tenant_id=tenant.id)["reader"]
        reader = set_user_role(
            s, tenant_id=tenant.id, user_id=reader.id, role_id=reader_role.id, role_slug="reader"
        )
        from fastapi import HTTPException

        with pytest.raises(HTTPException) as exc:
            analysis.run_analysis(
                s,
                user=reader,
                source=src,
                other=None,
                req=analysis.AnalysisRequest(tool="centroid", output="collection", title="Centres"),
                introspect=introspect_table,
                masked_source=frozenset(),
                masked_other=frozenset(),
                endpoint_url="http://localhost:9000",
                access_key="x",
                secret_key="y",
                base_uri=str(tmp_path),
                apply_ddl=apply_collection_ddl,
            )
        assert exc.value.status_code in (401, 403)
        s.rollback()
    with pg_engine.begin() as conn:
        for (t,) in conn.execute(text("SELECT table_name FROM collections")).all():
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
            )
        )
