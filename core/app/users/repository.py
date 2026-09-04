# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.roles.repository import ensure_built_in_roles
from app.users.models import User


def get_or_create_user(
    session: Session,
    *,
    tenant_id: str,
    oidc_sub: str,
    username: str,
    email: str | None,
    first_name: str,
    last_name: str,
    bootstrap_admin: bool = False,
    bootstrap_analyst: bool = False,
) -> User:
    roles = ensure_built_in_roles(session, tenant_id=tenant_id)
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.oidc_sub == oidc_sub)
    )
    if user is None:
        if bootstrap_admin:
            initial_role = roles["admin"]
        elif bootstrap_analyst:
            initial_role = roles["analyst"]
        else:
            initial_role = roles["creator"]
        user = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            oidc_sub=oidc_sub,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
            role_id=initial_role.id,
            is_admin=(initial_role.slug == "admin"),
        )
        session.add(user)
    else:
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
        if bootstrap_admin and user.role_id != roles["admin"].id:
            # Promotion par env uniquement — la rétrogradation passe par
            # set_user_role() (retirer un sub de CORE_ADMIN_SUBS ne doit pas
            # destituer silencieusement).
            user.role_id = roles["admin"].id
            user.is_admin = True
        elif bootstrap_analyst and user.role_id in (roles["creator"].id, roles["reader"].id):
            # Miroir de bootstrap_admin — ne promeut que depuis un rôle
            # prédéfini non-privilégié (creator/reader). Ne touche JAMAIS un
            # rôle sur mesure : un tel rôle peut porter des privilèges
            # qu'une rétrogradation silencieuse briserait, y compris
            # l'anti-lockout (ce chemin d'écriture ne passe par aucun des
            # deux gardes anti-lockout HTTP). "admin" est déjà exclu par la
            # construction du elif.
            user.role_id = roles["analyst"].id
    session.flush()
    session.refresh(user)
    return user


def set_user_role(
    session: Session, *, tenant_id: str, user_id: str, role_id: str, role_slug: str
) -> User | None:
    user = session.scalar(select(User).where(User.tenant_id == tenant_id, User.id == user_id))
    if user is None:
        return None
    user.role_id = role_id
    user.is_admin = role_slug == "admin"
    session.flush()
    return user


def list_users(
    session: Session, *, tenant_id: str, page: int, page_size: int, q: str | None = None
) -> tuple[list[User], int]:
    base = select(User).where(User.tenant_id == tenant_id)
    if q:
        base = base.where(User.username.ilike(f"%{q}%"))
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    users = list(
        session.scalars(
            base.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
        ).all()
    )
    return users, total
