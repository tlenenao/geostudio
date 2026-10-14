# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""Revue voie N (ARC-33) : clé d'upload contrainte, GeoTIFF seul, limites géographiques
fail-closed par défaut, bornes de zonal-stats."""

import pytest
import rasterio

from app.configs.geo_limits_dep import get_request_geo_limits
from app.raster import ingest, service, zonal
from app.raster.models import RasterAsset
from tests.raster_fixtures import write_tif
from tests.test_raster_routes import _box, env  # noqa: F401

HEX = "a" * 32


def _create(env, key, filename="o.tif"):
    return env.client.post(
        "/v1/raster/uploads", json={"key": key, "filename": filename, "title": "t"}
    )


# --- 1. clé d'upload ------------------------------------------------------------


@pytest.mark.parametrize(
    "tail",
    [
        "x/o.tif",
        f"{HEX}/cog.tif",
        f"{HEX}/a/b.tif",
        f"{HEX}/..",
        f"{HEX}/a..b.tif",
        f"{HEX[:-1]}/o",
    ],
)
def test_upload_key_must_have_presigned_shape(env, tail):
    assert _create(env, f"{env.ids.tenant}/{tail}").status_code == 400
    assert env.deferred == []


def test_upload_key_cannot_target_an_existing_cog_or_be_reused(env):
    # cog.tif d'un raster existant (job_id connu de son auteur) : refusé par la forme
    assert _create(env, f"{env.ids.tenant}/{HEX}/cog.tif").status_code == 400
    ok = f"{env.ids.tenant}/{HEX}/o.tif"
    assert _create(env, ok).status_code == 201
    assert _create(env, ok).status_code == 409  # déjà porté par un job


@pytest.mark.parametrize("name", ["a/b.tif", "..", "x..y.tif", "a\\b.tif"])
def test_presign_filename_rejects_paths(env, name):
    r = env.client.post("/v1/raster/uploads/presign", json={"filename": name})
    assert r.status_code == 422


# --- 2. GeoTIFF seul ------------------------------------------------------------


def test_vrt_and_other_gdal_formats_are_refused(tmp_path):
    vrt = tmp_path / "evil.vrt"
    vrt.write_text(
        '<VRTDataset rasterXSize="1" rasterYSize="1"><VRTRasterBand dataType="Byte" band="1">'
        "<SimpleSource><SourceFilename>/vsicurl/http://127.0.0.1/x.tif</SourceFilename>"
        "</SimpleSource></VRTRasterBand></VRTDataset>"
    )
    with pytest.raises(ingest.RasterIngestError, match="GeoTIFF"):
        ingest.to_cog(str(vrt), str(tmp_path / "out.tif"))
    with pytest.raises(ingest.RasterIngestError, match="GeoTIFF"):
        ingest.read_metadata(str(vrt))


def _count_gdal_requests(path_tmpl: str, **cfg) -> int:
    import http.server
    import threading

    hits: list[str] = []

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            hits.append(self.path)
            self.send_response(404)
            self.end_headers()

        do_HEAD = do_GET

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_port
    try:
        with rasterio.Env(
            AWS_S3_ENDPOINT=f"127.0.0.1:{port}",
            AWS_HTTPS="NO",
            AWS_VIRTUAL_HOSTING="FALSE",
            AWS_NO_SIGN_REQUEST="YES",
            **cfg,
        ):
            with pytest.raises(rasterio.errors.RasterioIOError):
                rasterio.open(path_tmpl.format(port=port))
    finally:
        srv.shutdown()
    return len(hits)


@pytest.mark.parametrize("path", ["/vsicurl/http://127.0.0.1:{port}/x.tif", "/vsis3/b/x.tif"])
def test_local_only_gdal_env_emits_no_network_request(path):
    from app.terrain3d.conversion import LOCAL_ONLY_GDAL

    assert _count_gdal_requests(path) > 0  # la sonde voit bien les requêtes sans le garde
    assert _count_gdal_requests(path, **LOCAL_ONLY_GDAL) == 0


def test_ingest_runs_gdal_under_the_local_only_env(tmp_path, monkeypatch):
    from app.terrain3d.conversion import LOCAL_ONLY_GDAL

    seen: list[dict] = []

    def fake_validate(path, strict):
        seen.append(rasterio.env.getenv())
        return True, [], []

    monkeypatch.setattr(ingest, "cog_validate", fake_validate)
    src = tmp_path / "o.tif"
    write_tif(str(src))
    ingest.to_cog(str(src), str(tmp_path / "cog.tif"))
    assert seen and all(seen[0].get(k) == v for k, v in LOCAL_ONLY_GDAL.items())


# --- 3. limites géographiques fail-closed --------------------------------------


def test_unattached_raster_is_refused_to_a_geo_limited_caller(env):
    env.app.dependency_overrides[get_request_geo_limits] = lambda: {"t": [_box(2, 48, 3, 49)]}
    rid = env.ids.raster
    for r in (
        env.client.get(f"/v1/raster/{rid}"),
        env.client.get(f"/v1/raster/{rid}/tiles/5/10/12"),
        env.client.post(
            f"/v1/raster/{rid}/zonal-stats", json={"geojson": _box(2, 48.5, 2.1, 48.6)}
        ),
    ):
        assert r.status_code == 403 and "geo_limit_unsupported" in r.json()["detail"]
    env.app.dependency_overrides[get_request_geo_limits] = lambda: {}
    assert env.client.get(f"/v1/raster/{rid}").status_code == 200


def test_helper_passes_without_limits_and_fails_closed_otherwise(env):
    with env.Session() as s:
        a = s.get(RasterAsset, env.ids.raster)
        service.refuse_if_raster_geo_limited(s, a, {}, "p")
        with pytest.raises(Exception, match="geo_limit_unsupported"):
            service.refuse_if_raster_geo_limited(s, a, {"t": []}, "p")


# --- 4. bornes de zonal-stats ---------------------------------------------------


def test_zonal_pixel_budget_and_deadline(tmp_path, monkeypatch):
    poly = _box(2.0, 48.4, 2.6, 49.0)
    p = str(tmp_path / "a.tif")
    write_tif(p)
    with rasterio.open(p) as ds:
        assert zonal.zonal_stats(ds, [poly], stats=["count"])[0]["count"] > 0
        monkeypatch.setattr(zonal, "MAX_TOTAL_PIXELS", 100)
        with pytest.raises(zonal.ZonalError, match="budget"):
            zonal.zonal_stats(ds, [poly, poly], stats=["count"])
        monkeypatch.setattr(zonal, "MAX_TOTAL_PIXELS", 10**9)
        monkeypatch.setattr(zonal, "MAX_SECONDS", -1.0)
        with pytest.raises(zonal.ZonalError, match="délai"):
            zonal.zonal_stats(ds, [poly], stats=["count"])


def test_geojson_body_size_is_capped(env, monkeypatch):
    monkeypatch.setattr(service, "MAX_GEOJSON_BYTES", 50)
    r = env.client.post(
        f"/v1/raster/{env.ids.raster}/zonal-stats", json={"geojson": _box(2, 48.5, 2.1, 48.6)}
    )
    assert r.status_code == 422 and "volumineux" in r.json()["detail"]
