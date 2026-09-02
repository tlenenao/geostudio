# SPDX-License-Identifier: Apache-2.0
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.roles.repository import get_role
from app.users.models import User


def require_privilege(session: Session, user: User, privilege: str) -> None:
    role = get_role(session, tenant_id=user.tenant_id, role_id=user.role_id)
    if role is None or privilege not in role.privileges:
        raise HTTPException(status_code=403, detail=f"privilege '{privilege}' required")
