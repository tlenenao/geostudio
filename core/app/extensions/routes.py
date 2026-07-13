from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import get_session
from app.extensions import repository as repo
from app.extensions.schemas import ExtensionCreate, ExtensionPatch
from app.tenants.repository import get_or_create_default_tenant

router = APIRouter()


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _extension_json(ext) -> dict:
    return {
        "id": ext.id, "tag": ext.tag, "label": ext.label, "moduleUrl": ext.module_url,
        "props": ext.props, "events": ext.events, "actions": ext.actions,
        "defaultSize": ext.default_size, "permissions": ext.permissions,
        "enabled": ext.enabled,
    }


@router.post("/extensions", status_code=201)
def register_extension(
    body: ExtensionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    if repo.get_extension(session, tenant_id=user.tenant_id, extension_id=body.id):
        raise HTTPException(status_code=409, detail="extension already registered")
    ext = repo.create_extension(
        session, tenant_id=user.tenant_id, owner_id=user.id, id=body.id,
        tag=body.tag, label=body.label, module_url=body.moduleUrl,
        props=[p.model_dump() for p in body.props], events=body.events, actions=body.actions,
        default_size=body.defaultSize.model_dump(), permissions=body.permissions.model_dump(),
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="extension.create", object_type="extension", object_id=ext.id,
                payload={"moduleUrl": ext.module_url})
    return _extension_json(ext)


@router.patch("/extensions/{extension_id}")
def patch_extension(
    extension_id: str, body: ExtensionPatch,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    _require_admin(user)
    ext = repo.get_extension(session, tenant_id=user.tenant_id, extension_id=extension_id)
    if not ext:
        raise HTTPException(status_code=404, detail="extension not found")
    fields = body.model_dump(exclude_unset=True)
    if "defaultSize" in fields:
        fields["default_size"] = fields.pop("defaultSize")
    if "moduleUrl" in fields:
        fields["module_url"] = fields.pop("moduleUrl")
    repo.update_extension(session, ext, **fields)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="extension.update", object_type="extension", object_id=ext.id,
                payload={"fields": list(fields)})
    return _extension_json(ext)


@router.get("/extensions")
def list_extensions(
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    exts = repo.list_active_extensions(session, tenant_id=tenant_id)
    return {"extensions": [_extension_json(e) for e in exts]}
