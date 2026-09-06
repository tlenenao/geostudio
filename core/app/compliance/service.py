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

import uuid
from datetime import UTC, datetime

from sqlalchemy import delete
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.notifications.models import Notification
from app.roles.repository import count_users_with_privileges, get_role
from app.sharing.models import GroupMember
from app.users.models import User

# Même liste que app/auth/routes.py::patch_user (PATCH /users/{id}) — pas
# importée de là (module de routes, pas une source de vérité partagée) ;
# dupliquée sciemment, comme ce fichier le fait déjà pour lui-même.
_ANTI_LOCKOUT_PRIVILEGES = ["admin.users.manage", "admin.roles.manage"]


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
    user.oidc_sub = f"erased:{uuid.uuid4()}"
    user.erased_at = datetime.now(UTC)

    session.execute(delete(Notification).where(Notification.recipient_user_id == user_id))
    session.execute(delete(GroupMember).where(GroupMember.user_id == user_id))
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
