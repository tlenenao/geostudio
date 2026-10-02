# SPDX-License-Identifier: Apache-2.0
from typing import Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, Field, field_validator


def _check_http_url(value: str | None) -> str | None:
    # j07-004 : validation à l'écriture seulement (ces modèles ne relisent
    # jamais les sources déjà stockées, qui passent par _source_json).
    if value is None:
        return value
    parts = urlsplit(value.strip())
    if parts.scheme not in ("http", "https") or not parts.hostname:
        raise ValueError("url must be an http(s) URL")
    return value.strip()


class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis", "wms", "wfs", "wmts", "csw", "ogc-records", "ckan"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)

    _url_http = field_validator("url")(_check_http_url)


class HarvestSourcePatch(BaseModel):
    url: str | None = Field(default=None, min_length=1)
    mode: Literal["reference", "copy"] | None = None
    enabled: bool | None = None
    intervalMinutes: int | None = Field(default=None, ge=1)

    _url_http = field_validator("url")(_check_http_url)
