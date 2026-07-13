from sqlalchemy import select
from sqlalchemy.orm import Session

from app.extensions.models import Extension


def get_extension(session: Session, *, tenant_id: str, extension_id: str) -> Extension | None:
    return session.scalar(select(Extension).where(
        Extension.tenant_id == tenant_id, Extension.id == extension_id))


def create_extension(
    session: Session, *, tenant_id: str, owner_id: str, id: str, tag: str, label: str,
    module_url: str, props: list, events: list[str] | None, actions: list[str] | None,
    default_size: dict, permissions: dict,
) -> Extension:
    ext = Extension(
        id=id, tenant_id=tenant_id, owner_id=owner_id, tag=tag, label=label,
        module_url=module_url, props=props, events=events, actions=actions,
        default_size=default_size, permissions=permissions,
    )
    session.add(ext)
    session.flush()
    return ext


def update_extension(session: Session, ext: Extension, **fields) -> Extension:
    for key, value in fields.items():
        setattr(ext, key, value)
    session.flush()
    return ext


def list_extensions(session: Session, *, tenant_id: str, include_disabled: bool = False) -> list[Extension]:
    stmt = select(Extension).where(Extension.tenant_id == tenant_id)
    if not include_disabled:
        stmt = stmt.where(Extension.enabled.is_(True))
    return list(session.scalars(stmt.order_by(Extension.label)).all())
