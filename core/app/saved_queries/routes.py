# SPDX-License-Identifier: Apache-2.0
"""Requêtes SQL Lab enregistrées (AUD-062). Privées à leur auteur ; même privilège que SQL Lab.
Le texte n'est jamais exécuté ici : l'exécution repasse par `POST /analytics/sql` (sandbox)."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.saved_queries.models import SavedQuery
from app.users.models import User

router = APIRouter()

MAX_PER_USER = 200
MAX_SQL_CHARS = 20_000


class SavedQueryBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    sql: str = Field(min_length=1, max_length=MAX_SQL_CHARS)


class SavedQueryRead(BaseModel):
    id: str
    name: str
    sql: str
    createdAt: str
    updatedAt: str


def _read(q: SavedQuery) -> SavedQueryRead:
    return SavedQueryRead(
        id=q.id,
        name=q.name,
        sql=q.sql,
        createdAt=q.created_at.isoformat(),
        updatedAt=q.updated_at.isoformat(),
    )


def _guard(session: Session, user: User) -> None:
    require_privilege(session, user, Privilege.ANALYTICS_SQL_LAB_ACCESS.value)


def _own(session: Session, user: User, query_id: str) -> SavedQuery:
    q = session.scalar(
        select(SavedQuery).where(
            SavedQuery.id == query_id,
            SavedQuery.tenant_id == user.tenant_id,
            SavedQuery.owner_id == user.id,
        )
    )
    if q is None:  # d'un autre auteur = indistinguable d'absent
        raise HTTPException(status_code=404, detail="saved query not found")
    return q


def _audit(session: Session, user: User, action: str, query_id: str, name: str) -> None:
    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action=action,
        object_type="saved_query",
        object_id=query_id,
        payload={"name": name},
    )


@router.get("/analytics/sql/saved", response_model=list[SavedQueryRead])
def list_saved_queries(
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> list[SavedQueryRead]:
    _guard(session, user)
    rows = session.scalars(
        select(SavedQuery)
        .where(SavedQuery.tenant_id == user.tenant_id, SavedQuery.owner_id == user.id)
        .order_by(SavedQuery.name)
    ).all()
    return [_read(q) for q in rows]


@router.post("/analytics/sql/saved", response_model=SavedQueryRead, status_code=201)
def create_saved_query(
    body: SavedQueryBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> SavedQueryRead:
    _guard(session, user)
    count = session.scalar(
        select(func.count())
        .select_from(SavedQuery)
        .where(SavedQuery.tenant_id == user.tenant_id, SavedQuery.owner_id == user.id)
    )
    if (count or 0) >= MAX_PER_USER:
        raise HTTPException(status_code=409, detail=f"at most {MAX_PER_USER} saved queries")
    q = SavedQuery(
        id=uuid.uuid4().hex,
        tenant_id=user.tenant_id,
        owner_id=user.id,
        name=body.name.strip(),
        sql=body.sql,
    )
    session.add(q)
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="a saved query has this name") from exc
    _audit(session, user, "saved_query.create", q.id, q.name)
    return _read(q)


@router.put("/analytics/sql/saved/{query_id}", response_model=SavedQueryRead)
def update_saved_query(
    query_id: str,
    body: SavedQueryBody,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> SavedQueryRead:
    _guard(session, user)
    q = _own(session, user, query_id)
    q.name = body.name.strip()
    q.sql = body.sql
    try:
        session.flush()
    except IntegrityError as exc:
        raise HTTPException(status_code=409, detail="a saved query has this name") from exc
    _audit(session, user, "saved_query.update", q.id, q.name)
    return _read(q)


@router.delete("/analytics/sql/saved/{query_id}", status_code=204)
def delete_saved_query(
    query_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session, scope="function"),
) -> Response:
    _guard(session, user)
    q = _own(session, user, query_id)
    name = q.name
    session.delete(q)
    _audit(session, user, "saved_query.delete", query_id, name)
    return Response(status_code=204)
