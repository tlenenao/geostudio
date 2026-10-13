# SPDX-License-Identifier: Apache-2.0
"""ARC-33 : routes raster (ingestion, proxy de tuiles, zonal-stats) sur SQLite + faux S3/TiTiler."""

from contextlib import contextmanager
from types import SimpleNamespace

import numpy as np
import pytest
import rasterio
from fastapi.testclient import TestClient
from pytest_httpserver import HTTPServer

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections.models import Collection
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.ingestion import routes as ingestion_routes
from app.items import repository as items_repo
from app.main import create_app
from app.raster import routes as raster_routes
from app.raster.models import RasterAsset
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user, set_user_role
from tests.raster_fixtures import write_tif

BUCKET = "geostudio-raster"


class _FakeS3:
    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"

    def head_object(self, Bucket, Key):  # noqa: N803
        return {"ContentLength": 10}

    def list_objects_v2(self, **kw):
        return {"Contents": [], "IsTruncated": False}


def _box(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


@pytest.fixture()
def env(monkeypatch, httpserver: HTTPServer, tmp_path):
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    tif = str(tmp_path / "a.tif")
    ref = write_tif(tif)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        users = {
            n: get_or_create_user(
                s,
                tenant_id=tenant.id,
                oidc_sub=n,
                username=n,
                email=None,
                first_name="",
                last_name="",
            )
            for n in ("alice", "bob")
        }
        item = items_repo.create_item(
            s,
            tenant_id=tenant.id,
            owner_id=users["alice"].id,
            resource_type="raster",
            title="Ortho",
        )
        other = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=users["alice"].id, resource_type="map", title="Carte"
        )
        s.add(
            RasterAsset(
                item_id=item.id,
                tenant_id=tenant.id,
                source_key=f"{tenant.id}/job/cog.tif",
                srid=4326,
                bounds=[2.0, 48.36, 2.64, 49.0],
                width=64,
                height=64,
                dtype="float32",
                nodata=-9999.0,
                bands=[{"index": 1, "min": 64.0, "max": 4095.0, "mean": 2000.0, "std": 1.0}],
                size_bytes=1,
            )
        )
        s.commit()
        ids = SimpleNamespace(raster=item.id, other=other.id, tenant=tenant.id)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    who = {"user": users["alice"]}
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: who["user"]
    app.dependency_overrides[get_current_user_optional] = lambda: who["user"]
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: _FakeS3()
    app.dependency_overrides[raster_routes.get_titiler_url] = lambda: httpserver.url_for("")
    deferred: list = []
    app.dependency_overrides[raster_routes.get_task_deferrer] = lambda: (
        lambda job_id, tenant_id: deferred.append((job_id, tenant_id))
    )

    @contextmanager
    def opener(asset):
        with rasterio.open(tif) as ds:
            yield ds

    app.dependency_overrides[raster_routes.get_raster_opener] = lambda: opener
    return SimpleNamespace(
        client=TestClient(app),
        app=app,
        Session=Session,
        ids=ids,
        users=users,
        who=who,
        ref=ref,
        httpserver=httpserver,
        deferred=deferred,
    )


# --- tuiles ---------------------------------------------------------------------


def test_tile_proxies_titiler_with_server_side_url_only(env):
    # `url` fourni par le client est ignoré ; seuls les paramètres de rendu validés passent.
    env.httpserver.expect_request(
        "/cog/tiles/5/10/12.png",
        query_string=(
            f"url=s3%3A%2F%2F{BUCKET}%2F{env.ids.tenant}%2Fjob%2Fcog.tif"
            "&rescale=0%2C4000&colormap_name=viridis"
        ),
    ).respond_with_data(b"\x89PNG-tile", content_type="image/png")
    r = env.client.get(
        f"/v1/raster/{env.ids.raster}/tiles/5/10/12",
        params={"rescale": "0,4000", "colormap_name": "viridis", "url": "s3://evil/x.tif"},
    )
    assert r.status_code == 200 and r.content == b"\x89PNG-tile"
    assert r.headers["content-type"] == "image/png"


def test_tile_rejects_bad_render_param_and_out_of_range_tile(env):
    base = f"/v1/raster/{env.ids.raster}/tiles"
    assert env.client.get(f"{base}/5/10/12", params={"rescale": "0;rm"}).status_code == 422
    assert env.client.get(f"{base}/2/9/0").status_code == 404  # x >= 2**z


def test_tile_is_404_for_unreadable_unknown_or_non_raster_item(env):
    base = "/v1/raster"
    env.who["user"] = env.users["bob"]  # pas de partage : RLS par item
    assert env.client.get(f"{base}/{env.ids.raster}/tiles/0/0/0").status_code == 404
    assert env.client.get(f"{base}/{env.ids.raster}").status_code == 404
    env.who["user"] = env.users["alice"]
    assert env.client.get(f"{base}/{env.ids.other}/tiles/0/0/0").status_code == 404
    assert env.client.get(f"{base}/nope/tiles/0/0/0").status_code == 404


def test_tile_titiler_statuses(env):
    base = f"/v1/raster/{env.ids.raster}/tiles"
    env.httpserver.expect_request("/cog/tiles/3/1/1.png").respond_with_json({}, status=404)
    assert env.client.get(f"{base}/3/1/1").status_code == 404
    assert env.client.get(f"{base}/3/2/2").status_code == 502  # statut inattendu (500)


def test_tile_and_zonal_refused_403_under_geo_limit(env):
    with env.Session() as s:
        s.add(
            Collection(
                id="parcelles",
                tenant_id=env.ids.tenant,
                owner_id=env.users["alice"].id,
                table_name="parcelles_t",
                title="Parcelles",
                pk_column="id",
            )
        )
        s.get(RasterAsset, env.ids.raster).limit_collection_id = "parcelles"
        s.commit()
    env.app.dependency_overrides[get_request_geo_limits] = lambda: {
        "parcelles_t": [_box(2.0, 48.5, 2.1, 48.6)]
    }
    r = env.client.get(f"/v1/raster/{env.ids.raster}/tiles/5/10/12")
    assert r.status_code == 403 and "geo_limit_unsupported" in r.json()["detail"]
    z = env.client.post(
        f"/v1/raster/{env.ids.raster}/zonal-stats", json={"geojson": _box(2, 48.5, 2.1, 48.6)}
    )
    assert z.status_code == 403
    # un lecteur non limité (pas d'entrée pour cette collection) passe
    env.app.dependency_overrides[get_request_geo_limits] = lambda: {}
    env.httpserver.expect_request("/cog/tiles/5/10/12.png").respond_with_data(b"x")
    assert env.client.get(f"/v1/raster/{env.ids.raster}/tiles/5/10/12").status_code == 200


def test_info_returns_metadata(env):
    r = env.client.get(f"/v1/raster/{env.ids.raster}")
    assert r.status_code == 200
    body = r.json()
    assert body["srid"] == 4326 and body["bands"][0]["index"] == 1 and body["width"] == 64


# --- zonal-stats ------------------------------------------------------------------


def test_zonal_stats_geojson_matches_reference(env):
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "id": "a",
                "properties": {},
                "geometry": _box(2.10, 48.80, 2.20, 48.90),
            }
        ],
    }
    r = env.client.post(f"/v1/raster/{env.ids.raster}/zonal-stats", json={"geojson": fc})
    assert r.status_code == 200
    item = r.json()["results"][0]
    exp = env.ref[10:20, 10:20].astype("float64")
    assert item["id"] == "a" and item["stats"]["count"] == 100
    assert item["stats"]["mean"] == pytest.approx(exp.mean(), abs=1e-6)
    assert np.isclose(item["stats"]["sum"], exp.sum())


def test_zonal_stats_validation(env):
    url = f"/v1/raster/{env.ids.raster}/zonal-stats"
    many = {
        "type": "FeatureCollection",
        "features": [{"type": "Feature", "properties": {}, "geometry": _box(2, 48.5, 2.1, 48.6)}]
        * 1001,
    }
    assert env.client.post(url, json={"geojson": many}).status_code == 422
    assert env.client.post(url, json={}).status_code == 422  # ni geojson ni collectionId
    assert (
        env.client.post(
            url, json={"geojson": {"type": "Point", "coordinates": [2, 48]}}
        ).status_code
        == 422
    )
    assert (
        env.client.post(url, json={"geojson": _box(2, 48.5, 2.1, 48.6), "band": 5}).status_code
        == 422
    )
    env.who["user"] = env.users["bob"]
    assert env.client.post(url, json={"geojson": _box(2, 48.5, 2.1, 48.6)}).status_code == 404


def test_zonal_stats_from_collection_polygons(env):
    with env.Session() as s:
        s.add(
            Collection(
                id="zones",
                tenant_id=env.ids.tenant,
                owner_id=env.users["alice"].id,
                table_name="zones_t",
                title="Zones",
                pk_column="id",
            )
        )
        s.commit()
    feats = [
        {"id": 7, "geometry": _box(2.10, 48.80, 2.20, 48.90), "properties": {}},
        {"id": 8, "geometry": {"type": "Point", "coordinates": [2.1, 48.8]}, "properties": {}},
    ]
    fake_repo = SimpleNamespace(select_features=lambda *a, **k: SimpleNamespace(features=feats))
    o = env.app.dependency_overrides
    o[raster_routes.get_introspector] = lambda: lambda session, table: object()
    o[features_routes.get_features_repo] = lambda: fake_repo
    o[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    o[features_routes.get_masked_for_user] = lambda: False
    r = env.client.post(f"/v1/raster/{env.ids.raster}/zonal-stats", json={"collectionId": "zones"})
    assert r.status_code == 200
    assert [i["id"] for i in r.json()["results"]] == [7] and r.json()["results"][0]["stats"][
        "count"
    ] == 100


# --- ingestion --------------------------------------------------------------------


def test_upload_flow_defers_job_and_audits(env):
    me = env.users["alice"]
    p = env.client.post("/v1/raster/uploads/presign", json={"filename": "o.tif"})
    assert p.status_code == 200 and p.json()["key"].startswith(f"{env.ids.tenant}/")
    r = env.client.post(
        "/v1/raster/uploads",
        json={"key": p.json()["key"], "filename": "o.tif", "title": "Ortho 2026"},
    )
    assert r.status_code == 201
    assert env.deferred == [(r.json()["jobId"], me.tenant_id)]
    s = env.client.get(f"/v1/raster/uploads/{r.json()['jobId']}")
    assert s.json()["status"] == "uploaded"
    bad = env.client.post(
        "/v1/raster/uploads", json={"key": "other/x/o.tif", "filename": "o.tif", "title": "t"}
    )
    assert bad.status_code == 400


def test_upload_refused_to_reader_without_privilege(env):
    with env.Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=env.ids.tenant)
        set_user_role(
            s,
            tenant_id=env.ids.tenant,
            user_id=env.users["bob"].id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        s.commit()
        env.who["user"] = s.get(type(env.users["bob"]), env.users["bob"].id)
        s.expunge(env.who["user"])
    assert (
        env.client.post("/v1/raster/uploads/presign", json={"filename": "o.tif"}).status_code == 403
    )
    r = env.client.post(
        "/v1/raster/uploads",
        json={"key": f"{env.ids.tenant}/x/o.tif", "filename": "o.tif", "title": "t"},
    )
    assert r.status_code == 403 and env.deferred == []


def test_upload_refused_413_when_storage_quota_exceeded(env, monkeypatch):
    class _FullS3(_FakeS3):
        deleted: list = []

        def list_objects_v2(self, **kw):
            return {"Contents": [{"Size": 1001}], "IsTruncated": False}

        def delete_object(self, Bucket, Key):  # noqa: N803
            self.deleted.append(Key)

    full = _FullS3()
    env.app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: full
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_STORAGE_BYTES_PER_TENANT", "1000")
    key = f"{env.ids.tenant}/x/o.tif"
    r = env.client.post("/v1/raster/uploads", json={"key": key, "filename": "o.tif", "title": "t"})
    assert r.status_code == 413 and full.deleted == [key] and env.deferred == []


def test_routes_not_mounted_when_flag_off(monkeypatch):
    monkeypatch.delenv("CORE_RASTER_ENABLED", raising=False)
    assert TestClient(create_app()).get("/v1/raster/x").status_code == 404
