# SPDX-License-Identifier: Apache-2.0
"""Lecture du journal d'entité (ARC-15). La restauration d'une version vit dans
app.features.routes (elle réutilise la logique du PUT, couche au-dessus)."""

from datetime import UTC, datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.collections.routes import get_collection_for_read
from app.collections.sensitive import masked_fields_for
from app.configs.geo_limits_dep import get_request_geo_limits
from app.db import get_session
from app.history import service
from app.history.models import EntityHistory
from app.sharing.geo_limits import refuse_if_geo_limited
from app.users.models import User

router = APIRouter()

MAX_CHANGES = 1000


def _iso(dt: datetime) -> str:
    return dt.replace(tzinfo=None).isoformat() + "Z"


def _actors(session: Session, rows: list[EntityHistory]) -> dict[str, str]:
    ids = {r.actor_id for r in rows if r.actor_id}
    if not ids:
        return {}
    users = session.execute(select(User.id, User.username).where(User.id.in_(ids))).all()
    return {u.id: u.username for u in users}


def _row_json(r: EntityHistory, names: dict[str, str], masked: frozenset[str]) -> dict:
    return {
        "id": r.id,
        "fid": r.fid,
        "op": r.op,
        "at": _iso(r.created_at),
        "actor": (
            {"id": r.actor_id, "username": names.get(r.actor_id, "")} if r.actor_id else None
        ),
        "before": service.mask_snapshot(r.before, masked),
        "after": service.mask_snapshot(r.after, masked),
    }


@router.get("/collections/{collection_id}/items/{fid}/history")
def entity_history(
    collection_id: str,
    fid: str,
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
):
    col = get_collection_for_read(session, user, collection_id)
    # Fail-closed : le journal n'est pas découpé par limite géographique.
    refuse_if_geo_limited(geo_limits, col.table_name, path="entity history")
    rows = service.list_entity_history(
        session, tenant_id=col.tenant_id, collection_id=col.id, fid=fid
    )
    masked = masked_fields_for(session, user, col)
    names = _actors(session, rows)
    return {"versions": [_row_json(r, names, masked) for r in rows]}


@router.get("/collections/{collection_id}/changes")
def collection_changes(
    collection_id: str,
    since: datetime = Query(
        ...,
        description="ISO 8601 ; changements postérieurs, avec 30 s de recouvrement "
        "(transactions commitées tardivement) : dédoublonner par `id`",
    ),
    limit: int = Query(default=200, ge=1, le=MAX_CHANGES),
    user=Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
    geo_limits=Depends(get_request_geo_limits),
):
    col = get_collection_for_read(session, user, collection_id)
    refuse_if_geo_limited(geo_limits, col.table_name, path="collection changes")
    if since.tzinfo is not None:
        since = since.astimezone(UTC).replace(tzinfo=None)
    rows = service.list_changes_since(
        session, tenant_id=col.tenant_id, collection_id=col.id, since=since, limit=limit
    )
    masked = masked_fields_for(session, user, col)
    names = _actors(session, rows)
    return {"changes": [_row_json(r, names, masked) for r in rows]}
