# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class Tileset3DUploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)


class Tileset3DUploadCreated(BaseModel):
    jobId: str


class Tileset3DPartPresignResponse(BaseModel):
    uploadUrl: str


class Tileset3DPartInput(BaseModel):
    partNumber: int = Field(ge=1)
    etag: str = Field(min_length=1)


class Tileset3DCompleteRequest(BaseModel):
    parts: list[Tileset3DPartInput] = Field(min_length=1)


class Tileset3DJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    itemId: str | None
