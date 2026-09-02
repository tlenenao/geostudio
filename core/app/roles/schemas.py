# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class RoleRead(BaseModel):
    id: str
    name: str
    slug: str
    isBuiltIn: bool
    privileges: list[str]


class RoleCreate(BaseModel):
    name: str
    privileges: list[str]


class RolePatch(BaseModel):
    name: str | None = None
    privileges: list[str] | None = None


class PrivilegeCatalogEntry(BaseModel):
    privilege: str
    domain: str
    labelKey: str
