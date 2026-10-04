# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class UsageTaskRead(BaseModel):
    id: int
    actorId: str | None
    actorUsername: str | None = None
    action: str
    objectType: str
    objectId: str
    createdAt: str
    objectTitle: str | None = None


class UsageTaskPage(BaseModel):
    tasks: list[UsageTaskRead]
    total: int
    page: int
    pageSize: int


class UsageActorStatRead(BaseModel):
    actorId: str | None
    actorUsername: str | None
    count: int


class UsageResourceStatRead(BaseModel):
    objectType: str
    objectId: str
    count: int
    objectTitle: str | None = None


class UsageSummaryRead(BaseModel):
    byActor: list[UsageActorStatRead]
    byResource: list[UsageResourceStatRead]
    totalActions: int
    windowStart: str
    windowEnd: str
