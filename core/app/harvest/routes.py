# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.harvest import repository as repo
from app.harvest.connectors import get_connector
from app.harvest.jobs import run_harvest_task
from app.harvest.schemas import HarvestSourceCreate, HarvestSourcePatch
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

router = APIRouter()


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _source_json(source) -> dict:
    return {
        "id": source.id, "type": source.type, "url": source.url, "mode": source.mode,
        "enabled": source.enabled, "intervalMinutes": source.interval_minutes,
        "lastRunAt": source.last_run_at.isoformat() if source.last_run_at else None,
        "lastStatus": source.last_status, "lastError": source.last_error,
    }


def _check_copy_support(type_: str, mode: str) -> None:
    if mode != "copy":
        return
    connector = get_connector(type_)
    if not connector.supports_copy:
        raise HTTPException(status_code=400, detail=f"connector {type_!r} does not support copy mode")


def get_task_deferrer():  # overridé en test
    def deferrer(source_id: str, tenant_id: str) -> None:
        run_harvest_task.defer(source_id=source_id, tenant_id=tenant_id)
    return deferrer


@router.post("/harvest/sources", status_code=201)
def create_source(
    body: HarvestSourceCreate,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    _check_copy_support(body.type, body.mode)
    source = repo.create_source(
        session, tenant_id=user.tenant_id, owner_id=user.id, type=body.type,
        url=body.url, mode=body.mode, enabled=body.enabled, interval_minutes=body.intervalMinutes,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.create", object_type="harvest_source", object_id=source.id,
        payload={"type": source.type, "url": source.url},
    )
    return _source_json(source)


@router.get("/harvest/sources")
def list_sources(user: User = Depends(get_current_user), session: Session = Depends(get_session)):
    _require_admin(user)
    sources = repo.list_sources(session, tenant_id=user.tenant_id)
    return {"sources": [_source_json(s) for s in sources]}


@router.get("/harvest/layers")
def list_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, tiles_url, _layer_kind in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title, "kind": "raster", "tilesUrl": tiles_url})
    return {"layers": layers}


@router.get("/harvest/feature-layers")
def list_feature_layers(
    q: str | None = None,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    rows = repo.list_feature_layer_records(session, tenant_id=user.tenant_id, q=q)
    layers = []
    for item_id, title, _external_url in rows:
        facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
        if facts is None or not can(session, user_id=user.id, action="read", item=facts):
            continue
        layers.append({"id": item_id, "title": title})
    return {"layers": layers}


@router.get("/harvest/sources/{source_id}")
def get_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    return _source_json(source)


@router.patch("/harvest/sources/{source_id}")
def patch_source(
    source_id: str, body: HarvestSourcePatch,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    fields = body.model_dump(exclude_unset=True)
    if "intervalMinutes" in fields:
        fields["interval_minutes"] = fields.pop("intervalMinutes")
    if fields.get("mode") == "copy":
        _check_copy_support(source.type, "copy")
    repo.update_source(session, source, **fields)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.update", object_type="harvest_source", object_id=source.id,
        payload={"fields": list(fields)},
    )
    return _source_json(source)


@router.delete("/harvest/sources/{source_id}", status_code=204)
def delete_source(
    source_id: str, user: User = Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.delete", object_type="harvest_source", object_id=source.id, payload={},
    )
    repo.delete_source(session, source)


@router.post("/harvest/sources/{source_id}/run", status_code=202)
def run_source(
    source_id: str,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
    defer_task=Depends(get_task_deferrer),
):
    _require_admin(user)
    source = repo.get_source(session, tenant_id=user.tenant_id, source_id=source_id)
    if source is None:
        raise HTTPException(status_code=404, detail="harvest source not found")
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="harvest_source.run", object_type="harvest_source", object_id=source.id, payload={},
    )
    session.commit()
    defer_task(source.id, user.tenant_id)
    return {"status": "queued"}
