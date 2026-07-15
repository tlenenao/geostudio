# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import func, select
from sqlalchemy.orm import Session

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
) -> User:
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.oidc_sub == oidc_sub)
    )
    if user is None:
        user = User(
            id=uuid.uuid4().hex,
            tenant_id=tenant_id,
            oidc_sub=oidc_sub,
            username=username,
            email=email,
            first_name=first_name,
            last_name=last_name,
        )
        session.add(user)
    else:
        user.username = username
        user.email = email
        user.first_name = first_name
        user.last_name = last_name
    if bootstrap_admin and not user.is_admin:
        # Promotion par env uniquement — la rétrogradation passe par set_admin()
        # (retirer un sub de CORE_ADMIN_SUBS ne doit pas destituer silencieusement).
        user.is_admin = True
    session.flush()
    session.refresh(user)
    return user


def set_admin(session: Session, *, tenant_id: str, user_id: str, is_admin: bool) -> User | None:
    user = session.scalar(
        select(User).where(User.tenant_id == tenant_id, User.id == user_id)
    )
    if user is None:
        return None
    user.is_admin = is_admin
    session.flush()
    return user


def count_admins(session: Session, *, tenant_id: str) -> int:
    return session.scalar(
        select(func.count()).select_from(User).where(
            User.tenant_id == tenant_id, User.is_admin.is_(True)
        )
    )


def list_users(
    session: Session, *, tenant_id: str, page: int, page_size: int
) -> tuple[list[User], int]:
    base = select(User).where(User.tenant_id == tenant_id)
    total = session.scalar(select(func.count()).select_from(base.subquery()))
    users = list(session.scalars(
        base.order_by(User.username).offset((page - 1) * page_size).limit(page_size)
    ).all())
    return users, total
