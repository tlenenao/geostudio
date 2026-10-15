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
from rasterio.transform import from_origin

from app.pipelines import egress as pipelines_egress
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import readers2 as r2
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog

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
    with pytest.raises(Exception, match="variable"):
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
    with pytest.raises(PipelineRuntimeError, match="résolution"):
        _read(r2.read_sentinel2, conn, path=root, band="B04", resolution=60)


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


def test_cityjson_degenerate_and_invalid(tmp_path, conn):
    p = tmp_path / "bad.json"
    p.write_text(
        '{"type":"CityJSON","vertices":[[0,0,0]],"CityObjects":{"x":{"type":"B","geometry":'
        '[{"type":"MultiSurface","lod":"1","boundaries":[[[0,5,9]]]}]}}}'
    )
    with pytest.raises(PipelineRuntimeError, match="hors bornes|srid"):
        _read(r2.read_cityjson, conn, path=str(p), srid=2154)
    p.write_text('{"type":"Other CityJSON"}')
    with pytest.raises(PipelineRuntimeError, match="invalide"):
        _read(r2.read_cityjson, conn, path=str(p))
    nocrs = _cityjson(tmp_path / "n.json", crs="foo")
    with pytest.raises(PipelineRuntimeError, match="srid"):
        _read(r2.read_cityjson, conn, path=nocrs)


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
    with pytest.raises(Exception, match="too large|width\\*height"):
        _read(r2.read_wms, conn, url=httpserver.url_for("/wms"), layers="a", bbox=[0, 0, 1, 1])
    with pytest.raises(Exception, match="width"):
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
    with pytest.raises(Exception, match="bbox"):
        _read(r2.read_wms, conn, url="http://x", layers="a", bbox=[1, 1, 0, 0])
