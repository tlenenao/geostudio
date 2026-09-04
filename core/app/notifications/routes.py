# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.auth.dependency import get_current_user
from app.db import get_session
from app.notifications.models import Notification
from app.notifications.repository import (
    count_unread_notifications,
    get_notification_preference,
    list_notifications,
    mark_all_notifications_read,
    mark_notification_read,
    set_notification_preference,
)
from app.notifications.schemas import (
    NotificationPage,
    NotificationPreferencePatch,
    NotificationPreferenceRead,
    NotificationRead,
    UnreadCount,
)
from app.users.models import User

router = APIRouter()

_VALID_PREFERENCE_VALUES = {"all", "failures_only", "none"}


def _notification_json(notification: Notification) -> NotificationRead:
    return NotificationRead(
        id=notification.id,
        kind=notification.kind,
        status=notification.status,
        itemId=notification.item_id,
        itemResourceType=notification.item_resource_type,
        itemTitle=notification.item_title,
        errorMessage=notification.error_message,
        createdAt=notification.created_at.isoformat(),
        readAt=notification.read_at.isoformat() if notification.read_at is not None else None,
    )


@router.get("/notifications", response_model=NotificationPage)
def get_notifications(
    page: int = 1,
    pageSize: int = 20,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationPage:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    notifications, total = list_notifications(
        session,
        tenant_id=user.tenant_id,
        recipient_user_id=user.id,
        preference=preference,
        page=page,
        page_size=pageSize,
    )
    return NotificationPage(
        notifications=[_notification_json(n) for n in notifications],
        total=total,
        page=page,
        pageSize=pageSize,
    )


@router.get("/notifications/unread-count", response_model=UnreadCount)
def get_unread_count(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> UnreadCount:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    count = count_unread_notifications(
        session, tenant_id=user.tenant_id, recipient_user_id=user.id, preference=preference
    )
    return UnreadCount(count=count)


@router.post("/notifications/{notification_id}/read", response_model=NotificationRead)
def post_notification_read(
    notification_id: str,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationRead:
    notification = mark_notification_read(
        session,
        tenant_id=user.tenant_id,
        recipient_user_id=user.id,
        notification_id=notification_id,
    )
    if notification is None:
        raise HTTPException(status_code=404, detail="notification not found")
    return _notification_json(notification)


@router.post("/notifications/read-all", status_code=204)
def post_notifications_read_all(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> None:
    preference = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    mark_all_notifications_read(
        session, tenant_id=user.tenant_id, recipient_user_id=user.id, preference=preference
    )


@router.get("/notifications/preference", response_model=NotificationPreferenceRead)
def get_preference(
    user: User = Depends(get_current_user), session: Session = Depends(get_session)
) -> NotificationPreferenceRead:
    value = get_notification_preference(session, tenant_id=user.tenant_id, user_id=user.id)
    return NotificationPreferenceRead(value=value)


@router.patch("/notifications/preference", response_model=NotificationPreferenceRead)
def patch_preference(
    body: NotificationPreferencePatch,
    user: User = Depends(get_current_user),
    session: Session = Depends(get_session),
) -> NotificationPreferenceRead:
    if body.value not in _VALID_PREFERENCE_VALUES:
        raise HTTPException(status_code=400, detail=f"unknown preference value: {body.value}")
    value = set_notification_preference(
        session, tenant_id=user.tenant_id, user_id=user.id, value=body.value
    )
    return NotificationPreferenceRead(value=value)
