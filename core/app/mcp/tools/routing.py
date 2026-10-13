# SPDX-License-Identifier: Apache-2.0
"""Tools MCP de routage (ARC-34, ADR 0025) : jumeaux de POST /v1/routing/* — même client
(`app.routing.client`, garde d'egress, plafonds), même privilège `analytics.view`, même
budget 100 appels/min/utilisateur. Lecture seule ; l'audit `mcp.tool_call` est posé par le
harness. Absents de l'allowlist du copilote."""

from collections.abc import Callable

from mcp.server.auth.middleware.auth_context import get_access_token
from mcp.server.fastmcp import Context, FastMCP

from app.db import request_scoped_session
from app.mcp.tools.identity import McpToolError, resolve_actor
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.routing.client import (
    RateLimited,
    RoutingError,
    RoutingUnavailable,
    Valhalla,
    get_routing,
    rate_window,
)


def register(server: FastMCP, session_factory) -> None:
    def run(call: Callable[[Valhalla], dict]) -> dict:
        with request_scoped_session(session_factory) as session:
            user = resolve_actor(session, get_access_token())
            if not has_privilege(session, user, Privilege.ANALYTICS_VIEW.value):
                raise McpToolError(403, "privilege 'analytics.view' required")
            user_id = user.id
        try:
            rate_window.check(user_id)
        except RateLimited:
            raise McpToolError(
                429, "Trop de requêtes de routage, réessayez dans une minute."
            ) from None
        try:
            return call(get_routing())
        except RoutingUnavailable as exc:
            raise McpToolError(503, str(exc)) from None
        except (RoutingError, ValueError, KeyError, TypeError) as exc:
            raise McpToolError(422, str(exc)) from None

    @server.tool()
    async def route(ctx: Context, points: list[dict], costing: str = "auto") -> dict:
        """Compute a route through 2-20 points (each {"lon", "lat"}, WGS84). costing: auto,
        bicycle, pedestrian, truck, bus or motor_scooter. Returns {"distance_km",
        "duration_s", "geometry" (GeoJSON LineString), "legs"}. Read-only. ARC-34."""
        return run(lambda v: v.route(points, costing))

    @server.tool()
    async def isochrone(
        ctx: Context, origin: dict, minutes: list[float], costing: str = "auto"
    ) -> dict:
        """Travel-time polygons around one origin ({"lon","lat"}) for 1-4 contours of
        1-60 minutes. Returns a GeoJSON FeatureCollection (property contour_minutes).
        Read-only. ARC-34."""
        return run(lambda v: v.isochrone(origin, minutes, costing))

    @server.tool()
    async def service_area(
        ctx: Context, origins: list[dict], minutes: list[float], costing: str = "auto"
    ) -> dict:
        """Isochrones for 1-10 origins at once (features carry origin_index and
        contour_minutes). Read-only. ARC-34."""
        return run(lambda v: v.service_area(origins, minutes, costing))

    @server.tool()
    async def travel_matrix(
        ctx: Context, sources: list[dict], targets: list[dict], costing: str = "auto"
    ) -> dict:
        """Distance (km) and duration (s) between each source and each target (at most 50
        each, 1000 cells). Returns {"matrix": [[{"distance_km","duration_s"}]]}. Read-only.
        ARC-34."""
        return run(lambda v: v.matrix(sources, targets, costing))
