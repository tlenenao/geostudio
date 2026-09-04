# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class NotificationRead(BaseModel):
    id: str
    kind: str
    status: str
    itemId: str | None
    itemResourceType: str | None
    itemTitle: str
    errorMessage: str | None
    createdAt: str
    readAt: str | None


class NotificationPage(BaseModel):
    notifications: list[NotificationRead]
    total: int
    page: int
    pageSize: int


class UnreadCount(BaseModel):
    count: int


class NotificationPreferenceRead(BaseModel):
    value: str


class NotificationPreferencePatch(BaseModel):
    value: str
