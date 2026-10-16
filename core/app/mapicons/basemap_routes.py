# SPDX-License-Identifier: Apache-2.0
"""Fonds de carte partagés par tenant (REV-367 i / ARC-09a) : un administrateur
ajoute un fond (style MapLibre ou tuiles raster XYZ/WMTS-REST), tous les
utilisateurs du tenant le voient dans les sélecteurs de fond. Son origine entre
dans l'allowlist CSP dynamique (app.security.service)."""

import uuid
from typing import Annotated
from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.mapicons.models import TenantBasemap
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter()

XYZ_PREFIX = "xyz:"


class BasemapCreate(BaseModel):
    label: Annotated[str, Field(min_length=1, max_length=120)]
    style: Annotated[str, Field(min_length=1, max_length=2000)]

    @field_validator("label")
    @classmethod
    def _strip_label(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("label must not be blank")
        return v

    @field_validator("style")
    @classmethod
    def _valid_style(cls, v: str) -> str:
        """`https://…/style.json`, ou `xyz:https://…/{z}/{x}/{y}.png` (gabarit raster)."""
        v = v.strip()
        url = v.removeprefix(XYZ_PREFIX)
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("style must be an http(s) URL (optionally prefixed with 'xyz:')")
        if v.startswith(XYZ_PREFIX) and not all(k in url for k in ("{z}", "{x}", "{y}")):
            raise ValueError("an xyz: basemap needs a {z}/{x}/{y} tile template")
        return v


class BasemapOut(BaseModel):
    id: str
    label: str
    style: str


def _out(b: TenantBasemap) -> BasemapOut:
    return BasemapOut(id=b.id, label=b.label, style=b.style)


@router.get("/basemaps")
def list_basemaps(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> list[BasemapOut]:
    rows = session.scalars(
        select(TenantBasemap)
        .where(TenantBasemap.tenant_id == user.tenant_id)
        .order_by(TenantBasemap.label, TenantBasemap.id)
    ).all()
    return [_out(b) for b in rows]


@router.post("/basemaps", status_code=201)
def create_basemap(
    body: BasemapCreate,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> BasemapOut:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    basemap = TenantBasemap(
        id=uuid.uuid4().hex,
        tenant_id=user.tenant_id,
        label=body.label,
        style=body.style,
        created_by=user.id,
    )
    session.add(basemap)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="basemap.create",
        object_type="basemap",
        object_id=basemap.id,
        payload={"label": basemap.label},
    )
    return _out(basemap)


@router.delete("/basemaps/{basemap_id}", status_code=204)
def delete_basemap(
    basemap_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> None:
    require_privilege(session, user, Privilege.SETTINGS_INSTANCE_MANAGE.value)
    basemap = session.scalar(
        select(TenantBasemap).where(
            TenantBasemap.tenant_id == user.tenant_id, TenantBasemap.id == basemap_id
        )
    )
    if basemap is None:
        raise HTTPException(status_code=404, detail="basemap not found")
    label = basemap.label
    session.delete(basemap)
    session.flush()
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="basemap.delete",
        object_type="basemap",
        object_id=basemap_id,
        payload={"label": label},
    )
