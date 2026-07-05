from sqlalchemy.orm import Session

from app.audit.models import AuditLog


def write_audit(
    session: Session,
    *,
    tenant_id: str,
    actor_id: str | None,
    actor_kind: str,
    action: str,
    object_type: str,
    object_id: str,
    payload: dict | None = None,
) -> None:
    session.add(
        AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_kind=actor_kind,
            action=action,
            object_type=object_type,
            object_id=object_id,
            payload=payload or {},
        )
    )
    session.flush()
