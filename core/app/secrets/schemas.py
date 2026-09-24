# SPDX-License-Identifier: Apache-2.0
"""Payload chiffré des secrets connecteurs (design SP-15e §4). Union
discriminée par `kind`, additive par construction : ajouter un kind =
ajouter une variante Pydantic, aucune migration requise pour les lignes
existantes."""

from typing import Annotated, Any, Literal

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
    est fourni ; un JSON malformé y échoue *localement* avant tout appel
    réseau.

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


class MssqlDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers Microsoft SQL Server, forme
    `mssql+pymssql://user:pass@host:port/dbname` (vérifiée directement
    contre le module source réel `sqlalchemy/dialects/mssql/pymssql.py` du
    dépôt sqlalchemy/sqlalchemy, docstring `:connectstring:` +
    l'exemple `"mssql+pymssql://user:pass@host/db"` du docstring de
    `sqlalchemy/dialects/mssql/base.py`, pas seulement la doc publiée —
    piège CLAUDE.md n°3). Driver retenu : `pymssql` (pur Python, s'appuie
    sur FreeTDS embarqué dans ses wheels officielles) plutôt que `pyodbc`
    (nécessiterait `unixodbc` + un driver ODBC système sur l'image du
    worker) — aucune limitation bloquante trouvée qui imposerait pyodbc.
    Comme postgres_dsn/snowflake_dsn/bigquery_dsn : le cœur ne parse ni ne
    valide ce DSN, il le passe tel quel à sa.create_engine() ; comme
    postgres_dsn/snowflake_dsn (et contrairement à bigquery_dsn),
    sa.create_engine() reste paresseux pour ce dialecte — aucun appel
    réseau avant .connect(), et le mot de passe est masqué par
    `str(engine.url)`.

    Limitation documentée à connaître avant d'écrire `query` (analogue à la
    réserve SAMPLE/TOP/MINUS de SnowflakeDsnPayload, mais dans l'autre sens) :
    `query` est validée SELECT-only en la parsant avec le dialecte SQL de
    DuckDB (app.pipelines.connector_runtime), pas le T-SQL réel. `TOP n`
    n'est pas reconnu par le parseur DuckDB et est donc rejeté ici, alors
    qu'il serait valide sur un vrai SQL Server — à reformuler en
    `ORDER BY ... OFFSET n ROWS FETCH NEXT m ROWS ONLY`. Un identifiant entre
    crochets `[col]` (syntaxe T-SQL propriétaire) passe la validation DuckDB
    tant qu'il ne contient ni espace ni caractère spécial (`[id]` accepté,
    `[my column]` rejeté — vérifié empiriquement contre le vrai parseur, pas
    supposé) ; reformuler en guillemets doubles (`"my column"`) si besoin
    d'un identifiant à espace. À l'inverse, `LIMIT n` est accepté ici (syntaxe DuckDB valide)
    mais n'est PAS du T-SQL valide — SQL Server ne connaît pas la clause
    LIMIT — et une requête qui passe cette validation peut donc échouer
    côté serveur avec une erreur explicite au moment de l'exécution."""

    kind: Literal["mssql_dsn"] = "mssql_dsn"
    dsn: str


class OracleDsnPayload(BaseModel):
    """DSN SQLAlchemy complet vers Oracle Database, forme
    `oracle+oracledb://user:pass@hostname:port[/dbname][?service_name=<service>]`
    (vérifiée directement contre le module source réel
    `sqlalchemy/dialects/oracle/oracledb.py` du dépôt sqlalchemy/sqlalchemy —
    docstring `:connectstring:` en tête de module —, pas seulement la doc
    publiée, piège CLAUDE.md n°3). Driver retenu : `python-oracledb` (le
    driver officiel qui remplace cx_Oracle), en mode **thin** — pur Python,
    aucune bibliothèque cliente Oracle native à installer sur l'image du
    worker. Vérifié empiriquement (pas seulement lu dans la doc) : le mode
    thin est celui utilisé par défaut par `sa.create_engine()` pour ce
    dialecte — `OracleDialect_oracledb.__init__` (code source réel) n'appelle
    `oracledb.init_oracle_client()` (qui bascule en mode thick) que si
    `thick_mode` est explicitement vrai ; par défaut (`thick_mode=None`),
    aucun appel de ce type n'a lieu, et `oracledb.is_thin_mode()` renvoie
    `True` sans configuration après un simple `sa.create_engine(...)` sans
    connexion. Ce module n'a donc besoin d'aucune initialisation
    supplémentaire dans `materialize_oracle_connector`.

    Comme postgres_dsn/snowflake_dsn/mssql_dsn (et contrairement à
    bigquery_dsn) : le cœur ne parse ni ne valide ce DSN, il le passe tel
    quel à sa.create_engine() ; sa.create_engine() reste paresseux pour ce
    dialecte — vérifié empiriquement (aucun appel réseau avant .connect(),
    retour en configuration locale seulement) — et le mot de passe est
    masqué par `str(engine.url)`.

    `query` est validée SELECT-only en la parsant avec le dialecte SQL de
    DuckDB (app.pipelines.connector_runtime), pas le vrai SQL Oracle (PL/SQL)
    — même heuristique de défense en profondeur que les autres DSN de ce
    module, mêmes limites potentielles non vérifiées ici (ex. `ROWNUM`/
    `FETCH FIRST n ROWS ONLY`, pseudo-colonnes Oracle) : une requête acceptée
    ici peut malgré tout échouer côté serveur avec une erreur explicite."""

    kind: Literal["oracle_dsn"] = "oracle_dsn"
    dsn: str


class S3CredentialsPayload(BaseModel):
    """Identifiants d'accès à un bucket S3 (ou compatible S3 — MinIO, etc. via
    `endpointUrl`) pour `reader.connector.blob` (Task 15, Vague 2 §6.1).

    Champs alignés — pas devinés — sur le constructeur réel de
    `dlt.common.configuration.specs.aws_credentials.AwsCredentials`
    (`aws_access_key_id`/`aws_secret_access_key`/`endpoint_url`, vérifié par
    introspection du paquet `dlt` installé, piège CLAUDE.md n°3) : ce module
    construit un `AwsCredentials(...)` directement à partir de ces 3 champs
    et le passe tel quel à `dlt.sources.filesystem.filesystem(credentials=)` —
    c'est CETTE classe, jamais ce payload, qui sait produire les kwargs réels
    de s3fs (`.to_s3fs_credentials()` → `key`/`secret`/`endpoint_url`)."""

    kind: Literal["s3_credentials"] = "s3_credentials"
    awsAccessKeyId: str
    awsSecretAccessKey: str
    endpointUrl: str | None = None


class AzureBlobCredentialsPayload(BaseModel):
    """Identifiants d'accès à un compte Azure Blob Storage pour
    `reader.connector.blob` (Task 15, Vague 2 §6.1).

    Champs alignés sur le constructeur réel de
    `dlt.common.configuration.specs.azure_credentials.AzureCredentialsWithoutDefaults`
    (`azure_storage_account_name`/`azure_storage_account_key`, vérifié par
    introspection du paquet `dlt` installé) : ce module construit un
    `AzureCredentialsWithoutDefaults(...)` à partir de ces 2 champs — c'est
    cette classe qui produit ensuite les kwargs adlfs réels
    (`.to_adlfs_credentials()` → `account_name`/`account_key`)."""

    kind: Literal["azure_blob_credentials"] = "azure_blob_credentials"
    accountName: str
    accountKey: str


class GcsCredentialsPayload(BaseModel):
    """Compte de service Google Cloud Storage (JSON collé tel quel, tous ses
    champs standard — `type`/`project_id`/`private_key`/`client_email`/...)
    pour `reader.connector.blob` (Task 15, Vague 2 §6.1).

    Ce module ne mappe pas champ à champ : il passe `json.dumps(serviceAccountInfo)`
    à `GcpServiceAccountCredentials.parse_native_representation()` — vérifié
    empiriquement que cette méthode ignore silencieusement les champs du JSON
    non repris par le dataclass (`client_id`, `auth_provider_x509_cert_url`,
    `universe_domain`, etc., piège CLAUDE.md n°3 : pas supposé, testé), donc
    un JSON de compte de service copié-collé tel quel depuis la console GCP
    fonctionne sans filtrage manuel."""

    kind: Literal["gcs_credentials"] = "gcs_credentials"
    serviceAccountInfo: dict[str, Any]


SecretPayload = Annotated[
    ApiKeyPayload
    | BearerTokenPayload
    | BasicAuthPayload
    | OAuth2ClientCredentialsPayload
    | PostgresDsnPayload
    | SmtpCredentialsPayload
    | SnowflakeDsnPayload
    | BigQueryDsnPayload
    | MssqlDsnPayload
    | OracleDsnPayload
    | S3CredentialsPayload
    | AzureBlobCredentialsPayload
    | GcsCredentialsPayload,
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
    | MssqlDsnPayload
    | OracleDsnPayload
    | S3CredentialsPayload
    | AzureBlobCredentialsPayload
    | GcsCredentialsPayload
] = TypeAdapter(SecretPayload)


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload
