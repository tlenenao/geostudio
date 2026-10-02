# SPDX-License-Identifier: Apache-2.0
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Grammaire des custom elements (tiret obligatoire) ; module chargé via
# import() dans le shell : https uniquement (j08-008).
Tag = Annotated[str, Field(min_length=1, pattern=r"^[a-z][a-z0-9._]*-[a-z0-9._-]*$")]
ModuleUrl = Annotated[str, Field(min_length=1, pattern=r"^https://[^\s]+$")]
Label = Annotated[str, Field(min_length=1)]


class ExtensionProp(BaseModel):
    name: str
    type: Literal["string", "number", "boolean", "dataSource"]
    label: str
    default: object = None


class ExtensionPermissions(BaseModel):
    collections: list[str] | Literal["all"] = "all"


class ExtensionSize(BaseModel):
    w: int = Field(gt=0)
    h: int = Field(gt=0)


class ExtensionCreate(BaseModel):
    id: str = Field(min_length=1, max_length=100)
    tag: Tag
    label: Label
    moduleUrl: ModuleUrl
    props: list[ExtensionProp] = []
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize
    permissions: ExtensionPermissions = ExtensionPermissions()


class ExtensionPatch(BaseModel):
    tag: Tag | None = None
    label: Label | None = None
    moduleUrl: ModuleUrl | None = None
    props: list[ExtensionProp] | None = None
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize | None = None
    permissions: ExtensionPermissions | None = None
    enabled: bool | None = None
