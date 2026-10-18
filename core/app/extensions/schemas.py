# SPDX-License-Identifier: Apache-2.0
from typing import Annotated, Literal

from pydantic import BaseModel, Field

# Grammaire des custom elements (tiret obligatoire) ; module chargé via
# import() dans le shell : https uniquement (j08-008).
Tag = Annotated[str, Field(min_length=1, pattern=r"^[a-z][a-z0-9._]*-[a-z0-9._-]*$")]
ModuleUrl = Annotated[str, Field(min_length=1, pattern=r"^https://[^\s]+$")]
Label = Annotated[str, Field(min_length=1)]
# AUD-109 : origine https seule (pas de chemin, pas de joker) injectée dans la CSP ;
# SRI (sha256/384/512 en base64) vérifié par le navigateur avant exécution du module.
Origin = Annotated[str, Field(max_length=253, pattern=r"^https://[a-z0-9.-]+(:[0-9]{1,5})?$")]
Integrity = Annotated[
    str, Field(max_length=200, pattern=r"^sha(256|384|512)-[A-Za-z0-9+/]+={0,2}$")
]
# AUD-110 : version du contrat DOM du SDK (préversion, D5). Seule la v1 existe ; une
# valeur supérieure est refusée tant que le shell ne sait pas la servir.
SdkVersion = Literal[1]


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
    sdkVersion: SdkVersion = 1
    integrity: Integrity | None = None
    connectHosts: list[Origin] = Field(default_factory=list, max_length=20)
    imgHosts: list[Origin] = Field(default_factory=list, max_length=20)


class ExtensionPatch(BaseModel):
    tag: Tag | None = None
    label: Label | None = None
    moduleUrl: ModuleUrl | None = None
    props: list[ExtensionProp] | None = None
    events: list[str] | None = None
    actions: list[str] | None = None
    defaultSize: ExtensionSize | None = None
    permissions: ExtensionPermissions | None = None
    sdkVersion: SdkVersion | None = None
    integrity: Integrity | None = None
    connectHosts: list[Origin] | None = Field(default=None, max_length=20)
    imgHosts: list[Origin] | None = Field(default=None, max_length=20)
    enabled: bool | None = None
