# SPDX-License-Identifier: Apache-2.0
"""Couche de service pour les items — extraite de app/items/routes.py
(get_item/get_sharing/set_sharing) pour être appelée à la fois par la
route REST et par le tool MCP équivalent (app/mcp/tools/catalog.py,
app/mcp/tools/sharing.py), pour la première fois partagée entre les deux
surfaces (SP-43 Étape 8). Les fonctions ci-dessous lèvent HTTPException
(comme le faisaient les routes) ; app/mcp/tools/* les attrape et les
retraduit en ValueError, même patron que les validateurs partagés déjà
existants (dataset_validation, bookmark_validation, ...)."""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.items import repository as repo
from app.items.schemas import ItemRead
from app.sharing import repository as sharing_repo
from app.sharing.authorization import can
from app.sharing.schemas import GroupShare, Sharing
from app.users.models import User


def get_item_service(session: Session, *, item_id: str, user: User) -> ItemRead:
    """Extrait de GET /items/{id} (app/items/routes.py::get_item)."""
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    result = repo.get_item(
        session, tenant_id=user.tenant_id, item_id=item_id, current_user_id=user.id
    )
    if result is None:
        raise HTTPException(status_code=404, detail="item not found")
    return result


def get_sharing_service(session: Session, *, item_id: str, user: User) -> Sharing:
    """Extrait de GET /items/{id}/sharing (app/items/routes.py::get_sharing)."""
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    shares = sharing_repo.list_shares(session, item_id=item_id)
    return Sharing(
        public=facts.is_public,
        groups=[GroupShare(groupId=s.group_id, role=s.role) for s in shares],
    )


def set_sharing_service(
    session: Session,
    *,
    item_id: str,
    user: User,
    sharing: Sharing,
    actor_kind: str = "user",
) -> None:
    """Extrait de PUT /items/{id}/sharing (app/items/routes.py::set_sharing).
    `actor_kind` distingue seulement l'auteur de la ligne d'audit ("user"
    pour la route REST, "agent" pour le tool MCP set_sharing) — même patron
    que pipelines/service.py::run_pipeline_service."""
    facts = repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    if not can(session, user_id=user.id, action="share", item=facts):
        raise HTTPException(status_code=403, detail="not allowed to share this item")

    ok = sharing_repo.replace_shares(
        session,
        tenant_id=user.tenant_id,
        item_id=item_id,
        shares=[(g.groupId, g.role) for g in sharing.groups],
    )
    if not ok:
        raise HTTPException(status_code=404, detail="group not found")
    repo.set_is_public(session, tenant_id=user.tenant_id, item_id=item_id, is_public=sharing.public)

    write_audit(
        session,
        tenant_id=user.tenant_id,
        actor_id=user.id,
        actor_kind=actor_kind,
        action="item.share",
        object_type="item",
        object_id=item_id,
        payload={"public": sharing.public, "groups": [g.model_dump() for g in sharing.groups]},
    )
