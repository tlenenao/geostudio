# SPDX-License-Identifier: Apache-2.0
from collections.abc import Sequence

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def has_privilege(session: Session, user: User, privilege: str) -> bool:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    return role is not None and privilege in role.privileges


def privilege_required_error(privilege: str) -> HTTPException:
    return HTTPException(status_code=403, detail=f"privilege '{privilege}' required")


def require_privilege(session: Session, user: User, privilege: str) -> None:
    if not has_privilege(session, user, privilege):
        raise privilege_required_error(privilege)


def require_any_privilege(session: Session, user: User, privileges: Sequence[str]) -> None:
    """Autorise si l'utilisateur porte AU MOINS UN des privilèges donnés.
    Une liste vide ne satisfait jamais (`any([])` est `False` — cohérent,
    mais vérifié explicitement par un test dédié pour ne jamais laisser un
    appelant futur croire qu'une liste vide autorise tout le monde)."""
    if not any(has_privilege(session, user, p) for p in privileges):
        joined = " ou ".join(privileges) if privileges else "(aucun privilège listé)"
        raise HTTPException(status_code=403, detail=f"privilege '{joined}' required")
