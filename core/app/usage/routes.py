# SPDX-License-Identifier: Apache-2.0
"""Routes de lecture d'audit_log (GAP-03b + GAP-71/28) — jamais d'écriture,
app.audit.writer reste l'unique point d'écriture. tasks.view restreint à
soi-même ; tasks.view_all lève cette restriction."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.roles.guards import has_privilege, require_any_privilege, require_privilege
from app.roles.privileges import Privilege
from app.usage import service
from app.usage.schemas import (
    UsageActorStatRead,
    UsageResourceStatRead,
    UsageSummaryRead,
    UsageTaskPage,
    UsageTaskRead,
)
from app.users.models import User

router = APIRouter()


@router.get("/usage/tasks", response_model=UsageTaskPage)
def list_usage_tasks(
    page: int = 1,
    pageSize: int = 50,
    actorId: str | None = None,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UsageTaskPage:
    require_any_privilege(
        session, user, [Privilege.TASKS_VIEW.value, Privilege.TASKS_VIEW_ALL.value]
    )
    sees_all = has_privilege(session, user, Privilege.TASKS_VIEW_ALL.value)
    if not sees_all:
        if actorId is not None and actorId != user.id:
            raise HTTPException(status_code=403, detail="cannot view another actor's tasks")
        actorId = user.id
    rows, total = service.list_tasks(
        session,
        tenant_id=user.tenant_id,
        actor_id=actorId,
        page=page,
        page_size=min(pageSize, 200),
    )
    return UsageTaskPage(
        tasks=[
            UsageTaskRead(
                id=r.id,
                actorId=r.actor_id,
                action=r.action,
                objectType=r.object_type,
                objectId=r.object_id,
                createdAt=r.created_at.isoformat(),
            )
            for r in rows
        ],
        total=total,
        page=page,
        pageSize=pageSize,
    )


@router.get("/usage/summary", response_model=UsageSummaryRead)
def get_usage_summary(
    since: str | None = None,
    until: str | None = None,
    limit: int = 10,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> UsageSummaryRead:
    require_privilege(session, user, Privilege.TASKS_VIEW_ALL.value)
    until_dt = datetime.fromisoformat(until) if until else datetime.now(UTC)
    since_dt = datetime.fromisoformat(since) if since else until_dt - timedelta(days=30)
    summary = service.summarize(
        session, tenant_id=user.tenant_id, since=since_dt, until=until_dt, limit=limit
    )
    return UsageSummaryRead(
        byActor=[
            UsageActorStatRead(actorId=a.actor_id, actorUsername=a.actor_username, count=a.count)
            for a in summary.by_actor
        ],
        byResource=[
            UsageResourceStatRead(objectType=r.object_type, objectId=r.object_id, count=r.count)
            for r in summary.by_resource
        ],
        totalActions=summary.total_actions,
        windowStart=since_dt.isoformat(),
        windowEnd=until_dt.isoformat(),
    )
