# SPDX-License-Identifier: Apache-2.0
"""Voie F2 FME : lecteurs GDAL (NetCDF, GRIB, ERDAS, JP2, Sentinel-2, Landsat-8, OSM), CityJSON,
WMS, WCS. Fixtures générées par code (< 100 Ko)."""

import json
import os
import struct
import time
import zlib

import duckdb
import numpy as np
import pytest
import rasterio
import rasterio.shutil
from pydantic import ValidationError
from rasterio.transform import from_origin

from app.configs.schemas import PipelinePayload
from app.pipelines import egress as pipelines_egress
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import readers2 as r2
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from tests.test_pipeline_ops_raster2 import env  # noqa: F401
from tests.test_pipeline_ops_raster2 import rows as rrows
from tests.test_pipeline_ops_raster2 import run as rrun

LANE_OPS = {
    "reader.netcdf", "reader.erdasImagine", "reader.jpeg2000", "reader.grib",
    "reader.sentinel2", "reader.landsat8", "reader.osm", "reader.cityjson",
    "reader.wms", "reader.wcs",
}  # fmt: skip
_REAL_GUARD = pipelines_egress.assert_egress_allowed


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _fileio(monkeypatch):
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "true")


def _read(fn, conn, **params):
    return fn(
        conn, session=None, tenant_id="t", node_id="n", view_name="v", user=None, base_uri="",
        params=params,
    )  # fmt: skip


def _grid(path, driver="GTiff", dtype="float32", crs="EPSG:4326"):
    a = np.arange(100, dtype=dtype).reshape(10, 10)
    with rasterio.open(
        path, "w", driver=driver, width=10, height=10, count=1, dtype=dtype, crs=crs,
        transform=from_origin(0, 10, 1, 1),
    ) as d:  # fmt: skip
        d.write(a, 1)
    return str(path)


def _rows(conn):
    return conn.execute(
        "SELECT x, y, value, ST_AsText(geometry) FROM v ORDER BY y DESC, x"
    ).fetchall()


def test_lane_contracts_and_catalog(monkeypatch):
    assert {c.op for c in r2.CONTRACTS} == LANE_OPS
    assert set(r2.READERS) == LANE_OPS
    assert all(OPERATIONS[o].engine_license for o in LANE_OPS)
    assert {"reader.wms", "reader.wcs"} <= set(ops_catalog())  # réseau : toujours visibles
    assert "reader.netcdf" in ops_catalog()  # flag fichier actif (fixture autouse)
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    assert "reader.netcdf" not in ops_catalog() and "reader.osm" not in ops_catalog()


# ------------------------------------------------------------------ rasters fichier


def test_netcdf(tmp_path, conn):
    rasterio.shutil.copy(_grid(tmp_path / "m.tif"), str(tmp_path / "a.nc"), driver="netCDF")
    srid = _read(r2.read_netcdf, conn, path=str(tmp_path / "a.nc"))
    rows = _rows(conn)
    assert srid == 4326 and len(rows) == 100
    assert rows[0][:3] == (0.5, 9.5, 0.0) and rows[-1][2] == 99.0
    assert rows[0][3] == "POINT (0.5 9.5)"


def test_netcdf_variable_rejects_injection(tmp_path, conn):
    rasterio.shutil.copy(_grid(tmp_path / "m.tif"), str(tmp_path / "a.nc"), driver="netCDF")
    with pytest.raises(ValidationError, match="variable"):
        _read(r2.read_netcdf, conn, path=str(tmp_path / "a.nc"), variable='x":/etc/passwd')


def test_erdas_grib_jp2(tmp_path, conn):
    for fn, drv, name, dtype in [
        (r2.read_erdas, "HFA", "a.img", "float32"),
        (r2.read_grib, "GRIB", "a.grib2", "float32"),
        (r2.read_jp2, "JP2OpenJPEG", "a.jp2", "uint16"),
    ]:
        p = _grid(tmp_path / name, drv, dtype)
        assert _read(fn, conn, path=p) == 4326
        assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 100
        conn.execute("DROP TABLE v")


def test_decimation_caps_cells(tmp_path, conn):
    _read(r2.read_erdas, conn, path=_grid(tmp_path / "a.img", "HFA"), maxCells=25)
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] <= 25


def test_nan_and_nodata_dropped(tmp_path, conn):
    a = np.full((10, 10), np.nan, dtype="float32")
    a[0, 0] = 7
    with rasterio.open(
        tmp_path / "n.img", "w", driver="HFA", width=10, height=10, count=1, dtype="float32",
        crs="EPSG:4326", transform=from_origin(0, 10, 1, 1),
    ) as d:  # fmt: skip
        d.write(a, 1)
    _read(r2.read_erdas, conn, path=str(tmp_path / "n.img"))
    assert conn.execute("SELECT value FROM v").fetchall() == [(7.0,)]


def test_missing_crs_needs_srid(tmp_path, conn):
    a = np.ones((4, 4), dtype="float32")
    with rasterio.open(
        tmp_path / "x.img", "w", driver="HFA", width=4, height=4, count=1, dtype="float32",
        transform=from_origin(0, 4, 1, 1),
    ) as d:  # fmt: skip
        d.write(a, 1)
    with pytest.raises(PipelineRuntimeError, match="srid"):
        _read(r2.read_erdas, conn, path=str(tmp_path / "x.img"))
    assert _read(r2.read_erdas, conn, path=str(tmp_path / "x.img"), srid=2154) == 2154


def test_bad_band(tmp_path, conn):
    with pytest.raises(PipelineRuntimeError, match="band 2"):
        _read(r2.read_erdas, conn, path=_grid(tmp_path / "a.img", "HFA"), band=2)


# ------------------------------------------------------------------ garde fichier


def test_flag_off_refused(tmp_path, conn, monkeypatch):
    p = _grid(tmp_path / "a.img", "HFA")
    monkeypatch.setenv("CORE_PIPELINE_FILE_IO_ENABLED", "false")
    for fn in (r2.read_erdas, r2.read_osm, r2.read_cityjson, r2.read_netcdf):
        with pytest.raises(PipelineRuntimeError, match="CORE_PIPELINE_FILE_IO_ENABLED"):
            _read(fn, conn, path=p)


@pytest.mark.parametrize(
    "bad", ["/vsicurl/http://x/a.img", "/vsis3/b/a.img", "a.img", "http://x/a.img", "/etc/\x00x"]
)
def test_arbitrary_access_refused(bad, conn):
    with pytest.raises(PipelineRuntimeError):
        _read(r2.read_erdas, conn, path=bad)


def test_vrt_and_wrong_format_refused(tmp_path, conn):
    vrt = tmp_path / "evil.img"
    vrt.write_text('<VRTDataset rasterXSize="1" rasterYSize="1"><VRTRasterBand dataType="Byte">'
                   '<SimpleSource><SourceFilename>/etc/passwd</SourceFilename></SimpleSource>'
                   '</VRTRasterBand></VRTDataset>')  # fmt: skip
    for fn in (r2.read_erdas, r2.read_jp2, r2.read_grib, r2.read_netcdf, r2.read_osm):
        with pytest.raises(PipelineRuntimeError, match="format attendu"):
            _read(fn, conn, path=str(vrt))


def test_symlink_to_non_file_and_dir(tmp_path, conn):
    with pytest.raises(PipelineRuntimeError, match="introuvable"):
        _read(r2.read_erdas, conn, path=str(tmp_path))


def test_file_size_cap(tmp_path, conn, monkeypatch):
    monkeypatch.setattr(r2, "MAX_FILE_BYTES", 100)
    with pytest.raises(PipelineRuntimeError, match="too large"):
        _read(r2.read_erdas, conn, path=_grid(tmp_path / "a.img", "HFA"))


def test_declared_pixel_bomb_refused(tmp_path, conn, monkeypatch):
    p = _grid(tmp_path / "a.img", "HFA")
    monkeypatch.setattr(r2, "MAX_SOURCE_PIXELS", 50)
    with pytest.raises(PipelineRuntimeError, match="too large"):
        _read(r2.read_erdas, conn, path=p)


def test_bounded_timeout_and_memory(monkeypatch):
    monkeypatch.setattr(r2, "READ_TIMEOUT_S", 0.5)
    t = time.monotonic()
    with pytest.raises(PipelineRuntimeError, match="time limit"):
        r2._bounded("op", time.sleep, 30)
    assert time.monotonic() - t < 10
    monkeypatch.setattr(r2, "READ_TIMEOUT_S", 30)
    monkeypatch.setattr(r2, "READ_EXTRA_MEMORY", 64 * 1024 * 1024)
    with pytest.raises(PipelineRuntimeError):
        r2._bounded("op", lambda: np.ones(2_000_000_000, dtype="uint8").sum())


# ------------------------------------------------------------------ Sentinel-2 / Landsat-8


def _s2(tmp_path):
    d = tmp_path / "S2A.SAFE" / "GRANULE" / "L2A_T31" / "IMG_DATA" / "R10m"
    d.mkdir(parents=True)
    _grid(d / "T31_20240101_B04_10m.jp2", "JP2OpenJPEG", "uint16")
    return str(tmp_path / "S2A.SAFE")


def test_sentinel2(tmp_path, conn):
    root = _s2(tmp_path)
    assert _read(r2.read_sentinel2, conn, path=root, band="B04", resolution=10) == 4326
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 100
    conn.execute("DROP TABLE v")
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_sentinel2, conn, path=root, band="B08")
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_sentinel2, conn, path=root, band="B04", resolution=60)


def test_sentinel2_resolution_selected_before_sorting(tmp_path, conn):
    for res in (10, 20, 60):
        d = tmp_path / "S2.SAFE" / "IMG_DATA" / f"R{res}m"
        d.mkdir(parents=True, exist_ok=True)
        with rasterio.open(
            d / f"T_B04_{res}m.jp2", "w", driver="JP2OpenJPEG", width=res // 10 * 4,
            height=res // 10 * 4, count=1, dtype="uint16", crs="EPSG:4326",
            transform=from_origin(0, 10, 1, 1),
        ) as dst:  # fmt: skip
            dst.write(np.ones((res // 10 * 4,) * 2, dtype="uint16"), 1)
    root = str(tmp_path / "S2.SAFE")
    for res, n in ((10, 16), (20, 64), (60, 576)):
        _read(r2.read_sentinel2, conn, path=root, band="B04", resolution=res)
        assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == n
        conn.execute("DROP TABLE v")


def test_sentinel2_symlink_escape_ignored(tmp_path, conn):
    outside = _grid(tmp_path / "outside.jp2", "JP2OpenJPEG", "uint16")
    d = tmp_path / "S2B.SAFE" / "IMG_DATA"
    d.mkdir(parents=True)
    os.symlink(outside, d / "T_B04.jp2")
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_sentinel2, conn, path=str(tmp_path / "S2B.SAFE"), band="B04")


def test_landsat8(tmp_path, conn):
    d = tmp_path / "LC08_L1TP"
    d.mkdir()
    _grid(d / "LC08_L1TP_B4.TIF", "GTiff", "uint16")
    (d / "LC08_L1TP_MTL.txt").write_text("GROUP = L1_METADATA_FILE")
    assert _read(r2.read_landsat8, conn, path=str(d), band=4) == 4326
    assert conn.execute("SELECT max(value) FROM v").fetchone()[0] == 99
    with pytest.raises(PipelineRuntimeError, match="aucune bande"):
        _read(r2.read_landsat8, conn, path=str(d), band=5)


# ------------------------------------------------------------------ OSM


OSM_XML = """<?xml version='1.0' encoding='UTF-8'?>
<osm version="0.6" generator="t">
 <node id="1" lat="45.0" lon="2.0" version="1"><tag k="name" v="Tulle"/><tag k="amenity" v="cafe"/></node>
 <node id="2" lat="45.1" lon="2.1" version="1"/>
 <node id="3" lat="45.2" lon="2.2" version="1"><tag k="name" v="B"/></node>
</osm>"""  # noqa: E501


def _varint(n):
    out = b""
    while True:
        b = n & 0x7F
        n >>= 7
        out += bytes([b | (0x80 if n else 0)])
        if not n:
            return out


def _f(num, wt, payload):
    return _varint(num << 3 | wt) + payload


def _ld(num, data):
    return _f(num, 2, _varint(len(data)) + data)


def _zz(n):
    return _varint((n << 1) ^ (n >> 63))


def _pbf(path):
    def blob(kind, data):
        z = zlib.compress(data)
        b = _f(2, 0, _varint(len(data))) + _ld(3, z)
        h = _ld(1, kind) + _f(3, 0, _varint(len(b)))
        return struct.pack(">I", len(h)) + h + b

    header = _ld(4, b"OsmSchema-V0.6")
    strings = b"".join(_ld(1, s) for s in (b"", b"name", b"Tulle"))
    node = (
        _f(1, 0, _zz(1)) + _ld(2, _varint(1)) + _ld(3, _varint(2))
        + _f(8, 0, _zz(450_000_000)) + _f(9, 0, _zz(20_000_000))
    )  # fmt: skip
    block = _ld(1, strings) + _ld(2, _ld(1, node))
    path.write_bytes(blob(b"OSMHeader", header) + blob(b"OSMData", block))
    return str(path)


def test_osm_xml(tmp_path, conn):
    p = tmp_path / "a.osm"
    p.write_text(OSM_XML)
    assert _read(r2.read_osm, conn, path=str(p), layer="points") == 4326
    names = conn.execute("SELECT name FROM v ORDER BY osm_id").fetchall()
    assert len(names) >= 2 and ("Tulle",) in names
    assert conn.execute("SELECT ST_AsText(geometry) FROM v WHERE name='Tulle'").fetchone() == (
        "POINT (2 45)",
    )


@pytest.mark.parametrize(
    "content",
    [
        "<?xml version='1.0'?><!-- <osm --><OGRVRTDataSource><OGRVRTLayer name='x'>"
        "<SrcDataSource>/etc/hostname</SrcDataSource></OGRVRTLayer></OGRVRTDataSource>",
        "<osm><!-- <OGRVRTDataSource> --></osm>",
        "<!DOCTYPE x><osm></osm>",
        "<other><osm/></other>",
    ],
)
def test_osm_polyglot_refused(tmp_path, conn, content):
    p = tmp_path / "evil.osm"
    p.write_text(content)
    with pytest.raises(PipelineRuntimeError, match="format attendu"):
        _read(r2.read_osm, conn, path=str(p))


def test_osm_driver_is_checked_after_open(tmp_path, conn, monkeypatch):
    p = tmp_path / "a.osm"
    p.write_text(OSM_XML)
    import pyogrio

    monkeypatch.setattr(pyogrio, "read_info", lambda path, **kw: {"driver": "OGR_VRT"})
    with pytest.raises(PipelineRuntimeError, match="pilote inattendu"):
        _read(r2.read_osm, conn, path=str(p))


def test_osm_max_features(tmp_path, conn):
    p = tmp_path / "a.osm"
    p.write_text(OSM_XML)
    _read(r2.read_osm, conn, path=str(p), maxFeatures=1)
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 1


def test_osm_pbf(tmp_path, conn):
    _read(r2.read_osm, conn, path=_pbf(tmp_path / "a.osm.pbf"))
    assert conn.execute("SELECT ST_AsText(geometry) FROM v WHERE name='Tulle'").fetchone() == (
        "POINT (2 45)",
    )


# ------------------------------------------------------------------ CityJSON


def _cityjson(path, crs="https://www.opengis.net/def/crs/EPSG/0/2154"):
    # cube 10x10x5 en coordonnées entières + transform
    v = [
        [0, 0, 0],
        [10, 0, 0],
        [10, 10, 0],
        [0, 10, 0],
        [0, 0, 5],
        [10, 0, 5],
        [10, 10, 5],
        [0, 10, 5],
    ]
    faces = [
        [[0, 3, 2, 1]],
        [[4, 5, 6, 7]],
        [[0, 1, 5, 4]],
        [[1, 2, 6, 5]],
        [[2, 3, 7, 6]],
        [[3, 0, 4, 7]],
    ]
    doc = {
        "type": "CityJSON", "version": "2.0",
        "transform": {"scale": [1.0, 1.0, 1.0], "translate": [1000.0, 2000.0, 100.0]},
        "metadata": {"referenceSystem": crs},
        "CityObjects": {
            "b1": {"type": "Building", "attributes": {"h": 5},
                   "geometry": [{"type": "Solid", "lod": "2", "boundaries": [faces]},
                                {"type": "Solid", "lod": "1", "boundaries": [faces[:2]]}]},
            "e": {"type": "Bridge", "geometry": []},
        },
        "vertices": v,
    }  # fmt: skip
    path.write_text(json.dumps(doc))
    return str(path)


def test_cityjson(tmp_path, conn):
    p = _cityjson(tmp_path / "c.city.json")
    assert _read(r2.read_cityjson, conn, path=p) == 2154
    rows = conn.execute(
        "SELECT id, type, lod, min_z, max_z, ST_Area(geometry), attributes FROM v ORDER BY id"
    ).fetchall()
    assert rows[0] == ("b1", "Building", "2", 100.0, 105.0, 100.0, '{"h": 5}')
    assert rows[1][0] == "e" and rows[1][5] is None
    conn.execute("DROP TABLE v")
    _read(r2.read_cityjson, conn, path=p, lod="1")
    assert conn.execute("SELECT lod FROM v WHERE id='b1'").fetchone() == ("1",)


def _city_doc(path, boundaries, vertices=((0, 0, 0), (1, 0, 0), (1, 1, 0), (0, 1, 0))):
    doc = {
        "type": "CityJSON", "version": "2.0",
        "metadata": {"referenceSystem": "urn:ogc:def:crs:EPSG::2154"},
        "vertices": [list(v) for v in vertices],
        "CityObjects": {
            "ok": {"type": "B", "geometry": [{"type": "MultiSurface", "lod": "1",
                                             "boundaries": [[[0, 1, 2, 3]]]}]},
            "bad": {"type": "B", "geometry": [{"type": "MultiSurface", "lod": "1",
                                              "boundaries": boundaries}]},
        },
    }  # fmt: skip
    path.write_text(json.dumps(doc))
    return str(path)


@pytest.mark.parametrize(
    ("boundaries", "msg"),
    [
        ([[[0, 1]]], "moins de 3 sommets"),
        ([[[0, 1, -1]]], "hors bornes"),
        ([[[0, 1, 9]]], "hors bornes"),
        ([[["a", 1, 2]]], "invalide"),
    ],
)
def test_cityjson_degenerate_rings_are_row_errors(tmp_path, conn, boundaries, msg):
    _read(r2.read_cityjson, conn, path=_city_doc(tmp_path / "c.json", boundaries))
    got = dict(conn.execute("SELECT id, error FROM v").fetchall())
    assert got["ok"] is None and msg in got["bad"]  # une ligne en erreur, les autres lues
    assert conn.execute("SELECT geometry FROM v WHERE id='bad'").fetchone() == (None,)


def test_cityjson_invalid_file_and_no_crs(tmp_path, conn):
    p = tmp_path / "bad.json"
    p.write_text('{"type":"Other CityJSON"}')
    with pytest.raises(PipelineRuntimeError, match="invalide"):
        _read(r2.read_cityjson, conn, path=str(p))
    nocrs = _cityjson(tmp_path / "n.json", crs="foo")
    with pytest.raises(PipelineRuntimeError, match="srid"):
        _read(r2.read_cityjson, conn, path=nocrs)


def test_cityjson_parse_runs_in_bounded_child(tmp_path, conn, monkeypatch):
    p = _cityjson(tmp_path / "c.json")
    pids = tmp_path / "pids"
    real_load = json.load

    def spy(f):
        pids.write_text(str(os.getpid()))
        return real_load(f)

    monkeypatch.setattr(r2.json, "load", spy)
    _read(r2.read_cityjson, conn, path=p)
    assert pids.read_text() != str(os.getpid())  # json.load s'exécute dans le fils, pas le worker


# ------------------------------------------------------------------ WMS / WCS


@pytest.fixture()
def local_net(monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


def _png(w=4, h=3):
    with rasterio.MemoryFile() as m:
        with m.open(
            driver="PNG", width=w, height=h, count=3, dtype="uint8",
            transform=from_origin(0, h, 1, 1),
        ) as d:  # fmt: skip
            for i in (1, 2, 3):
                d.write(np.full((h, w), i * 10, dtype="uint8"), i)
        return m.read()


def _tif_bytes():
    with rasterio.MemoryFile() as m:
        with m.open(
            driver="GTiff", width=4, height=4, count=1, dtype="float32", crs="EPSG:3857",
            transform=from_origin(100, 140, 10, 10),
        ) as d:  # fmt: skip
            d.write(np.arange(16, dtype="float32").reshape(4, 4), 1)
        return m.read()


def test_wms(httpserver, local_net, conn):
    httpserver.expect_request("/wms").respond_with_data(_png(), content_type="image/png")
    srid = _read(
        r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 40, 4, 43],
        width=4, height=3,
    )  # fmt: skip
    assert srid == 4326
    q = httpserver.log[0][0].args
    assert q["bbox"] == "40.0,0.0,43.0,4.0" and q["crs"] == "EPSG:4326" and q["request"] == "GetMap"
    rows = conn.execute("SELECT x, y, band_1, band_3 FROM v ORDER BY y DESC, x").fetchall()
    assert len(rows) == 12 and rows[0] == (0.5, 42.5, 10, 30)


def test_wms_georef_uses_received_size(httpserver, local_net, conn):
    httpserver.expect_request("/wms").respond_with_data(_png(4, 3))  # serveur ignore 8x6
    _read(
        r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 40, 4, 43],
        width=8, height=6,
    )  # fmt: skip
    assert conn.execute("SELECT min(x), max(x), max(y) FROM v").fetchone() == (0.5, 3.5, 42.5)


def test_wms_exception_not_image(httpserver, local_net, conn):
    httpserver.expect_request("/wms").respond_with_data(
        "<ServiceException/>", content_type="text/xml"
    )
    with pytest.raises(PipelineRuntimeError, match="not an image"):
        _read(r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 0, 1, 1])


def test_wcs_geotiff(httpserver, local_net, conn):
    httpserver.expect_request("/wcs").respond_with_data(_tif_bytes(), content_type="image/tiff")
    srid = _read(
        r2.read_wcs, conn, url=httpserver.url_for("/wcs"), coverage="c", bbox=[100, 100, 140, 140],
        srid=3857, width=4, height=4,
    )  # fmt: skip
    assert srid == 3857
    assert conn.execute("SELECT count(*), max(value) FROM v").fetchone() == (16, 15.0)
    assert httpserver.log[0][0].args["coverage"] == "c"


def test_wcs_201_query(httpserver, local_net, conn):
    httpserver.expect_request("/wcs").respond_with_data(_tif_bytes())
    _read(
        r2.read_wcs, conn, url=httpserver.url_for("/wcs"), coverage="c", version="2.0.1",
        bbox=[100, 100, 140, 140], srid=3857,
    )  # fmt: skip
    assert httpserver.log[0][0].args.getlist("subset") == ["x(100.0,140.0)", "y(100.0,140.0)"]


def test_web_caps(httpserver, local_net, conn, monkeypatch):
    httpserver.expect_request("/wms").respond_with_data(_png())
    monkeypatch.setattr(r2, "MAX_WEB_BYTES", 10)
    with pytest.raises(PipelineRuntimeError, match="too large"):
        _read(r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 0, 1, 1])
    monkeypatch.setattr(r2, "MAX_WEB_BYTES", 10**7)
    monkeypatch.setattr(r2, "MAX_WEB_PIXELS", 4)
    with pytest.raises(PipelineRuntimeError, match="too large"):
        _read(
            r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 0, 1, 1],
            width=2, height=2,
        )  # fmt: skip
    with pytest.raises(ValidationError, match="width"):
        _read(
            r2.read_wms,
            conn,
            url="http://x",
            layers="a",
            bbox=[0, 0, 1, 1],
            width=2048,
            height=2048,
        )


def test_web_egress_guard_and_scheme(conn, monkeypatch):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_GUARD)
    for url in ("http://127.0.0.1:1/wms", "http://169.254.169.254/latest"):
        with pytest.raises(PipelineRuntimeError, match="egress blocked"):
            _read(r2.read_wms, conn, url=url, layers="a", bbox=[0, 0, 1, 1])
    for url in ("file:///etc/passwd", "ftp://x/y"):
        with pytest.raises(PipelineRuntimeError, match="http"):
            _read(r2.read_wcs, conn, url=url, coverage="c", bbox=[0, 0, 1, 1])


def test_web_bad_bbox(conn):
    with pytest.raises(ValidationError, match="bbox"):
        _read(r2.read_wms, conn, url="http://x", layers="a", bbox=[1, 1, 0, 0])


# ------------------------------------------------------------------ output=rasterItem (F1)


@pytest.fixture()
def renv(request):
    return request.getfixturevalue("env")


@pytest.mark.parametrize(
    ("fn", "drv", "name", "dtype"),
    [
        (r2.read_erdas, "HFA", "a.img", "float32"),
        (r2.read_grib, "GRIB", "a.grib2", "float32"),
        (r2.read_jp2, "JP2OpenJPEG", "a.jp2", "uint16"),
    ],
)
def test_raster_item_feeds_f1_stats(renv, tmp_path, fn, drv, name, dtype):
    from app.raster.models import RasterAsset

    src = _grid(tmp_path / name, drv, dtype)
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    # renv.paths mappe source_key -> fichier : le faux téléversement de F1 y copie le COG
    fn(
        conn, session=renv.s, tenant_id=renv.tid, node_id="n", view_name="v", user=renv.alice,
        base_uri="", params={"path": src, "output": "rasterItem", "title": "T"},
    )  # fmt: skip
    (item_id, w, h, bands, srid) = conn.execute("SELECT * FROM v").fetchone()
    assert (w, h, bands, srid) == (10, 10, 1, 4326) and renv.s.get(RasterAsset, item_id)
    # E2E : la sortie alimente transform.rasterStats (colonne item_id, comme reader.rasterItems)
    c = rrun(renv, "transform.rasterStats", {}, [item_id])
    count, mx = rrows(c, "SELECT raster_b1_count, raster_b1_max FROM out")[0]
    assert count == 100 and mx >= 90  # JP2 : compression avec perte


def test_raster_item_netcdf_and_guards(renv, tmp_path, monkeypatch):
    rasterio.shutil.copy(_grid(tmp_path / "m.tif"), str(tmp_path / "a.nc"), driver="netCDF")
    conn = duckdb.connect(":memory:")
    conn.execute("INSTALL spatial; LOAD spatial;")
    kw = {
        "session": renv.s,
        "tenant_id": renv.tid,
        "node_id": "n",
        "view_name": "v",
        "base_uri": "",
    }
    params = {"path": str(tmp_path / "a.nc"), "output": "rasterItem"}
    r2.read_netcdf(conn, user=renv.alice, params=params, **kw)
    assert conn.execute("SELECT count(*) FROM v").fetchone()[0] == 1
    conn.execute("DROP TABLE v")
    from app.users.repository import set_user_role

    set_user_role(
        renv.s, tenant_id=renv.tid, user_id=renv.bob.id, role_id=renv.roles["reader"].id,
        role_slug="reader",
    )  # fmt: skip
    with pytest.raises(PipelineRuntimeError, match="catalog.manage"):
        r2.read_netcdf(conn, user=renv.bob, params=params, **kw)
    monkeypatch.setattr(r2, "MAX_ITEM_PIXELS", 50)
    with pytest.raises(PipelineRuntimeError, match="trop grand"):
        r2.read_netcdf(conn, user=renv.alice, params=params, **kw)
    monkeypatch.setenv("CORE_RASTER_ENABLED", "false")
    with pytest.raises(PipelineRuntimeError, match="CORE_RASTER_ENABLED"):
        r2.read_netcdf(conn, user=renv.alice, params=params, **kw)


def test_raster_item_not_published_in_preview(renv, tmp_path):
    from app.raster.models import RasterAsset

    payload = PipelinePayload.model_validate(
        {
            "nodes": [
                {
                    "id": "r1", "kind": "reader", "op": "reader.erdasImagine",
                    "params": {"path": _grid(tmp_path / "a.img", "HFA"), "output": "rasterItem"},
                },
                {"id": "w1", "kind": "writer", "op": "writer.export",
                 "params": {"format": "csv", "key": "o.csv"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        }
    )  # fmt: skip
    n = renv.s.query(RasterAsset).count()
    out = runtime.preview_pipeline(
        session=renv.s, payload=payload, tenant_id=renv.tid, user=renv.alice, up_to="r1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=5,
    )  # fmt: skip
    assert renv.s.query(RasterAsset).count() == n
    assert out == [{"item_id": None, "width": 10, "height": 10, "bands": 1, "srid": 4326}]


def test_f2_node_preview_via_preview_pipeline(tmp_path):
    payload = PipelinePayload.model_validate(
        {
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.erdasImagine",
                 "params": {"path": _grid(tmp_path / "a.img", "HFA")}},
                {"id": "t1", "kind": "transform", "op": "transform.filter",
                 "params": {"expr": "value >= 95"}},
                {"id": "w1", "kind": "writer", "op": "writer.export",
                 "params": {"format": "csv", "key": "o.csv"}},
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"},
                {"id": "e2", "from": "t1", "to": "w1"},
            ],
        }
    )  # fmt: skip
    out = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )  # fmt: skip
    assert sorted(r["value"] for r in out) == [95, 96, 97, 98, 99]
    assert out[0]["geometry"]["type"] == "Point"


def test_pipelines_import_without_posix_resource_module():
    """Windows (sidecar desktop-etl) n'a pas `resource` : le runtime de pipeline
    doit s'importer quand même (régression CI desktop-etl du 2026-10-15)."""
    import subprocess
    import sys

    code = "import sys; sys.modules['resource'] = None; import app.pipelines.runtime"
    subprocess.run([sys.executable, "-c", code], check=True, cwd=".")
