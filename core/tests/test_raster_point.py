# SPDX-License-Identifier: Apache-2.0
"""AUD-142 : identify raster (`GET /raster/{id}/point`) via TiTiler, mêmes gardes que les tuiles."""

from app.collections.models import Collection
from app.configs.geo_limits_dep import get_request_geo_limits
from app.raster.models import RasterAsset
from tests.test_raster_routes import BUCKET, _box, env  # noqa: F401  (fixture partagée)


def test_point_proxies_titiler_with_server_side_url_only(env):  # noqa: F811
    env.httpserver.expect_request(
        "/cog/point/2.35,48.85",
        query_string=f"url=s3%3A%2F%2F{BUCKET}%2F{env.ids.tenant}%2Fjob%2Fcog.tif",
    ).respond_with_json(
        {"coordinates": [2.35, 48.85], "values": [12.5, None], "band_names": ["b1", "b2"]}
    )
    r = env.client.get(
        f"/v1/raster/{env.ids.raster}/point",
        params={"lon": 2.35, "lat": 48.85, "url": "s3://evil/x.tif"},
    )
    assert r.status_code == 200
    assert r.json() == {
        "lon": 2.35,
        "lat": 48.85,
        "values": [12.5, None],
        "bandNames": ["b1", "b2"],
    }


def test_point_validates_coordinates_and_statuses(env):  # noqa: F811
    base = f"/v1/raster/{env.ids.raster}/point"
    assert env.client.get(base, params={"lon": 181, "lat": 0}).status_code == 422
    assert env.client.get(base, params={"lon": 0}).status_code == 422
    env.httpserver.expect_request("/cog/point/1.0,1.0").respond_with_json({}, status=404)
    assert env.client.get(base, params={"lon": 1, "lat": 1}).status_code == 404
    env.httpserver.expect_request("/cog/point/2.0,2.0").respond_with_json({}, status=500)
    assert env.client.get(base, params={"lon": 2, "lat": 2}).status_code == 502
    env.httpserver.expect_request("/cog/point/3.0,3.0").respond_with_json({"oops": 1})
    assert env.client.get(base, params={"lon": 3, "lat": 3}).status_code == 502


def test_point_is_404_for_unreadable_or_non_raster_item(env):  # noqa: F811
    env.who["user"] = env.users["bob"]  # pas de partage : lecture de l'item refusée
    assert env.client.get(f"/v1/raster/{env.ids.raster}/point?lon=0&lat=0").status_code == 404
    env.who["user"] = env.users["alice"]
    assert env.client.get(f"/v1/raster/{env.ids.other}/point?lon=0&lat=0").status_code == 404


def test_point_refused_under_geo_limit(env):  # noqa: F811
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
    r = env.client.get(f"/v1/raster/{env.ids.raster}/point?lon=2.05&lat=48.55")
    assert r.status_code == 403 and "geo_limit_unsupported" in r.json()["detail"]
