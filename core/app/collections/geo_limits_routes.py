# SPDX-License-Identifier: Apache-2.0
"""Administration des limites géographiques de lecture (GAP-27, REV-121).

Une limite = polygone WGS84 attaché à (collection × rôle|groupe). Écriture
réservée à `admin.collections.manage` ; l'application de la limite se fait en
lecture (RLS restrictive `geo_limit`, cf. app.collections.ddl) — jamais ici."""

from datetime import UTC
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collections import repository as repo
from app.collections.ddl import ensure_geo_limit_policy
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.models import Role
from app.roles.privileges import Privilege
from app.sharing import geo_limits as geo
from app.sharing.models import Group

router = APIRouter(tags=["geo-limits"])

TargetType = Literal["role", "group"]


class GeoLimitPut(BaseModel):
    geometry: dict


class GeoLimitRead(BaseModel):
    targetType: TargetType
    targetId: str
    geometry: dict
    updatedAt: str


class GeoLimitList(BaseModel):
    limits: list[GeoLimitRead]


def _read(row) -> GeoLimitRead:
    ts = row.updated_at if row.updated_at.tzinfo else row.updated_at.replace(tzinfo=UTC)
    return GeoLimitRead(
        targetType=row.target_type,
        targetId=row.target_id,
        geometry=row.geometry,
        updatedAt=ts.isoformat(),
    )


def _admin_collection(session: Session, user, collection_id: str):
    require_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
    col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


def _require_target(session: Session, tenant_id: str, target_type: str, target_id: str) -> None:
    model = Role if target_type == "role" else Group
    found = session.execute(
        select(model.id).where(model.id == target_id, model.tenant_id == tenant_id)
    ).first()
    if found is None:
        raise HTTPException(status_code=404, detail=f"{target_type} not found")


@router.get("/collections/{collection_id}/geo-limits", response_model=GeoLimitList)
def list_geo_limits(
    collection_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    col = _admin_collection(session, user, collection_id)
    rows = geo.list_limits(session, tenant_id=user.tenant_id, collection_id=col.id)
    return GeoLimitList(limits=[_read(r) for r in rows])


@router.put(
    "/collections/{collection_id}/geo-limits/{target_type}/{target_id}",
    response_model=GeoLimitRead,
)
def put_geo_limit(
    collection_id: str,
    target_type: TargetType,
    target_id: str,
    body: GeoLimitPut,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
):
    col = _admin_collection(session, user, collection_id)
    _require_target(session, user.tenant_id, target_type, target_id)
    if target_type == "role":
        role = session.get(Role, target_id)
        if role is not None and Privilege.ADMIN_COLLECTIONS_MANAGE.value in role.privileges:
            raise HTTPException(
                status_code=422,
                detail="a role holding admin.collections.manage is never geo-limited "
                "(administrator exemption)",
            )
    try:
        geometry = geo.validate_limit_geometry(body.geometry)
    except geo.InvalidGeoLimit as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    # La policy RLS est posée à l'enregistrement de la collection ; une collection
    # antérieure à cette fonctionnalité la reçoit ici (idempotent). Sans elle (pas
    # de géométrie, hors PostGIS) la limite ne serait jamais appliquée : refus.
    if not ensure_geo_limit_policy(session, col.table_name):
        raise HTTPException(
            status_code=422, detail="geo limits require a geometry column on PostGIS"
        )
    row = geo.upsert_limit(
        session,
        tenant_id=user.tenant_id,
        collection_id=col.id,
        target_type=target_type,
        target_id=target_id,
        geometry=geometry,
        actor_id=user.id,
    )
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="geo_limit.set",
        object_type="collection",
        object_id=col.id,
        payload={"targetType": target_type, "targetId": target_id},
    )
    return _read(row)


@router.delete("/collections/{collection_id}/geo-limits/{target_type}/{target_id}", status_code=204)
def delete_geo_limit(
    collection_id: str,
    target_type: TargetType,
    target_id: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> None:
    col = _admin_collection(session, user, collection_id)
    ok = geo.delete_limit(
        session,
        tenant_id=user.tenant_id,
        collection_id=col.id,
        target_type=target_type,
        target_id=target_id,
    )
    if not ok:
        raise HTTPException(status_code=404, detail="geo limit not found")
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="geo_limit.delete",
        object_type="collection",
        object_id=col.id,
        payload={"targetType": target_type, "targetId": target_id},
    )
