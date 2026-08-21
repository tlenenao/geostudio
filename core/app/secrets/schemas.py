# SPDX-License-Identifier: Apache-2.0
"""Payload chiffré des secrets connecteurs (design SP-15e §4). Union
discriminée par `kind`, additive par construction : ajouter un kind =
ajouter une variante Pydantic, aucune migration requise pour les lignes
existantes."""

from typing import Annotated, Literal

from pydantic import BaseModel, Field, TypeAdapter


class ApiKeyPayload(BaseModel):
    """`location="query"` couvre les jetons en paramètre d'URL (ex.
    `?token=...` d'un ArcGIS Feature Service, clé GeoServer sur un WFS) ;
    `location="header"` couvre le cas générique (`X-API-Key`, etc.)."""

    kind: Literal["api_key"] = "api_key"
    location: Literal["header", "query"]
    key: str
    value: str


class BearerTokenPayload(BaseModel):
    kind: Literal["bearer_token"] = "bearer_token"
    token: str


class BasicAuthPayload(BaseModel):
    """Couvre aussi un WFS/WMS/WMTS/CSW gaté par HTTP Basic Auth, et le flux
    ArcGIS Enterprise `generateToken` si un connecteur choisit de faire
    l'échange de jeton lui-même — le coffre ne porte que le matériel brut."""

    kind: Literal["basic_auth"] = "basic_auth"
    username: str
    password: str


class OAuth2ClientCredentialsPayload(BaseModel):
    """Flux OAuth2 client-credentials — couvre notamment l'« app login »
    ArcGIS Online et toute API tierce gatée par ce flux standard. Le coffre
    stocke les identifiants client, jamais le jeton d'accès obtenu."""

    kind: Literal["oauth2_client_credentials"] = "oauth2_client_credentials"
    tokenUrl: str
    clientId: str
    clientSecret: str


class PostgresDsnPayload(BaseModel):
    kind: Literal["postgres_dsn"] = "postgres_dsn"
    dsn: str


class SmtpCredentialsPayload(BaseModel):
    """SMTP credentials for AlertRule email delivery (SP-16b §5). Unlike
    the webhook channel's URL, this comes from an admin-only secret
    (POST /secrets is admin-only, SP-15e) rather than arbitrary per-rule
    user input — no egress guard applies to it (Global Constraints,
    SP-16b plan), same trust model as postgres_dsn."""

    kind: Literal["smtp"] = "smtp"
    host: str
    port: int
    username: str
    password: str
    useTls: bool = True
    fromAddress: str


SecretPayload = Annotated[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload,
    Field(discriminator="kind"),
]

SECRET_PAYLOAD_ADAPTER: TypeAdapter[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
] = TypeAdapter(SecretPayload)


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload
