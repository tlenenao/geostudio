# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, field_validator


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
