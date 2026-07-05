import uuid

from sqlalchemy import select
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
    session.flush()
    session.refresh(user)
    return user
