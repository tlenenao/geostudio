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


class SnowflakeDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers un entrepôt Snowflake (GAP-16), forme
    `snowflake://user:password@account/database/schema?warehouse=...&role=...`
    (vérifiée contre le README du dépôt snowflake-sqlalchemy, design §2.2).
    Comme postgres_dsn : le cœur ne parse ni ne valide ce DSN, il le passe
    tel quel à sa.create_engine()."""

    kind: Literal["snowflake_dsn"] = "snowflake_dsn"
    dsn: str


class BigQueryDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers Google BigQuery, forme
    `bigquery://project/dataset?credentials_base64=<JSON compte de service
    encodé en base64>` — vérifiée directement contre le code source réel de
    `sqlalchemy-bigquery` (googleapis/python-bigquery-sqlalchemy, modules
    `parse_url.py`/`base.py`/`_helpers.py`, pas seulement son README, piège
    CLAUDE.md n°3), pas contre sa documentation. Pas de `credentials_path` :
    un chemin de fichier sur disque ne survivrait pas au trajet secret
    chiffré -> chaîne opaque -> DSN (design GAP-16 §12/Vague 2 §6.1) —
    `credentials_base64` embarque le JSON du compte de service intégralement
    dans la chaîne de connexion, round-trippable comme n'importe quel autre
    DSN opaque de ce module. Comme postgres_dsn/snowflake_dsn : le cœur ne
    parse ni ne valide ce DSN, il le passe tel quel à sa.create_engine().

    Différence de comportement vérifiée empiriquement par rapport à
    postgres_dsn/snowflake_dsn : `sa.create_engine()` n'est PAS totalement
    paresseux pour ce dialecte — il construit localement un objet
    `google.auth.service_account.Credentials` (et un client BigQuery) dès
    l'appel, sans y faire pour autant le moindre appel réseau tant qu'un
    JSON de compte de service bien formé (champs `client_email`/
    `token_uri`/`private_key` présents, clé RSA syntaxiquement valide) lui
    est fourni ; un JSON malformé y échoue *localement* avant tout aussi.

    Mise en garde distincte de postgres_dsn/snowflake_dsn : le mot de passe
    d'un DSN Postgres/Snowflake est masqué par `str(url)` de SQLAlchemy
    (`URL.__str__` connaît le champ password) — `credentials_base64`, lui,
    est un paramètre de requête ordinaire aux yeux de SQLAlchemy et n'est
    JAMAIS masqué par cette méthode. Aucun code de ce dépôt n'appelle
    `str(engine.url)`/`str(engine)` sur un engine bigquery (vérifié par
    grep, 2026-09-21) ; à ne jamais introduire pour ce DSN précis sans
    masquage explicite au préalable."""

    kind: Literal["bigquery_dsn"] = "bigquery_dsn"
    dsn: str


SecretPayload = Annotated[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
    | SnowflakeDsnPayload
    | BigQueryDsnPayload,
    Field(discriminator="kind"),
]

SECRET_PAYLOAD_ADAPTER: TypeAdapter[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
    | SnowflakeDsnPayload
    | BigQueryDsnPayload
] = TypeAdapter(SecretPayload)


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload
