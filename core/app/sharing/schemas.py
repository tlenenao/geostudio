# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, field_validator

# GAP-12 (chantier 4.23) : liens de partage à échéance, distincts du
# partage groupe/rôle plat ci-dessus.
_MAX_SHARE_LINK_TTL_DAYS = 30


class CreateShareLinkRequest(BaseModel):
    ttlDays: int

    @field_validator("ttlDays")
    @classmethod
    def ttl_within_server_cap(cls, ttl_days: int) -> int:
        if ttl_days < 1 or ttl_days > _MAX_SHARE_LINK_TTL_DAYS:
            raise ValueError(f"ttlDays must be between 1 and {_MAX_SHARE_LINK_TTL_DAYS}")
        return ttl_days


class ShareLinkCreated(BaseModel):
    url: str
    expiresAt: str


class ShareLinkListItem(BaseModel):
    id: str
    expiresAt: str
    revoked: bool


class ResolvedShareLink(BaseModel):
    itemId: str
    title: str
    resourceType: str
    expiresAt: str


class GroupShare(BaseModel):
    groupId: str
    role: Literal["viewer", "editor"]


class Sharing(BaseModel):
    public: bool
    groups: list[GroupShare]

    @field_validator("groups")
    @classmethod
    def no_duplicate_groups(cls, groups):
        seen = [g.groupId for g in groups]
        if len(seen) != len(set(seen)):
            raise ValueError("duplicate groupId in sharing payload")
        return groups
