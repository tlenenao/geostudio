# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class Terrain3DPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class Terrain3DPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class Terrain3DUploadCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)


class Terrain3DUploadCreated(BaseModel):
    jobId: str


class Terrain3DJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    itemId: str | None
