# SPDX-License-Identifier: Apache-2.0
"""Routes de conformité RGPD (SP-58) : anonymisation d'utilisateur (Tâche 7)
et purge de tenant (Tâches 9-10) — regroupées dans le même module pour
garder les deux opérations de conformité au même endroit (décision de la
Tâche 7, documentée dans le message de commit)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.compliance.service import (
    AnonymizationLockoutError,
    UserAlreadyErasedError,
    anonymize_user,
)
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.users.models import User

router = APIRouter(prefix="/compliance")


@router.post("/users/{user_id}/erase", status_code=204)
def erase_user(
    user_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> None:
    target_id = user.id if user_id == "me" else user_id
    if target_id != user.id:
        # Un autre utilisateur du même tenant : requiert admin.users.manage
        # (déjà utilisé par UsersAdminPage, cf. CLAUDE.md SP-38) — pas de
        # nouveau privilège nécessaire pour ce cas (spec §3.2).
        require_privilege(session, user, Privilege.ADMIN_USERS_MANAGE.value)
    try:
        anonymize_user(session, tenant_id=user.tenant_id, user_id=target_id, actor_id=user.id)
        session.commit()
    except LookupError as exc:
        # Jamais d'anonymisation cross-tenant, même avec le privilège —
        # anonymize_user vérifie déjà tenant_id == user.tenant_id, mais un
        # id qui n'existe pas du tout dans CE tenant lève la même erreur :
        # les deux cas sont indistinguables de l'extérieur (pas de fuite
        # d'information sur l'existence d'un compte dans un autre tenant).
        raise HTTPException(status_code=404, detail="user not found in this tenant") from exc
    except UserAlreadyErasedError as exc:
        raise HTTPException(status_code=409, detail="user already erased") from exc
    except AnonymizationLockoutError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
