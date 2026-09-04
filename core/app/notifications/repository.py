# SPDX-License-Identifier: Apache-2.0
import uuid
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.notifications.models import Notification, NotificationPreference


def create_notification(
    session: Session,
    *,
    tenant_id: str,
    recipient_user_id: str,
    kind: str,
    status: str,
    item_id: str | None,
    item_resource_type: str | None,
    item_title: str,
    error_message: str | None = None,
) -> Notification:
    notification = Notification(
        id=uuid.uuid4().hex,
        tenant_id=tenant_id,
        recipient_user_id=recipient_user_id,
        kind=kind,
        status=status,
        item_id=item_id,
        item_resource_type=item_resource_type,
        item_title=item_title,
        error_message=error_message,
    )
    session.add(notification)
    session.flush()
    return notification


def _scope(base, *, preference: str):
    if preference == "failures_only":
        return base.where(Notification.status == "failure")
    return base


def list_notifications(
    session: Session,
    *,
    tenant_id: str,
    recipient_user_id: str,
    preference: str,
    page: int,
    page_size: int,
) -> tuple[list[Notification], int]:
    if preference == "none":
        return [], 0
    base = select(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_user_id == recipient_user_id,
    )
    base = _scope(base, preference=preference)
    total = session.scalar(select(func.count()).select_from(base.subquery())) or 0
    rows = list(
        session.scalars(
            base.order_by(Notification.created_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        ).all()
    )
    return rows, total


def count_unread_notifications(
    session: Session, *, tenant_id: str, recipient_user_id: str, preference: str
) -> int:
    if preference == "none":
        return 0
    base = (
        select(func.count())
        .select_from(Notification)
        .where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.read_at.is_(None),
        )
    )
    base = _scope(base, preference=preference)
    return session.scalar(base) or 0


def mark_notification_read(
    session: Session, *, tenant_id: str, recipient_user_id: str, notification_id: str
) -> Notification | None:
    notification = session.scalar(
        select(Notification).where(
            Notification.tenant_id == tenant_id,
            Notification.recipient_user_id == recipient_user_id,
            Notification.id == notification_id,
        )
    )
    if notification is None:
        return None
    if notification.read_at is None:
        notification.read_at = datetime.now(UTC)
        session.flush()
    return notification


def mark_all_notifications_read(
    session: Session, *, tenant_id: str, recipient_user_id: str, preference: str
) -> None:
    if preference == "none":
        return
    base = select(Notification).where(
        Notification.tenant_id == tenant_id,
        Notification.recipient_user_id == recipient_user_id,
        Notification.read_at.is_(None),
    )
    base = _scope(base, preference=preference)
    now = datetime.now(UTC)
    for notification in session.scalars(base).all():
        notification.read_at = now
    session.flush()


def get_notification_preference(session: Session, *, tenant_id: str, user_id: str) -> str:
    pref = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
        )
    )
    return pref.value if pref is not None else "all"


def set_notification_preference(
    session: Session, *, tenant_id: str, user_id: str, value: str
) -> str:
    pref = session.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tenant_id == tenant_id,
            NotificationPreference.user_id == user_id,
        )
    )
    if pref is None:
        pref = NotificationPreference(user_id=user_id, tenant_id=tenant_id, value=value)
        session.add(pref)
    else:
        pref.value = value
    session.flush()
    return pref.value
