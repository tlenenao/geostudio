# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field


class ExtensionProp(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "dataSource"]
    label: str
    default: object = None


class ExtensionPermissions(BaseModel):
    collections: list[str] | Literal["all"] = "all"


class ExtensionSize(BaseModel):
    w: int
    h: int


class ExtensionCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    tag: str = Field(min_length=1)
    label: str = Field(min_length=1)
    moduleUrl: str = Field(min_length=1)
    props: list[ExtensionProp] = []
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize
    permissions: ExtensionPermissions = ExtensionPermissions()


class ExtensionPatch(BaseModel):
    tag: str | None = None
    label: str | None = None
    moduleUrl: str | None = None
    props: list[ExtensionProp] | None = None
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize | None = None
    permissions: ExtensionPermissions | None = None
    enabled: bool | None = None
