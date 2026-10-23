# SPDX-License-Identifier: Apache-2.0
"""POST /v1/routing/{route,isochrone,service-area,matrix} (ARC-34, ADR 0025) : proxy
authentifié vers Valhalla. Privilège `analytics.view`, 100 appels/min/utilisateur (429),
une ligne d'audit par appel accepté par le limiteur (un service absent est tracé aussi),
503 RFC 7807 quand le service est absent ou injoignable."""

from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import privilege_required_error
from app.roles.privileges import Privilege
from app.routing.client import (
    MAX_CONTOURS,
    MAX_MATRIX_SIDE,
    MAX_ORIGINS,
    MAX_ROUTE_POINTS,
    RateLimited,
    RoutingError,
    RoutingUnavailable,
    Valhalla,
    get_routing,
    rate_window,
)
from app.routing.gate import can_route
from app.users.models import User

router = APIRouter(prefix="/routing", tags=["routing"])


class Point(BaseModel):
    lon: float = Field(ge=-180, le=180)
    lat: float = Field(ge=-90, le=90)


Costing = Annotated[str, Field(pattern="^(auto|bicycle|pedestrian|truck|bus|motor_scooter)$")]
Minutes = Annotated[list[float], Field(min_length=1, max_length=MAX_CONTOURS)]


class RouteRequest(BaseModel):
    points: list[Point] = Field(min_length=2, max_length=MAX_ROUTE_POINTS)
    costing: Costing = "auto"


class IsochroneRequest(BaseModel):
    origin: Point
    minutes: Minutes
    costing: Costing = "auto"


class ServiceAreaRequest(BaseModel):
    origins: list[Point] = Field(min_length=1, max_length=MAX_ORIGINS)
    minutes: Minutes
    costing: Costing = "auto"


class MatrixRequest(BaseModel):
    sources: list[Point] = Field(min_length=1, max_length=MAX_MATRIX_SIDE)
    targets: list[Point] = Field(min_length=1, max_length=MAX_MATRIX_SIDE)
    costing: Costing = "auto"


def serve(
    session: Session,
    user: User,
    action: str,
    audit: dict,
    call: Callable[[Valhalla], dict],
) -> Any:
    """Porte commune : privilège -> appel Valhalla ; l'audit (commité) est écrit une fois le
    limiteur passé (débit compté par requête amont, via `throttle`), ou si le service est absent."""
    if not can_route(session, user):
        raise privilege_required_error(Privilege.ANALYTICS_VIEW.value)
    audited = False

    def audit_once() -> None:
        nonlocal audited
        if audited:
            return
        audited = True
        write_audit(
            session,
            tenant_id=user.tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action=f"routing.{action}",
            object_type="routing",
            object_id=action,
            payload=audit,
        )
        session.commit()

    def throttle() -> None:
        rate_window.check(user.id)  # RateLimited : aucun audit pour un appel refusé (REV-401)
        audit_once()

    try:
        return call(get_routing(throttle))
    except RateLimited:
        raise HTTPException(
            status_code=429, detail="Trop de requêtes de routage, réessayez dans une minute."
        ) from None
    except RoutingUnavailable as exc:
        audit_once()  # service absent : tracé aussi
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except (RoutingError, ValueError) as exc:
        audit_once()
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _pts(points: list[Point]) -> list[dict]:
    return [p.model_dump() for p in points]


@router.post("/route")
def route(
    body: RouteRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    return serve(
        session,
        user,
        "route",
        {"costing": body.costing, "points": len(body.points)},
        lambda v: v.route(_pts(body.points), body.costing),
    )


@router.post("/isochrone")
def isochrone(
    body: IsochroneRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    return serve(
        session,
        user,
        "isochrone",
        {"costing": body.costing, "contours": len(body.minutes)},
        lambda v: v.isochrone(body.origin.model_dump(), body.minutes, body.costing),
    )


@router.post("/service-area")
def service_area(
    body: ServiceAreaRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    return serve(
        session,
        user,
        "service-area",
        {"costing": body.costing, "origins": len(body.origins), "contours": len(body.minutes)},
        lambda v: v.service_area(_pts(body.origins), body.minutes, body.costing),
    )


@router.post("/matrix")
def matrix(
    body: MatrixRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> dict:
    return serve(
        session,
        user,
        "matrix",
        {"costing": body.costing, "sources": len(body.sources), "targets": len(body.targets)},
        lambda v: v.matrix(_pts(body.sources), _pts(body.targets), body.costing),
    )
