# SPDX-License-Identifier: Apache-2.0
"""Collecte terrain (ARC-27) : import XLSForm -> collection + App formulaire mobile, et liste
« mes saisies » (créations journalisées de l'appelant, ARC-15)."""

import json
from collections.abc import Callable

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.collect.kit import build_kit, if_none_match_hits
from app.collections.domains import check_domain_config, check_rules_config, with_attribute_rules
from app.collections.provisioning import create_empty_collection
from app.collections.routes import (
    get_collection_for_read,
    get_ddl_applier,
    get_introspector,
)
from app.collections.schemas import AttributeRule, EmptyCollectionColumn, FieldDomain
from app.collections.sensitive import masked_fields_for, may_read_sensitive
from app.configs.geo_limits_dep import get_request_geo_limits
from app.configs.service import create_config_service
from app.db import get_session
from app.history import service as history
from app.history.models import EntityHistory
from app.mcp.form_app import build_collect_config
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.sharing.geo_limits import refuse_if_geo_limited
from app.users.models import User
from app.xlsform.parser import MAX_BYTES, XlsFormError, parse_xlsform

router = APIRouter()

MAX_ENTRIES = 100


@router.post("/xlsform/import", status_code=201)
async def import_xlsform(
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect: Callable = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
):
    # Même garde que POST /collections/empty (DDL) ; la création de l'App est gardée par
    # create_config_service (privilège du kind).
    require_privilege(session, user, Privilege.DATA_MANAGE.value)
    content = await file.read(MAX_BYTES + 1)
    try:
        plan = parse_xlsform(content)
    except XlsFormError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    col = create_empty_collection(
        session,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        title=plan.title,
        columns=[EmptyCollectionColumn(**c) for c in plan.columns],
        geometry_type=plan.geometry_type,  # type: ignore[arg-type]
        srid=4326 if plan.geometry_type else None,
        introspect=introspect,
        apply_ddl=apply_ddl,
    )
    domains = {
        k: FieldDomain(**v).model_dump(exclude_none=True) for k, v in plan.field_domains.items()
    }
    rules = [AttributeRule(**r).model_dump(exclude_none=True) for r in plan.attribute_rules]
    info = with_attribute_rules(introspect(session, col.table_name), col)
    problems = check_domain_config(info, domains, {}) + check_rules_config(info, rules)
    if problems:
        raise HTTPException(status_code=422, detail="; ".join(problems))
    col.attachment_fields = plan.attachment_fields
    col.geometry_required = plan.geometry_required
    col.field_domains = domains
    col.attribute_rules = rules
    session.flush()

    config = build_collect_config(
        collection_id=col.id, form_fields=plan.form_fields, geometry_type=plan.geometry_type
    )
    created = create_config_service(session, config, title=plan.title, user=user)
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="xlsform.import",
        object_type="collection",
        object_id=col.id,
        payload={"itemId": created.item.id, "questions": len(plan.form_fields)},
    )
    return {
        "collectionId": col.id,
        "itemId": created.item.id,
        "title": plan.title,
        "report": [r.as_dict() for r in plan.report],
    }


@router.get("/collections/{collection_id}/my-entries")
def my_entries(
    collection_id: str,
    limit: int = Query(default=20, ge=1, le=MAX_ENTRIES),
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
):
    """Saisies créées par l'appelant (journal d'entité), les plus récentes d'abord, hors
    enregistrements supprimés depuis."""
    col = get_collection_for_read(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="my entries")
    deleted = select(EntityHistory.fid).where(
        EntityHistory.collection_id == col.id, EntityHistory.op == "delete"
    )
    rows = session.scalars(
        select(EntityHistory)
        .where(
            EntityHistory.tenant_id == col.tenant_id,
            EntityHistory.collection_id == col.id,
            EntityHistory.actor_id == user.id,
            EntityHistory.op == "create",
            EntityHistory.fid.not_in(deleted),
        )
        .order_by(EntityHistory.id.desc())
        .limit(limit)
    ).all()
    masked = masked_fields_for(session, user, col)
    return {
        "entries": [
            {
                "fid": r.fid,
                "at": r.created_at.replace(tzinfo=None).isoformat() + "Z",
                "properties": (history.mask_snapshot(r.after, masked) or {}).get("properties", {}),
            }
            for r in rows
        ]
    }


@router.get("/collections/{collection_id}/collect-kit")
def collect_kit(
    collection_id: str,
    request: Request,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    introspect: Callable = Depends(get_introspector),
):
    """Kit de collecte hors-ligne (L8) : schéma, domaines, règles, champs média typés. Droit de
    LECTURE requis ; champs sensibles masqués comme `GET .../schema` (GAP-22). L'autorisation
    d'écriture reste vérifiée à l'envoi : le client ne s'y fie jamais. ETag fort + 304."""
    col = get_collection_for_read(session, user, collection_id)
    kit = build_kit(
        session,
        col,
        introspect,
        sees_sensitive=may_read_sensitive(session, user, col),
        public=False,
    )
    headers = {"ETag": f'"{kit["etag"]}"', "Cache-Control": "private, no-cache"}
    if if_none_match_hits(request.headers.get("if-none-match"), kit["etag"]):
        return Response(status_code=304, headers=headers)
    return Response(content=json.dumps(kit), media_type="application/json", headers=headers)
