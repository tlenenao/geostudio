# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class PresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    contentType: str = Field(min_length=1, max_length=100)


class PresignResponse(BaseModel):
    uploadUrl: str
    key: str


class IngestionJobCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    collectionTitle: str = Field(min_length=1)
    latField: str | None = None
    lonField: str | None = None
    layerName: str | None = None


class IngestionJobCreated(BaseModel):
    jobId: str


class IngestionJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    collectionId: str | None
    itemId: str | None


class InspectRequest(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)


class LayerInfoOut(BaseModel):
    name: str
    featureCount: int
    geometryType: str


class InspectResponse(BaseModel):
    layers: list[LayerInfoOut]
