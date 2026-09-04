# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field, field_validator

from app.catalog.metadata import validate_language_id, validate_license_id


class ItemPermissions(BaseModel):
    """Ce que l'utilisateur courant a le droit de faire sur cet item.

    Calculé par le cœur depuis `can()` (une seule porte, spec §6.3) et jamais
    recalculé côté client : le shell affiche ou masque à partir de ces quatre
    booléens, ce qui supprime les commandes qui produisaient un 403 après le
    clic. Ce n'est PAS une frontière de sécurité — le cœur reste seul juge à
    chaque écriture.
    """

    read: bool
    write: bool
    delete: bool
    share: bool


class ItemRead(BaseModel):
    pk: str
    resourceType: str
    slug: str | None = None
    title: str
    abstract: str
    owner: str
    thumbnailUrl: str | None
    date: str
    configId: str | None
    isPublished: bool
    keywords: list[str] = []
    license: str = ""
    language: str = "fr"
    permissions: ItemPermissions


class ItemPage(BaseModel):
    items: list[ItemRead]
    total: int
    page: int
    pageSize: int


class ItemUpdatePatch(BaseModel):
    title: str | None = None
    abstract: str | None = None
    keywords: list[str] | None = None
    isPublished: bool | None = Field(default=None)
    slug: str | None = None
    license: str | None = None
    language: str | None = None

    @field_validator("license")
    @classmethod
    def _validate_license(cls, v: str | None) -> str | None:
        return validate_license_id(v)

    @field_validator("language")
    @classmethod
    def _validate_language(cls, v: str | None) -> str | None:
        return validate_language_id(v)
