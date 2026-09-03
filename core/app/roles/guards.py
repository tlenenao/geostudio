# SPDX-License-Identifier: Apache-2.0
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def has_privilege(session: Session, user: User, privilege: str) -> bool:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    return role is not None and privilege in role.privileges


def require_privilege(session: Session, user: User, privilege: str) -> None:
    if not has_privilege(session, user, privilege):
        raise HTTPException(status_code=403, detail=f"privilege '{privilege}' required")
