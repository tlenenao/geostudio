# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel


class LicenseCatalogEntry(BaseModel):
    id: str
    label: str
    dcatUri: str | None
    spdxId: str


class FrequencyCatalogEntry(BaseModel):
    id: str
    label: str


class LanguageCatalogEntry(BaseModel):
    id: str
    label: str


class MetadataCatalog(BaseModel):
    licenses: list[LicenseCatalogEntry]
    frequencies: list[FrequencyCatalogEntry]
    languages: list[LanguageCatalogEntry]
