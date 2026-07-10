from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as repo
from app.collections.introspection import (
    Introspector, TableNotFound, UnsupportedTable,
)
from app.collections.schemas import CollectionCreate, CollectionPatch
from app.db import Base, get_session
from app.sharing.authorization import can

router = APIRouter()

CORE_TABLES = frozenset(Base.metadata.tables) | {"alembic_version"}


def get_introspector() -> Introspector:  # overridé en test ; task 7 branche le vrai
    from app.collections.introspection_pg import introspect_table
    return introspect_table


def get_ddl_applier() -> Callable[[Session, str], None]:  # task 8 branche le vrai
    from app.collections.ddl import apply_collection_ddl
    return apply_collection_ddl


def _collection_json(col) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": col.editable,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
    }


def _require_admin(user) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


def _get_readable(session, user, collection_id):
    """404 avant 403 : une collection illisible est indistinguable d'une absente."""
    col = None
    if user is not None:
        col = repo.get_collection(session, tenant_id=user.tenant_id, collection_id=collection_id)
    else:
        from app.tenants.repository import get_or_create_default_tenant
        tenant = get_or_create_default_tenant(session)
        col = repo.get_collection(session, tenant_id=tenant.id, collection_id=collection_id)
    if col is None:
        raise HTTPException(status_code=404, detail="collection not found")
    readable = can(
        session, user_id=user.id if user else "", action="read",
        item=repo.get_access_facts(col), kind="collection",
        actor_is_admin=bool(user and user.is_admin),
    )
    if not readable:
        raise HTTPException(status_code=404, detail="collection not found")
    return col


@router.post("/collections", status_code=201)
def register_collection(
    body: CollectionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
):
    _require_admin(user)
    if body.tableName in CORE_TABLES:
        raise HTTPException(status_code=400, detail="core table cannot be registered")
    if repo.get_collection(session, tenant_id=user.tenant_id, collection_id=body.tableName):
        raise HTTPException(status_code=409, detail="table already registered")
    try:
        info = introspect(session, body.tableName)
    except TableNotFound:
        raise HTTPException(status_code=400, detail="table not found in schema public")
    except UnsupportedTable as exc:
        raise HTTPException(status_code=400, detail=exc.reason)
    apply_ddl(session, info.table_name)
    col = repo.create_collection(
        session, tenant_id=user.tenant_id, owner_id=user.id, table_name=info.table_name,
        title=body.title or info.table_name, description=body.description,
        is_public=body.isPublic, pk_column=info.pk_column,
        geometry_column=info.geometry_column, geometry_type=info.geometry_type,
        srid=info.srid,
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.create", object_type="collection", object_id=col.id,
                payload={"tableName": col.table_name})
    return _collection_json(col)


@router.get("/collections")
def list_collections(
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    cols = repo.list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin),
    )
    return {"collections": [_collection_json(c) for c in cols]}


@router.get("/collections/{collection_id}")
def get_collection(
    collection_id: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    return _collection_json(_get_readable(session, user, collection_id))


@router.patch("/collections/{collection_id}")
def patch_collection(
    collection_id: str, body: CollectionPatch,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    if not can(session, user_id=user.id, action="write", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="write access required")
    for attr, value in (("title", body.title), ("description", body.description),
                        ("is_public", body.isPublic), ("editable", body.editable)):
        if value is not None:
            setattr(col, attr, value)
    session.flush()
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.update", object_type="collection", object_id=col.id,
                payload=body.model_dump(exclude_none=True))
    return _collection_json(col)


@router.delete("/collections/{collection_id}", status_code=204)
def unregister_collection(
    collection_id: str,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    _require_admin(user)  # après le 404 : un non-admin qui la voit reçoit 403
    repo.delete_collection(session, col)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.delete", object_type="collection", object_id=collection_id,
                payload={})
