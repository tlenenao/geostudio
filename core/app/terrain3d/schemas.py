# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class Terrain3DPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    # Même forme que app.ingestion.schemas.PresignRequest. Le type est signé
    # dans l'URL présignée (X-Amz-SignedHeaders) : s'il ne correspond pas à
    # l'en-tête que le navigateur enverra (File.type, "image/tiff" pour un
    # .tif), S3 répond 403 SignatureDoesNotMatch. Défaut conservé pour ne pas
    # rendre le champ obligatoire à un appelant existant.
    contentType: str = Field(default="application/octet-stream", min_length=1, max_length=100)


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
