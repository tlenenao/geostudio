# SPDX-License-Identifier: Apache-2.0
"""Anonymisation d'un utilisateur (RGPD Art. 17, SP-58 Tâche 7).

Approche retenue (spec §1.3/§3.2) : anonymisation en place, pas suppression
physique de la ligne `users` — 16 clés étrangères vers `users.id` sans
`ondelete=` rendraient une suppression physique impraticable sans un
chantier de migration hors de proportion avec ce que le droit à l'effacement
exige réellement (les données personnelles, pas l'intégrité référentielle).
Les colonnes identifiantes sont écrasées ; tout ce qui est référencé par FK
(items possédés, collections, pièces jointes…) survit, attribué au compte
anonymisé — aucune fuite nouvelle, ces objets étaient déjà visibles avant.

Garde anti-lockout : un utilisateur titulaire d'un privilège anti-lockout
(admin.users.manage/admin.roles.manage, même liste que le garde-fou déjà en
place sur PATCH /users/{id}, app/auth/routes.py) ne peut pas être anonymisé
s'il en est le DERNIER titulaire du tenant — l'anonymisation change
irrévocablement son oidc_sub (il ne peut plus jamais se reconnecter sous
cette identité), ce qui aurait le même effet qu'une rétrogradation de rôle
que ce garde-fou existant empêche déjà par ailleurs."""

from datetime import UTC, datetime

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.orm import Session

from app.apikeys.service import revoke_all_for_user
from app.audit.chain import audit_maintenance
from app.audit.models import AuditLog
from app.audit.writer import write_audit
from app.compliance.journal import schedule_erasure_journal
from app.history.service import erase_actor
from app.notifications.models import Notification
from app.outbox.models import FileTrigger, OutboundWebhook
from app.pipelines.models import PipelineWebhookToken
from app.roles.repository import count_users_with_privileges, get_role
from app.sharing.models import GroupMember, ShareLink
from app.sharing.models import _now as _share_link_now
from app.users.models import User
from app.users.repository import erased_sub

# Même liste que app/auth/routes.py::patch_user (PATCH /users/{id}) — pas
# importée de là (module de routes, pas une source de vérité partagée) ;
# dupliquée sciemment, comme ce fichier le fait déjà pour lui-même.
_ANTI_LOCKOUT_PRIVILEGES = ["admin.users.manage", "admin.roles.manage"]

# AUD-092 : clés de payload d'audit portant du texte saisi (nom de fichier, de groupe, de
# rôle…) — retirées des lignes de l'acteur effacé. Action, horodatage et pseudonyme (id)
# restent : base légale = obligation de traçabilité/sécurité (SECURITY.md).
_PII_PAYLOAD_KEYS = frozenset(
    {"filename", "title", "name", "email", "username", "firstName", "lastName"}
)


def _scrub_audit_payloads(session: Session, *, tenant_id: str, user_id: str) -> None:
    rows = session.scalars(
        select(AuditLog).where(
            AuditLog.tenant_id == tenant_id,
            or_(
                AuditLog.actor_id == user_id,
                and_(AuditLog.object_type == "user", AuditLog.object_id == user_id),
            ),
        )
    ).all()
    with audit_maintenance(session):
        for row in rows:
            if _PII_PAYLOAD_KEYS & set(row.payload or {}):
                row.payload = {k: v for k, v in row.payload.items() if k not in _PII_PAYLOAD_KEYS}


class UserAlreadyErasedError(Exception):
    """Un second appel sur un compte déjà anonymisé — pas une double
    écriture silencieuse."""


class AnonymizationLockoutError(Exception):
    """La cible est le dernier titulaire d'un privilège anti-lockout du
    tenant — l'anonymiser locquerait le tenant hors de toute gestion
    d'utilisateurs/rôles."""


def anonymize_user(
    session: Session, *, tenant_id: str, user_id: str, actor_id: str | None = None
) -> None:
    """actor_id : l'utilisateur qui déclenche l'effacement (soi-même ou un
    admin qui efface un autre compte) — distinct de `user_id` (la cible),
    pour un audit correct. Défaut `user_id` : couvre le cas le plus courant
    (effacement de son propre compte) sans obliger chaque appelant interne
    (tests, futurs scripts) à le préciser explicitement."""
    user = session.get(User, user_id)
    if user is None or user.tenant_id != tenant_id:
        raise LookupError(f"user '{user_id}' not found in tenant '{tenant_id}'")
    if user.erased_at is not None:
        raise UserAlreadyErasedError(user_id)

    role = get_role(session, tenant_id=tenant_id, role_id=user.role_id)
    if role is not None:
        for privilege in _ANTI_LOCKOUT_PRIVILEGES:
            if privilege in role.privileges and (
                count_users_with_privileges(session, tenant_id=tenant_id, privileges=[privilege])
                == 1
            ):
                raise AnonymizationLockoutError(
                    f"cannot erase the last holder of '{privilege}' in this tenant"
                )

    user.username = f"utilisateur-efface-{user_id[:8]}"
    user.email = None
    user.first_name = ""
    user.last_name = ""
    user.oidc_sub = erased_sub(user.oidc_sub)
    user.erased_at = datetime.now(UTC)

    revoke_all_for_user(session, tenant_id=tenant_id, user_id=user_id)
    session.execute(delete(Notification).where(Notification.recipient_user_id == user_id))
    session.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
    # AUD-094 : ni jeton webhook ni lien de partage ne survivent au compte.
    session.execute(
        delete(PipelineWebhookToken).where(
            PipelineWebhookToken.tenant_id == tenant_id,
            PipelineWebhookToken.created_by == user_id,
        )
    )
    session.execute(
        update(ShareLink)
        .where(
            ShareLink.tenant_id == tenant_id,
            ShareLink.created_by == user_id,
            ShareLink.revoked_at.is_(None),
        )
        .values(revoked_at=_share_link_now())
    )
    # Revue SP-L2 I3 : ni webhook sortant ni déclencheur fichier n'agit encore en son nom.
    session.execute(
        update(OutboundWebhook)
        .where(OutboundWebhook.tenant_id == tenant_id, OutboundWebhook.created_by == user_id)
        .values(enabled=False, disabled_reason="compte créateur effacé")
    )
    session.execute(
        update(FileTrigger)
        .where(FileTrigger.tenant_id == tenant_id, FileTrigger.created_by == user_id)
        .values(enabled=False, last_error="compte créateur effacé")
    )
    erase_actor(session, tenant_id=tenant_id, user_id=user_id)  # ARC-15 : journal d'entité
    _scrub_audit_payloads(session, tenant_id=tenant_id, user_id=user_id)  # AUD-092
    schedule_erasure_journal(session, kind="user", tenant_id=tenant_id, subject_id=user_id)
    session.flush()

    write_audit(
        session,
        tenant_id=tenant_id,
        actor_id=actor_id if actor_id is not None else user_id,
        actor_kind="user",
        action="user.erase",
        object_type="user",
        object_id=user_id,
        payload={},
    )
