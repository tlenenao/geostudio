from typing import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as repo
from app.collections.introspection import (
    Introspector, TableNotFound, UnsupportedTable,
)
from app.collections.schema_json import table_info_to_schema
from app.collections.schemas import CollectionCreate, CollectionPatch
from app.db import core_table_names, get_session
from app.sharing.authorization import can
from app.sharing.schemas import Sharing

router = APIRouter()

# Tables système PostGIS : de simples tables Postgres ordinaires (PK simple,
# pas de tenant_id) qui passeraient toutes les autres gardes. Les enregistrer
# comme collection ALTERerait une table système partagée par toute l'instance
# PostGIS (tenant_id, RLS, grants) — à exclure explicitement, la denylist
# core_table_names() ne les connaît pas (ce ne sont pas des modèles du cœur).
POSTGIS_SYSTEM_TABLES = frozenset({
    "spatial_ref_sys", "geometry_columns", "geography_columns",
})


def _core_tables() -> frozenset[str]:
    # Calculé à la requête, jamais à l'import : au moment où main.py importe ce
    # module, app.items/app.configs ne sont pas encore importés et
    # Base.metadata serait incomplet (denylist trouée).
    return core_table_names() | {"alembic_version"} | POSTGIS_SYSTEM_TABLES


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
    if body.tableName in _core_tables():
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


@router.get("/collections/{collection_id}/schema")
def get_collection_schema(
    collection_id: str,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
):
    col = _get_readable(session, user, collection_id)
    info = introspect(session, col.table_name)
    return table_info_to_schema(info)


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


def _require_share(session, user, col) -> None:
    if not can(session, user_id=user.id, action="share", item=repo.get_access_facts(col),
               kind="collection", actor_is_admin=user.is_admin):
        raise HTTPException(status_code=403, detail="share access required")


@router.get("/collections/{collection_id}/sharing", response_model=Sharing)
def get_sharing(
    collection_id: str, user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    _require_share(session, user, col)
    shares = repo.get_collection_sharing(session, tenant_id=user.tenant_id, collection_id=col.id)
    return {"public": col.is_public,
            "groups": [{"groupId": s.group_id, "role": s.role} for s in shares]}


@router.put("/collections/{collection_id}/sharing", response_model=Sharing)
def put_sharing(
    collection_id: str, body: Sharing,
    user=Depends(get_current_user), session: Session = Depends(get_session),
):
    col = _get_readable(session, user, collection_id)
    _require_share(session, user, col)
    ok = repo.set_collection_sharing(
        session, tenant_id=user.tenant_id, collection_id=col.id,
        groups=[(g.groupId, g.role) for g in body.groups],
    )
    if not ok:
        # Même statut/détail que le chemin items (items/routes.py) : ne jamais
        # révéler l'existence d'un groupe d'un autre tenant. is_public n'est
        # muté qu'après validation — rien n'a changé à ce stade.
        raise HTTPException(status_code=404, detail="group not found")
    col.is_public = body.public
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="collection.share", object_type="collection", object_id=col.id,
                payload={"public": body.public,
                         "groups": [g.model_dump() for g in body.groups]})
    return {"public": col.is_public,
            "groups": [{"groupId": g.groupId, "role": g.role} for g in body.groups]}
