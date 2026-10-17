# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class ApiKeyCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    expiresInDays: int = Field(default=90, ge=1, le=365)
    # AUD-091 : sous-ensemble des privilèges du créateur ; None = tous les siens.
    scopes: list[str] | None = Field(default=None, max_length=50)
    readOnly: bool = False


class ApiKeyRead(BaseModel):
    id: str
    name: str
    prefix: str
    createdAt: str
    expiresAt: str
    revokedAt: str | None
    lastUsedAt: str | None
    scopes: list[str] | None = None
    readOnly: bool = False


class ApiKeyCreated(ApiKeyRead):
    # Seule réponse qui porte le secret, jamais relisible ensuite.
    token: str
