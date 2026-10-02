# SPDX-License-Identifier: Apache-2.0
from typing import Annotated

from pydantic import BaseModel, StringConstraints, field_validator

RoleName = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80)]


def _dedupe(values: list[str] | None) -> list[str] | None:
    return None if values is None else list(dict.fromkeys(values))


class RoleRead(BaseModel):
    id: str
    name: str
    slug: str
    isBuiltIn: bool
    privileges: list[str]


class RoleCreate(BaseModel):
    name: RoleName
    privileges: list[str]

    _dedupe_privileges = field_validator("privileges")(_dedupe)


class RolePatch(BaseModel):
    name: RoleName | None = None
    privileges: list[str] | None = None

    _dedupe_privileges = field_validator("privileges")(_dedupe)


class PrivilegeCatalogEntry(BaseModel):
    privilege: str
    domain: str
    labelKey: str
