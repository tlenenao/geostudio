from typing import Literal

from pydantic import BaseModel


class GroupShare(BaseModel):
    groupId: str
    role: Literal["viewer", "editor"]


class Sharing(BaseModel):
    public: bool
    groups: list[GroupShare]
