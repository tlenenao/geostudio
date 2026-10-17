# SPDX-License-Identifier: Apache-2.0
"""AUD-127 : NTF -> WGS84 exige la grille IGN (sinon Helmert ~2 m silencieux)."""

import io
import warnings

import geopandas as gpd
import pytest
from pyproj.transformer import TransformerGroup
from shapely.geometry import Point

from app.ingestion.parsers import IngestionParseError, _crs_transform, parse_geoparquet

WITH_GRID = (2.3365241427675185, 48.85034948131713)  # (600000, 2428000) EPSG:27572


def _grid_available() -> bool:
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return TransformerGroup(27572, 4171, always_xy=True).best_available


def test_lambert93_unchanged():
    lon, lat = _crs_transform("EPSG:2154")(700000.0, 6600000.0)
    assert (round(lon, 6), round(lat, 6)) == (3.0, 46.5)


@pytest.mark.skipif(_grid_available(), reason="grille installée : branche couverte ci-dessous")
def test_ntf_without_grid_is_refused():
    with pytest.raises(IngestionParseError, match="fr_ign_gr3df97a.tif"):
        _crs_transform("EPSG:27572")


@pytest.mark.skipif(not _grid_available(), reason="grille IGN absente (python -m pyproj sync)")
def test_ntf_with_grid_is_metric():
    lon, lat = _crs_transform("EPSG:27572")(600000.0, 2428000.0)
    assert lon == pytest.approx(WITH_GRID[0], abs=1e-7)
    assert lat == pytest.approx(WITH_GRID[1], abs=1e-7)


def test_ntf_geoparquet_follows_the_same_rule():
    """Jumelle : parse_geoparquet reprojetait par gdf.to_crs (Helmert silencieux)."""
    buf = io.BytesIO()
    gpd.GeoDataFrame({"a": [1]}, geometry=[Point(600000, 2428000)], crs=27572).to_parquet(buf)
    if not _grid_available():
        with pytest.raises(IngestionParseError, match="fr_ign_gr3df97a.tif"):
            list(parse_geoparquet(buf.getvalue()))
        return
    [(geom, _props)] = list(parse_geoparquet(buf.getvalue()))
    assert geom.x == pytest.approx(WITH_GRID[0], abs=1e-7)
    assert geom.y == pytest.approx(WITH_GRID[1], abs=1e-7)
