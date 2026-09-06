# SPDX-License-Identifier: Apache-2.0
"""Routes de conformité RGPD (SP-58) : anonymisation d'utilisateur (Tâche 7)
et purge de tenant (Tâches 9-10) — regroupées dans le même module pour
garder les deux opérations de conformité au même endroit (décision de la
Tâche 7, documentée dans le message de commit)."""

import uuid
from collections.abc import Callable
from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.compliance.models import PurgeReceipt
from app.compliance.service import (
    AnonymizationLockoutError,
    UserAlreadyErasedError,
    anonymize_user,
)
from app.db import get_session
from app.roles.guards import require_privilege
from app.roles.privileges import Privilege
from app.tenants.models import Tenant
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


class PurgeConfirmRequest(BaseModel):
    confirmSlug: str


class PurgeTriggeredResponse(BaseModel):
    jobId: str


class PurgeReceiptResponse(BaseModel):
    id: str
    tenantSlug: str
    requestedByUserId: str
    requestedAt: str
    completedAt: str
    counts: dict[str, Any]


def get_purge_task_deferrer() -> Callable[[str, str, str], None]:  # overridden in tests
    def deferrer(purge_id: str, tenant_id: str, requested_by_user_id: str) -> None:
        from app.compliance.jobs import purge_tenant_task

        purge_tenant_task.defer(
            purge_id=purge_id, tenant_id=tenant_id, requested_by_user_id=requested_by_user_id
        )

    return deferrer


@router.post("/tenants/{tenant_id}/purge", status_code=202)
def request_tenant_purge(
    tenant_id: str,
    body: PurgeConfirmRequest,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
    defer_task: Callable[[str, str, str], None] = Depends(get_purge_task_deferrer),
) -> PurgeTriggeredResponse:
    # Jamais d'acteur cross-tenant (spec §1.2/§3.3, aucun rôle
    # "super-admin" n'existe dans ce dépôt) : la purge ne peut cibler que
    # le tenant de l'appelant lui-même, quel que soit son privilège.
    if tenant_id != user.tenant_id:
        raise HTTPException(status_code=403, detail="cross-tenant purge not supported")
    require_privilege(session, user, Privilege.COMPLIANCE_MANAGE.value)
    tenant = session.get(Tenant, tenant_id)
    if tenant is None or body.confirmSlug != tenant.slug:
        raise HTTPException(status_code=400, detail="confirmation slug mismatch")
    purge_id = str(uuid.uuid4())
    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=user.id,
        actor_kind="user",
        action="tenant.purge_requested",
        object_type="tenant",
        object_id=tenant_id,
        payload={},
    )
    session.commit()
    # Défère APRÈS le commit de l'audit (même patron que create_upload_job/
    # create_terrain3d_upload) : le job ne doit jamais démarrer avant que
    # la ligne d'audit qui le justifie soit visible.
    defer_task(purge_id, tenant_id, user.id)
    return PurgeTriggeredResponse(jobId=purge_id)


@router.get("/purges/{purge_id}")
def get_purge_status(
    purge_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> PurgeReceiptResponse:
    require_privilege(session, user, Privilege.COMPLIANCE_MANAGE.value)
    receipt = session.get(PurgeReceipt, purge_id)
    if receipt is None:
        # Distinction impossible entre "encore en cours" et "jamais
        # déclenché" (purge_receipts n'a pas de FK vers tenants, donc pas
        # de moyen de vérifier que purge_id a été légitimement émis pour LE
        # tenant de l'appelant avant que le job ne se termine) — 202 tant
        # qu'aucune ligne n'existe est le signal attendu par le client
        # (patron GET /uploads/{job_id}, ici sans ligne de statut
        # intermédiaire propre à la purge).
        raise HTTPException(status_code=202, detail="purge still in progress or unknown")
    return PurgeReceiptResponse(
        id=receipt.id,
        tenantSlug=receipt.tenant_slug,
        requestedByUserId=receipt.requested_by_user_id,
        requestedAt=receipt.requested_at.isoformat(),
        completedAt=receipt.completed_at.isoformat() if receipt.completed_at else "",
        counts=receipt.counts,
    )
