# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811
"""Outil MCP raster_zonal_stats (ARC-33) : mêmes contrôles que la route REST."""

from contextlib import contextmanager

import pytest
import rasterio

from app.items import repository as items_repo
from app.raster.models import RasterAsset
from tests.raster_fixtures import write_tif
from tests.test_mcp_tools_create import (  # noqa: F401
    app_client,
    call_tool,
    call_tool_expecting_error,
)

POLY = {
    "type": "Polygon",
    "coordinates": [[[2.1, 48.5], [2.3, 48.5], [2.3, 48.7], [2.1, 48.7], [2.1, 48.5]]],
}


@pytest.fixture()
def raster(app_client, tmp_path, monkeypatch):
    monkeypatch.setenv("CORE_RASTER_ENABLED", "true")
    tif = str(tmp_path / "a.tif")
    write_tif(tif)

    @contextmanager
    def opener(asset):
        with rasterio.open(tif) as ds:
            yield ds

    monkeypatch.setattr("app.mcp.tools.raster.open_asset", opener)
    with app_client.session_factory() as s:
        item = items_repo.create_item(
            s,
            tenant_id=app_client.tenant.id,
            owner_id=app_client.mock_user.id,
            resource_type="raster",
            title="R",
        )
        s.add(
            RasterAsset(
                item_id=item.id,
                tenant_id=app_client.tenant.id,
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
        return item.id


def test_zonal_stats_over_geojson(app_client, raster):
    with app_client:
        r = call_tool(
            app_client,
            "raster_zonal_stats",
            {"item_id": raster, "geojson": POLY, "stats": ["count"]},
        )
    assert r["count"] == 1 and r["results"][0]["stats"]["count"] > 0


def test_unknown_item_and_bad_stat_are_errors(app_client, raster):
    with app_client:
        call_tool_expecting_error(
            app_client, "raster_zonal_stats", {"item_id": "nope", "geojson": POLY}
        )
        call_tool_expecting_error(
            app_client,
            "raster_zonal_stats",
            {"item_id": raster, "geojson": POLY, "stats": ["bogus"]},
        )
