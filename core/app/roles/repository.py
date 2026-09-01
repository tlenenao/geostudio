# SPDX-License-Identifier: Apache-2.0
import uuid
from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.roles.models import Role
from app.roles.privileges import BUILT_IN_ROLE_NAMES, BUILT_IN_ROLE_PRIVILEGES, PRIVILEGE_METADATA
from app.users.models import User


def ensure_built_in_roles(session: Session, *, tenant_id: str) -> dict[str, Role]:
    """Crée les 4 rôles prédéfinis pour ce tenant s'ils n'existent pas déjà —
    idempotent, appelée à chaque requête authentifiée (app.auth.dependency).
    Chaque tenant reçoit sa PROPRE copie, jamais un tenant_id nul (arbitrage
    non négociable) ; l'immuabilité vient de is_built_in (app.roles.routes),
    pas du partage d'une ligne (design §2)."""
    existing = {
        role.slug: role
        for role in session.scalars(
            select(Role).where(Role.tenant_id == tenant_id, Role.is_built_in.is_(True))
        ).all()
    }
    for slug, privileges in BUILT_IN_ROLE_PRIVILEGES.items():
        if slug in existing:
            continue
        role = Role(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            name=BUILT_IN_ROLE_NAMES[slug],
            slug=slug,
            is_built_in=True,
            privileges=list(privileges),
        )
        session.add(role)
        existing[slug] = role
    session.flush()
    return existing


def get_role(session: Session, *, tenant_id: str, role_id: str) -> Role | None:
    return session.scalar(select(Role).where(Role.tenant_id == tenant_id, Role.id == role_id))


def list_roles(session: Session, *, tenant_id: str) -> list[Role]:
    return list(
        session.scalars(select(Role).where(Role.tenant_id == tenant_id).order_by(Role.name)).all()
    )


def create_role(session: Session, *, tenant_id: str, name: str, privileges: Sequence[str]) -> Role:
    role = Role(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        name=name,
        slug=uuid.uuid4().hex,
        is_built_in=False,
        privileges=list(privileges),
    )
    session.add(role)
    session.flush()
    session.refresh(role)
    return role


def update_role(
    session: Session,
    *,
    tenant_id: str,
    role_id: str,
    name: str | None,
    privileges: list[str] | None,
) -> Role | None:
    role = get_role(session, tenant_id=tenant_id, role_id=role_id)
    if role is None:
        return None
    if name is not None:
        role.name = name
    if privileges is not None:
        role.privileges = privileges
    session.flush()
    return role


def delete_role(session: Session, *, tenant_id: str, role_id: str) -> None:
    role = get_role(session, tenant_id=tenant_id, role_id=role_id)
    if role is not None:
        session.delete(role)
        session.flush()


def count_role_holders(session: Session, *, tenant_id: str, role_id: str) -> int:
    return session.scalar(
        select(func.count())
        .select_from(User)
        .where(User.tenant_id == tenant_id, User.role_id == role_id)
    )


def count_users_with_privileges(
    session: Session, *, tenant_id: str, privileges: Sequence[str]
) -> int:
    needed = set(privileges)
    rows = session.execute(
        select(User.id, Role.privileges)
        .join(Role, Role.id == User.role_id)
        .where(User.tenant_id == tenant_id)
    ).all()
    return sum(1 for _, role_privileges in rows if needed.issubset(set(role_privileges)))


def would_orphan_privilege_holders(
    session: Session,
    *,
    tenant_id: str,
    privileges: Sequence[str],
    role_id: str,
    new_privileges: list[str],
) -> bool:
    """True si remplacer les privilèges du rôle `role_id` par `new_privileges`
    laisserait le tenant sans aucun utilisateur possédant tous les
    `privileges` demandés, par quelque rôle que ce soit."""
    needed = set(privileges)
    rows = session.execute(
        select(User.id, User.role_id, Role.privileges)
        .join(Role, Role.id == User.role_id)
        .where(User.tenant_id == tenant_id)
    ).all()
    for _, holder_role_id, role_privileges in rows:
        effective = set(new_privileges) if holder_role_id == role_id else set(role_privileges)
        if needed.issubset(effective):
            return False
    return True


def get_privilege_catalog() -> list[dict[str, str]]:
    return [
        {"privilege": privilege.value, "domain": domain, "labelKey": label_key}
        for privilege, (domain, label_key) in PRIVILEGE_METADATA.items()
    ]
