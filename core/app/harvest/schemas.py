# SPDX-License-Identifier: Apache-2.0
from typing import Literal

from pydantic import BaseModel, Field


class HarvestSourceCreate(BaseModel):
    type: Literal["stac", "arcgis"]
    url: str = Field(min_length=1)
    mode: Literal["reference", "copy"] = "reference"
    enabled: bool = True
    intervalMinutes: int | None = Field(default=None, ge=1)


class HarvestSourcePatch(BaseModel):
    url: str | None = Field(default=None, min_length=1)
    mode: Literal["reference", "copy"] | None = None
    enabled: bool | None = None
    intervalMinutes: int | None = Field(default=None, ge=1)
