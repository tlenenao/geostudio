# SPDX-License-Identifier: Apache-2.0
"""Lecture agrégée d'audit_log — jamais d'écriture ici (app.audit.writer
reste l'unique point d'écriture). Deux usages : (1) journal des actions de
job d'un tenant (allowlist fixe, `list_tasks`) — donne enfin une route
réelle à tasks.view/tasks.view_all (GAP-03) ; (2) agrégats pleine largeur
sur tout audit_log (`summarize`) — vue d'usage GAP-71/GAP-28, activité par
acteur + popularité des ressources."""

from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.audit.models import AuditLog
from app.items import repository as items_repo
from app.items.models import Item
from app.sharing.authorization import decide
from app.sharing.repository import roles_for_items
from app.users.models import User

# Établi par grep exhaustif sur les sites d'appel de write_audit() (core/app/*/jobs.py,
# */routes.py, */importer.py, */service.py, mcp/tools/pipelines.py) — cf. spec §3.2
# pour la justification de chaque exclusion. Revérifié en session d'exécution du
# plan (2026-09-05) avant d'écrire cette constante :
#   grep -rn "action=" core/app --include=*.py | grep -v test \
#     | grep -oP 'action="\K[^"]+' | sort -u
JOB_AUDIT_ACTIONS: frozenset[str] = frozenset(
    {
        "ingestion.job_create",
        "pipeline.run",
        "export.create",
        "export.run",
        "appexport.create",
        "report.run",
        "report.notify",
        "alert.evaluate",
        "alert.notify",
        "harvest_source.run",
        "tileset3d.job_create",
        "terrain3d.job_create",
    }
)


def list_tasks(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None = None,
    page: int,
    page_size: int,
) -> tuple[list[AuditLog], int]:
    base = select(AuditLog).where(
        AuditLog.tenant_id == tenant_id,
        AuditLog.action.in_(JOB_AUDIT_ACTIONS),
    )
    if actor_id is not None:
        base = base.where(AuditLog.actor_id == actor_id)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.scalars(
            base.order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total


@dataclass
class ActorStat:
    actor_id: str | None
    actor_username: str | None
    count: int


@dataclass
class ResourceStat:
    object_type: str
    object_id: str
    count: int


@dataclass
class UsageSummaryData:
    by_actor: list[ActorStat] = field(default_factory=list)
    by_resource: list[ResourceStat] = field(default_factory=list)
    total_actions: int = 0


def summarize(
    session: Session,
    *,
    tenant_id: str,
    since: datetime,
    until: datetime,
    limit: int,
) -> UsageSummaryData:
    window = (
        AuditLog.tenant_id == tenant_id,
        AuditLog.created_at >= since,
        AuditLog.created_at <= until,
    )
    total_actions = session.scalar(select(func.count()).select_from(AuditLog).where(*window)) or 0

    by_actor_rows = session.execute(
        select(AuditLog.actor_id, User.username, func.count().label("n"))
        .outerjoin(User, (User.id == AuditLog.actor_id) & (User.tenant_id == AuditLog.tenant_id))
        .where(*window)
        .group_by(AuditLog.actor_id, User.username)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    by_actor = [ActorStat(actor_id=r[0], actor_username=r[1], count=r[2]) for r in by_actor_rows]

    by_resource_rows = session.execute(
        select(AuditLog.object_type, AuditLog.object_id, func.count().label("n"))
        .where(*window)
        .group_by(AuditLog.object_type, AuditLog.object_id)
        .order_by(func.count().desc())
        .limit(limit)
    ).all()
    by_resource = [
        ResourceStat(object_type=r[0], object_id=r[1], count=r[2]) for r in by_resource_rows
    ]

    return UsageSummaryData(by_actor=by_actor, by_resource=by_resource, total_actions=total_actions)


def readable_item_titles(
    session: Session, *, user: User, item_ids: Iterable[str]
) -> dict[str, str]:
    """Titres des items de `item_ids` LISIBLES par `user` (REV-285(f)) — même
    règle que GET /v1/items/{id} (propriétaire, public, publié, rôle de
    partage ; tasks.view_all n'ouvre rien). Trois requêtes quelle que soit la
    taille de la page, patron groupé de app.harvest.routes (SP-49). Un
    object_id sans item (collection, job, id supprimé) est simplement absent."""
    ids = sorted({i for i in item_ids if i})
    facts_by_id = items_repo.get_access_facts_by_ids(
        session, tenant_id=user.tenant_id, item_ids=ids
    )
    remaining = [
        item_id
        for item_id, facts in facts_by_id.items()
        if not (facts.owner_id == user.id or facts.is_public or facts.is_published)
    ]
    roles_by_id = roles_for_items(
        session, tenant_id=user.tenant_id, user_id=user.id, item_ids=remaining
    )
    readable = [
        item_id
        for item_id, facts in facts_by_id.items()
        if decide(
            action="read",
            kind="item",
            is_owner=facts.owner_id == user.id,
            is_public=facts.is_public,
            is_published=facts.is_published,
            roles=roles_by_id.get(item_id, frozenset()),
            actor_is_admin=False,
        )
    ]
    if not readable:
        return {}
    rows = session.execute(
        select(Item.id, Item.title).where(Item.tenant_id == user.tenant_id, Item.id.in_(readable))
    ).all()
    return {row.id: row.title for row in rows}
