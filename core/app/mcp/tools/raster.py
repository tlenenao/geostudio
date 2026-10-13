# SPDX-License-Identifier: Apache-2.0
"""Tool MCP raster_zonal_stats (ARC-33) : jumeau de POST /v1/raster/{id}/zonal-stats pour des
polygones GeoJSON (les polygones d'une collection restent REST). Mêmes contrôles : `can(read)`
sur l'item, refus fail-closed si l'appelant est limité géographiquement sur la collection de
référence, plafond de 1000 polygones. Lecture seule ; absent de l'allowlist du copilote."""

import json

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.auth.dependency import is_raster_enabled
from app.db import request_scoped_session
from app.mcp.tools.identity import (
    McpToolError,
    require_access,
    resolve_actor,
    user_geo_limits,
)
from app.raster import repository as raster_repo
from app.raster import zonal
from app.raster.service import open_asset, polygons_from_geojson, refuse_if_raster_geo_limited
from app.sharing.geo_limits import GeoLimitRefused


def register(server: FastMCP, session_factory) -> None:
    @server.tool(structured_output=False)
    async def raster_zonal_stats(
        ctx: Context, item_id: str, geojson: dict, band: int = 1, stats: list[str] | None = None
    ) -> str:
        """Zonal statistics of a raster item (COG) over GeoJSON polygons (Polygon/MultiPolygon,
        Feature or FeatureCollection, WGS84, at most 1000). `stats` among count, min, max, mean,
        sum, std (default all). Returns {"count", "results": [{"id", "stats"}]}. Read-only."""
        if not is_raster_enabled():
            raise ValueError("raster capability is disabled")
        access_token = get_access_token()
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, access_token)
            require_access(session, user=user, item_id=item_id, action="read")
            asset = raster_repo.get_asset(session, tenant_id=user.tenant_id, item_id=item_id)
            if asset is None:
                raise ValueError("item not found")
            try:
                refuse_if_raster_geo_limited(
                    session, asset, user_geo_limits(session, user), "raster zonal statistics"
                )
            except GeoLimitRefused as exc:
                raise McpToolError(403, exc.detail) from exc
            polys = polygons_from_geojson(geojson)
            try:
                with open_asset(asset) as ds:
                    res = zonal.zonal_stats(
                        ds,
                        [g for _, g in polys],
                        band=band,
                        stats=stats or list(zonal.STATS),
                    )
            except zonal.ZonalError as exc:
                raise ValueError(str(exc)) from exc
            rows = [{"id": fid, "stats": s} for (fid, _), s in zip(polys, res, strict=True)]
            return json.dumps({"count": len(polys), "results": rows})
