## Task 2: Payload schemas — `core/app/secrets/schemas.py`

**Files:**
- Create: `core/app/secrets/schemas.py`
- Test: `core/tests/test_secrets_schemas.py`

**Interfaces:**
- Produces: `app.secrets.schemas.SecretPayload` (discriminated union type
  alias over `ApiKeyPayload | BearerTokenPayload | BasicAuthPayload |
  OAuth2ClientCredentialsPayload | PostgresDsnPayload`), `SecretCreate`
  (`BaseModel`, fields `name: str`, `payload: SecretPayload`),
  `SECRET_PAYLOAD_ADAPTER` (`TypeAdapter[SecretPayload]`). Consumed by Task
  4 (`repository.get_secret_payload`) and Task 5 (`routes.py`'s request
  body and `kind` derivation).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_secrets_schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretCreate


def test_api_key_header_placement_round_trips():
    body = SecretCreate.model_validate({
        "name": "geoserver-key",
        "payload": {"kind": "api_key", "location": "header", "key": "X-API-Key", "value": "abc"},
    })
    assert body.payload.location == "header"
    assert body.payload.key == "X-API-Key"


def test_api_key_query_placement_round_trips():
    # ArcGIS Feature Service / WFS-style token-in-query-param auth (spec §4).
    body = SecretCreate.model_validate({
        "name": "arcgis-fs-token",
        "payload": {"kind": "api_key", "location": "query", "key": "token", "value": "abc123"},
    })
    assert body.payload.location == "query"


def test_bearer_token_round_trips():
    body = SecretCreate.model_validate({
        "name": "weather-api", "payload": {"kind": "bearer_token", "token": "tok"},
    })
    assert body.payload.token == "tok"


def test_basic_auth_round_trips():
    body = SecretCreate.model_validate({
        "name": "wfs-basic",
        "payload": {"kind": "basic_auth", "username": "u", "password": "p"},
    })
    assert body.payload.username == "u"


def test_oauth2_client_credentials_round_trips():
    # ArcGIS Online app-login shape (spec §4).
    body = SecretCreate.model_validate({
        "name": "arcgis-online-app",
        "payload": {
            "kind": "oauth2_client_credentials",
            "tokenUrl": "https://www.arcgis.com/sharing/rest/oauth2/token",
            "clientId": "cid", "clientSecret": "csecret",
        },
    })
    assert body.payload.clientId == "cid"


def test_postgres_dsn_round_trips():
    body = SecretCreate.model_validate({
        "name": "warehouse-pg", "payload": {"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"},
    })
    assert body.payload.dsn == "postgresql://u:p@host/db"


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({"name": "x", "payload": {"kind": "ssh_key", "value": "y"}})


def test_api_key_requires_location():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({
            "name": "x", "payload": {"kind": "api_key", "key": "k", "value": "v"},
        })


def test_secret_payload_adapter_decodes_decrypted_dict():
    # This is exactly what repository.get_secret_payload does after
    # crypto.decrypt() returns a plain dict (Task 4).
    payload = SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "bearer_token", "token": "tok"})
    assert payload.token == "tok"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.secrets.schemas'`.

- [ ] **Step 3: Implement `schemas.py`**

Create `core/app/secrets/schemas.py`:

```python
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


SecretPayload = Annotated[
    ApiKeyPayload | BearerTokenPayload | BasicAuthPayload
    | OAuth2ClientCredentialsPayload | PostgresDsnPayload,
    Field(discriminator="kind"),
]

SECRET_PAYLOAD_ADAPTER: TypeAdapter = TypeAdapter(SecretPayload)


class SecretCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    payload: SecretPayload
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_schemas.py -v`
Expected: 9 passed.

- [ ] **Step 5: Commit**

```bash
git add core/app/secrets/schemas.py core/tests/test_secrets_schemas.py
git commit -m "feat(core): secrets module — discriminated payload schemas"
```

---

