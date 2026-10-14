# SPDX-License-Identifier: Apache-2.0
import pytest
import rasterio

from app.raster import ingest, zonal
from tests.raster_fixtures import write_tif


def _box(w, s, e, n):
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def test_zonal_stats_matches_numpy_reference(tmp_path):
    p = str(tmp_path / "a.tif")
    ref = write_tif(p)
    # pixels col 10..19, lignes 10..19 : x 2.10..2.20, y 48.80..48.90
    with rasterio.open(p) as ds:
        out = zonal.zonal_stats(ds, [_box(2.10, 48.80, 2.20, 48.90)])[0]
    expected = ref[10:20, 10:20].astype("float64")
    assert out["count"] == 100
    assert out["mean"] == pytest.approx(expected.mean(), abs=1e-6)
    assert out["sum"] == pytest.approx(expected.sum(), abs=1e-6)
    assert out["min"] == expected.min() and out["max"] == expected.max()


def test_zonal_stats_nodata_excluded_and_disjoint_empty(tmp_path):
    p = str(tmp_path / "a.tif")
    write_tif(p)
    with rasterio.open(p) as ds:
        top, away = zonal.zonal_stats(
            ds, [_box(2.0, 48.995, 2.64, 49.0), _box(10, 10, 11, 11)], stats=["count", "mean"]
        )
    assert top == {"count": 0, "mean": None}  # ligne 0 = nodata
    assert away == {"count": 0, "mean": None}


def test_zonal_stats_caps_and_validation(tmp_path):
    p = str(tmp_path / "a.tif")
    write_tif(p)
    with rasterio.open(p) as ds:
        with pytest.raises(zonal.ZonalError, match="trop de polygones"):
            zonal.zonal_stats(ds, [_box(2, 48.5, 2.1, 48.6)] * 1001)
        with pytest.raises(zonal.ZonalError, match="bande"):
            zonal.zonal_stats(ds, [], band=3)
        with pytest.raises(zonal.ZonalError, match="statistique"):
            zonal.zonal_stats(ds, [], stats=["median"])


def test_to_cog_converts_plain_tiff_and_passes_valid_cog(tmp_path):
    raw, cog, again = (str(tmp_path / n) for n in ("raw.tif", "cog.tif", "again.tif"))
    write_tif(raw, size=600)
    assert ingest.to_cog(raw, cog) is True
    assert ingest.to_cog(cog, again) is False
    meta = ingest.read_metadata(cog)
    assert meta.srid == 4326 and (meta.width, meta.height) == (600, 600)
    assert meta.bounds == pytest.approx([2.0, 43.0, 8.0, 49.0])
    assert meta.bands[0]["index"] == 1 and meta.nodata == -9999.0


def test_to_cog_rejects_missing_crs_and_garbage(tmp_path):
    raw = str(tmp_path / "nocrs.tif")
    write_tif(raw, crs=None)
    with pytest.raises(ingest.RasterIngestError):
        ingest.to_cog(raw, str(tmp_path / "o.tif"))
    junk = tmp_path / "junk.tif"
    junk.write_bytes(b"not a raster")
    with pytest.raises(ingest.RasterIngestError):
        ingest.to_cog(str(junk), str(tmp_path / "o2.tif"))
