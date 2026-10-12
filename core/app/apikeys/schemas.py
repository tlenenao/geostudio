# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expiresInDays: int = Field(default=90, ge=1, le=365)


class ApiKeyRead(BaseModel):
    id: str
    name: str
    prefix: str
    createdAt: str
    expiresAt: str
    revokedAt: str | None
    lastUsedAt: str | None


class ApiKeyCreated(ApiKeyRead):
    # Seule réponse qui porte le secret, jamais relisible ensuite.
    token: str
