# SPDX-License-Identifier: Apache-2.0
"""Routeur DCAT-AP (lecture seule) monté sous /dcat. Réutilise les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant) et l'emprise STAC (app.stac.extent.estimated_bbox_4326) —
aucun nouveau calcul d'emprise, aucune écriture, aucune surface shell/MCP."""

from datetime import UTC

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.repository import list_visible_collections
from app.collections.routes import get_introspector, get_readable_collection
from app.db import get_session
from app.dcat import serializers
from app.features.routes import get_rls_scope
from app.roles.guards import has_privilege
from app.roles.privileges import Privilege
from app.stac.extent import estimated_bbox_4326
from app.tenants.models import Tenant

router = APIRouter(prefix="/dcat", tags=["dcat"])

MEDIA_TYPE = "application/ld+json"


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return estimated_bbox_4326


def _base(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def _rfc3339(dt) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")


def _resolve_tenant(session: Session, user) -> Tenant:
    if user is not None:
        return session.get(Tenant, user.tenant_id)
    from app.tenants.repository import get_or_create_default_tenant

    return get_or_create_default_tenant(session)


def _visible_collections(session: Session, user, tenant: Tenant):
    cols = list_visible_collections(
        session,
        tenant_id=tenant.id,
        user_id=user.id if user else None,
        can_see_all=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )
    return sorted(cols, key=lambda c: c.id)


def _dataset_doc(*, base, col, introspect, bbox_provider, rls, session, publisher_name):
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        bbox = bbox_provider(session, info)
    return serializers.dataset(
        base=base,
        collection_id=col.id,
        title=col.title,
        description=col.description,
        created_at=_rfc3339(col.created_at),
        updated_at=_rfc3339(col.updated_at),
        is_public=col.is_public,
        publisher_name=publisher_name,
        bbox=bbox,
    )


@router.get("/catalog")
def get_catalog(
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    cols = _visible_collections(session, user, tenant)
    datasets = [
        _dataset_doc(
            base=base,
            col=col,
            introspect=introspect,
            bbox_provider=bbox_provider,
            rls=rls,
            session=session,
            publisher_name=tenant.name,
        )
        for col in cols
    ]
    doc = serializers.catalog(base=base, tenant_name=tenant.name, datasets=datasets)
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)


@router.get("/datasets/{collection_id}")
def get_dataset(
    collection_id: str,
    request: Request,
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    col = get_readable_collection(session, user, collection_id)  # 404 non-fuyant
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    doc = _dataset_doc(
        base=base,
        col=col,
        introspect=introspect,
        bbox_provider=bbox_provider,
        rls=rls,
        session=session,
        publisher_name=tenant.name,
    )
    doc["@context"] = serializers.CONTEXT
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)
