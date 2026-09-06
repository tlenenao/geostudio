# SPDX-License-Identifier: Apache-2.0
"""Routeur DCAT-AP (lecture seule) monté sous /dcat. Réutilise les portes de
permission existantes (list_visible_collections, get_readable_collection,
404 non-fuyant) et l'emprise STAC (app.stac.extent.estimated_bbox_4326) —
aucun nouveau calcul d'emprise, aucune écriture, aucune surface shell/MCP."""

import logging
from datetime import UTC

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user_optional
from app.collections.introspection import TableNotFound, UnsupportedTable
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

logger = logging.getLogger(__name__)

MEDIA_TYPE = "application/ld+json"

MAX_LIMIT = 1000
DEFAULT_LIMIT = 100


def get_bbox_provider():  # overridé en test SQLite (ST_EstimatedExtent absent)
    return estimated_bbox_4326


def _base(request: Request) -> str:
    # request.base_url ne porte jamais /v1 (juste scheme://host/) — ce
    # routeur (comme /collections, /stac) est nesté sous /v1 (SP-57b), et
    # tous les hrefs construits à partir de cette base (serializers.py)
    # référencent des routes désormais sous /v1.
    return str(request.base_url).rstrip("/") + "/v1"


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


def _resolve_bbox(session, col, *, introspect, bbox_provider, rls):
    info = introspect(session, col.table_name)
    with rls(session, col.tenant_id):
        return bbox_provider(session, info)


def _resolve_bbox_degrading(session, col, *, introspect, bbox_provider, rls):
    """Même calcul que _resolve_bbox, mais dégrade à bbox=None (au lieu de
    laisser remonter) pour TableNotFound/UnsupportedTable/DBAPIError — même
    patron que app.collections.routes.get_collection. Utilisé par
    get_catalog (pour qu'une collection cassée ne fasse pas échouer tout le
    catalogue) et par get_dataset (GAP-62, reste) pour qu'une collection
    présente mais dont la table est cassée réponde toujours 200 plutôt que
    500."""
    try:
        return _resolve_bbox(
            session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls
        )
    except (TableNotFound, UnsupportedTable, DBAPIError) as exc:
        logger.warning("dcat: extent lookup failed for collection %s: %s", col.id, exc)
        return None


def _dataset_doc(*, base, col, bbox, publisher_name):
    return serializers.dataset(
        base=base,
        collection_id=col.id,
        title=col.title,
        description=col.description,
        created_at=_rfc3339(col.created_at),
        updated_at=_rfc3339(col.updated_at),
        is_public=col.is_public,
        publisher_name=col.producer or publisher_name,
        bbox=bbox,
        license=col.license,
        license_uri=col.license_uri,
        language=col.language,
        update_frequency=col.update_frequency,
        lineage=col.lineage,
        contact=col.contact,
        version=col.version,
        temporal_start=col.temporal_start.isoformat() if col.temporal_start else None,
        temporal_end=col.temporal_end.isoformat() if col.temporal_end else None,
        producer_declared=bool(col.producer),
    )


@router.get("/catalog")
def get_catalog(
    request: Request,
    limit: int = Query(DEFAULT_LIMIT, ge=1),
    offset: int = Query(0, ge=0),
    user=Depends(get_current_user_optional),
    session: Session = Depends(get_session),
    introspect=Depends(get_introspector),
    bbox_provider=Depends(get_bbox_provider),
    rls=Depends(get_rls_scope),
):
    limit = min(limit, MAX_LIMIT)
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    cols = _visible_collections(session, user, tenant)
    total = len(cols)
    cols_page = cols[offset : offset + limit]
    datasets = [
        _dataset_doc(
            base=base,
            col=col,
            bbox=_resolve_bbox_degrading(
                session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls
            ),
            publisher_name=tenant.name,
        )
        for col in cols_page
    ]
    doc = serializers.catalog(base=base, tenant_name=tenant.name, datasets=datasets)
    if offset + len(cols_page) < total:
        doc["links"] = [
            {
                "rel": "next",
                "href": str(request.url.include_query_params(limit=limit, offset=offset + limit)),
            }
        ]
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
    col = get_readable_collection(
        session,
        user,
        collection_id,
        can_manage_collections=bool(
            user and has_privilege(session, user, Privilege.ADMIN_COLLECTIONS_MANAGE.value)
        ),
    )  # 404 non-fuyant
    base = _base(request)
    tenant = _resolve_tenant(session, user)
    doc = _dataset_doc(
        base=base,
        col=col,
        bbox=_resolve_bbox_degrading(
            session, col, introspect=introspect, bbox_provider=bbox_provider, rls=rls
        ),
        publisher_name=tenant.name,
    )
    doc["@context"] = serializers.CONTEXT
    return JSONResponse(content=doc, media_type=MEDIA_TYPE)
