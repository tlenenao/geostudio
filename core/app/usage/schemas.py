# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class UsageTaskRead(BaseModel):
    id: int
    actorId: str | None
    action: str
    objectType: str
    objectId: str
    createdAt: str


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


class UsageSummaryRead(BaseModel):
    byActor: list[UsageActorStatRead]
    byResource: list[UsageResourceStatRead]
    totalActions: int
    windowStart: str
    windowEnd: str
