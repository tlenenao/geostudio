# SP-15e — Coffre de secrets pour connecteurs externes — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a new `core/app/secrets/` module that stores external
connector credentials (REST API keys/tokens, HTTP basic auth, OAuth2
client-credentials, Postgres DSNs) encrypted at rest, referenced by a
tenant-scoped name, admin-only, never exposed in any API response after
creation.

**Architecture:** App-level AES-256-GCM encryption (`cryptography`'s
`AESGCM`), master key from a required env var
(`CORE_SECRETS_MASTER_KEY`), never touching SQL. A discriminated Pydantic
union (`SecretPayload`) covers five credential shapes, additive by
construction (new kind = new Pydantic variant, no migration). A new table
(`connector_secrets`, tenant-scoped, `audit_log`'d on every write) is
positioned in the import-linter layer contract strictly **below both**
`app.harvest` and `app.pipelines` — the two anticipated future consumer
families (this plan builds neither consumer; it only makes the store
capable of serving both later). Three REST routes
(`POST`/`GET`/`DELETE /secrets`), admin-gated via the repo's existing
`_require_admin(user)` pattern, never return a decrypted value or
ciphertext.

**Tech Stack:** Python/FastAPI (`core/`), Pydantic v2 discriminated unions,
SQLAlchemy 2.0 ORM + Alembic, `cryptography` (AES-GCM), pytest.

## Global Constraints

- **`tenant_id` + `audit_log` on every table/write, from the first
  migration** (`CLAUDE.md`, non-negotiable). `connector_secrets` has a
  `tenant_id` FK from Task 3; `secret.create`/`secret.delete` write
  `audit_log` rows from Task 5 — **the audit payload must never contain the
  secret value, ciphertext, or nonce**, only `name`/`kind`/`id` (spec §3.3).
- **No API response ever contains a decrypted value, `ciphertext`, or
  `nonce`.** `POST /secrets` returns metadata only, even on create. There is
  no `GET /secrets/{id}` and no `PUT` — rotation is delete + recreate (spec
  §6, non-goal).
- **Admin-only, tenant-scoped, on all three routes** (`POST`/`GET`/`DELETE
  /secrets`) — reuse the exact existing pattern, a local `_require_admin(user)`
  helper checking `user.is_admin`, raising `HTTPException(403, "admin role
  required")` (verified at `core/app/extensions/routes.py:15-18` and
  `core/app/harvest/routes.py:32-34` — duplicated per-module, no shared
  dependency exists in this codebase; do not invent one here).
- **Import-linter layering**: `core/pyproject.toml`'s `[[tool.importlinter.contracts]]`
  `layers` list currently orders `app.harvest` **above** `app.pipelines`
  (`core/pyproject.toml:78-79`, verified) — the two anticipated future
  consumers of this store are NOT peers of each other. `app.secrets` MUST be
  inserted strictly below both (position: immediately after `app.pipelines`,
  before `app.ingestion`), so both can import it and neither direction
  conflicts. Every new cross-module import this plan's own code needs
  (`app.audit`, `app.auth`, `app.users`) is already below that position —
  verified by reading the current list; do not reorder anything else.
- **No shared "require admin" dependency refactor.** Even though duplicating
  `_require_admin` a third time is mildly repetitive, this plan does not
  extract a shared helper — that would touch `app.extensions`/`app.harvest`
  outside this plan's scope. Follow the existing duplication convention.
- **No new `BuilderConfig` kind, no canvas/builder UI, no MCP tool that
  creates or returns a secret value** (spec §1 non-goals, §7). MCP exposure
  of secret *names* (metadata only) is explicitly deferred to SP-15f — do
  not add any MCP tool in this plan.
- **No `reader.connector`/dlt op, no SP-12 harvest-connector auth wiring.**
  This plan only makes the store *capable* of serving those future
  consumers (via the layering decision above and the generalized `api_key`
  shape) — it does not build either consumer.
- **Import-linter is verified via `cd core && uv run lint-imports`** (a
  separate CI step, `.github/workflows/ci.yml:58` — confirmed this repo does
  NOT run it via pytest). Every task below that changes the layers list or
  adds a new cross-module import must be followed by running this command,
  not by writing a new pytest test for it.
- **Test master key**: `create_app()` gains an eager, unconditional call to
  `crypto.load_master_key()` (Task 5) — this means **every existing test file
  that calls `create_app()`** (there are many, via the repo-wide `env()`
  fixture pattern, e.g. `core/tests/test_extensions_routes.py:25-45`) would
  start failing at collection time without a valid
  `CORE_SECRETS_MASTER_KEY`. Task 5 adds a fixed, clearly-dev-only test
  default via `os.environ.setdefault(...)` at the top of
  `core/tests/conftest.py`, loaded before any test module imports
  `app.main` — this is NOT a security concern (it's a well-known, committed
  test-only value, never used outside pytest) but IS load-bearing for the
  whole suite staying green. Do not skip this step.
- **`ConnectorSecret.id` is `uuid.uuid4().hex`, generated in the repository
  layer** (matching `core/app/pipelines/repository.py:15-22`'s
  `create_run`), not a DB-side default — follow this exactly, do not use a
  SQL `server_default` for `id`.
- **Response field naming is camelCase** (`createdAt`/`updatedAt`), matching
  `core/app/pipelines/routes.py:32-38`'s `RunStatus` (`startedAt`,
  `finishedAt`) — not the alternate hand-built-dict convention used by
  `app.extensions`/`app.collections`. Define the response shape as a
  Pydantic `BaseModel` directly in `routes.py`, not in `schemas.py`.

---

## Task 1: Encryption primitive — `core/app/secrets/crypto.py`

**Files:**
- Create: `core/app/secrets/__init__.py`
- Create: `core/app/secrets/crypto.py`
- Modify: `core/pyproject.toml` (add `cryptography` dependency, insert
  `app.secrets` into the import-linter `layers` list)
- Test: `core/tests/test_secrets_crypto.py`

**Interfaces:**
- Produces: `app.secrets.crypto.load_master_key() -> bytes`,
  `encrypt(payload: dict) -> tuple[bytes, bytes]`,
  `decrypt(ciphertext: bytes, nonce: bytes) -> dict`. Consumed by Task 4
  (`repository.get_secret_payload`), Task 5 (`routes.create_secret_route`,
  and `app.main.create_app()`'s eager boot check).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_secrets_crypto.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.secrets import crypto

TEST_KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"kind": "bearer_token", "token": "s3cr3t"})
    assert crypto.decrypt(ciphertext, nonce) == {"kind": "bearer_token", "token": "s3cr3t"}


def test_decrypt_rejects_tampered_ciphertext(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"token": "s3cr3t"})
    tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(InvalidTag):
        crypto.decrypt(tampered, nonce)


def test_decrypt_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"token": "s3cr3t"})
    other_key = base64.b64encode(bytes(range(1, 33))).decode()
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", other_key)
    with pytest.raises(InvalidTag):
        crypto.decrypt(ciphertext, nonce)


def test_load_master_key_missing_raises(monkeypatch):
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    with pytest.raises(KeyError):
        crypto.load_master_key()


def test_load_master_key_malformed_base64_raises(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", "not-valid-base64!!")
    with pytest.raises(RuntimeError, match="valid base64"):
        crypto.load_master_key()


def test_load_master_key_wrong_length_raises(monkeypatch):
    short_key = base64.b64encode(b"short").decode()
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", short_key)
    with pytest.raises(RuntimeError, match="32 bytes"):
        crypto.load_master_key()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_crypto.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.secrets'`.

- [ ] **Step 3: Add the `cryptography` dependency**

Modify `core/pyproject.toml` — in the `dependencies = [...]` list, add right
after `"pyjwt[crypto]>=2.8",`:

```toml
    "cryptography>=42.0",  # SP-15e : chiffrement applicatif AES-GCM du
                           # coffre de secrets ; déjà présent transitivement
                           # via pyjwt[crypto] (49.0.0 dans uv.lock, vérifié),
                           # déclaré ici en dépendance directe pour ne pas
                           # dépendre d'une extra tierce pour un import de
                           # production.
```

Run: `cd core && uv sync`
Expected: resolves without changing the locked `cryptography` version (it
was already present transitively at 49.0.0 — this just makes it a direct
dependency).

- [ ] **Step 4: Insert `app.secrets` into the import-linter layers list**

Modify `core/pyproject.toml` — in the `[[tool.importlinter.contracts]]`
block, change:

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

to:

```toml
layers = [
    "app.main",
    "app.mcp",
    "app.public",
    "app.harvest",
    "app.pipelines",
    "app.secrets",
    "app.ingestion",
    "app.dcat",
    "app.stac",
    "app.features",
    "app.collections",
    "app.configs",
    "app.extensions",
    "app.items",
    "app.sharing",
    "app.auth",
    "app.audit",
    "app.users",
    "app.tenants",
]
```

(`app.secrets` sits directly below both `app.harvest` and `app.pipelines` —
its two anticipated future consumer families — and above `app.audit`,
which Task 5's `routes.py` needs to import.)

- [ ] **Step 5: Create the module and implement `crypto.py`**

Create `core/app/secrets/__init__.py`:

```python
# SPDX-License-Identifier: Apache-2.0
```

Create `core/app/secrets/crypto.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Chiffrement applicatif AES-256-GCM des secrets connecteurs (design
SP-15e §2/§4 —
docs/superpowers/specs/2026-08-06-sp15e-connector-secrets-store-design.md).
La clé maître ne doit JAMAIS être loguée, incluse dans un message d'erreur,
un span OTel ou une entrée audit_log."""
import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE_BYTES = 12
_KEY_SIZE_BYTES = 32


def load_master_key() -> bytes:
    """Lit CORE_SECRETS_MASTER_KEY (32 octets encodés base64). Lève
    `KeyError` si absente, `RuntimeError` si mal formée — échec rapide,
    jamais un défaut silencieux (design §4)."""
    raw = os.environ["CORE_SECRETS_MASTER_KEY"]
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("CORE_SECRETS_MASTER_KEY must be valid base64") from exc
    if len(key) != _KEY_SIZE_BYTES:
        raise RuntimeError(
            f"CORE_SECRETS_MASTER_KEY must decode to {_KEY_SIZE_BYTES} bytes, got {len(key)}"
        )
    return key


def encrypt(payload: dict) -> tuple[bytes, bytes]:
    key = load_master_key()
    nonce = os.urandom(_NONCE_SIZE_BYTES)
    plaintext = json.dumps(payload).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes) -> dict:
    key = load_master_key()
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return json.loads(plaintext)
```

- [ ] **Step 6: Verify the layering contract holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` — `crypto.py` imports nothing from
any other `app.*` module, so this can't yet fail; this step just confirms
the layers-list edit itself is syntactically valid and doesn't break the
existing contract before any real cross-module import is added in later
tasks.

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_crypto.py -v`
Expected: 6 passed.

- [ ] **Step 8: Commit**

```bash
git add core/app/secrets/__init__.py core/app/secrets/crypto.py \
  core/pyproject.toml core/tests/test_secrets_crypto.py core/uv.lock
git commit -m "feat(core): secrets module — AES-GCM encryption primitive"
```

---

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

## Task 3: Data model + migration — `connector_secrets`

**Files:**
- Create: `core/app/secrets/models.py`
- Create: `core/alembic/versions/0019_connector_secrets.py`
- Modify: `core/app/db.py` (register the model in `core_table_names()`)
- Modify: `core/pyproject.toml` (`ignore_imports` entry for `app.db ->
  app.secrets.models`)
- Test: `core/tests/test_secrets_models.py`

**Interfaces:**
- Produces: `app.secrets.models.ConnectorSecret` (SQLAlchemy model:
  `id: str`, `tenant_id: str`, `name: str`, `kind: str`, `ciphertext:
  bytes`, `nonce: bytes`, `created_by: str`, `created_at: datetime`,
  `updated_at: datetime`, unique on `(tenant_id, name)`). Consumed by Task 4
  (`repository.py`) and Task 5 (`routes.py`'s `_to_response`).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_secrets_models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.exc import IntegrityError

from app.db import init_db, make_engine, make_session_factory
from app.secrets.models import ConnectorSecret
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_connector_secrets_table_is_registered():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    assert sa_inspect(engine).has_table("connector_secrets")


def test_connector_secret_row_round_trip():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        secret = ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="my-api", kind="bearer_token",
            ciphertext=b"cipher", nonce=b"nonce123456", created_by=user.id,
        )
        s.add(secret)
        s.commit()
        fetched = s.get(ConnectorSecret, "sec1")
        assert fetched.name == "my-api"
        assert fetched.kind == "bearer_token"
        assert fetched.created_at is not None
        assert fetched.updated_at is not None


def test_connector_secret_unique_name_per_tenant():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
        s.add(ConnectorSecret(
            id="sec1", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c1", nonce=b"n1", created_by=user.id,
        ))
        s.commit()
        s.add(ConnectorSecret(
            id="sec2", tenant_id=tenant.id, name="dup", kind="bearer_token",
            ciphertext=b"c2", nonce=b"n2", created_by=user.id,
        ))
        with pytest.raises(IntegrityError):
            s.commit()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.secrets.models'`.

- [ ] **Step 3: Implement `models.py`**

Create `core/app/secrets/models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, LargeBinary, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConnectorSecret(Base):
    __tablename__ = "connector_secrets"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    name: Mapped[str] = mapped_column(String, nullable=False)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    ciphertext: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    nonce: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)

    __table_args__ = (
        UniqueConstraint("tenant_id", "name", name="uq_connector_secrets_tenant_name"),
    )
```

- [ ] **Step 4: Register the model so `init_db()`/`create_all()` picks it up**

Modify `core/app/db.py` — in `core_table_names()`, add (alphabetically,
between `pipelines_models` and `sharing_models`):

```python
    from app.secrets import models as secrets_models  # noqa: F401
```

- [ ] **Step 5: Add the import-linter exemption**

Modify `core/pyproject.toml` — in the `ignore_imports` list (same
`[[tool.importlinter.contracts]]` block as Task 1 Step 4), add:

```toml
    "app.db -> app.secrets.models",
```

(This mirrors the 10 existing entries — `app.db` imports every module's
`models.py` to register it on `Base.metadata`, which the layers contract
would otherwise flag; every existing model module already has this exact
exemption.)

- [ ] **Step 6: Write the migration**

Create `core/alembic/versions/0019_connector_secrets.py`:

```python
"""app.secrets — connector_secrets (SP-15e)

Revision ID: 0019
Revises: 0018
Create Date: 2026-08-06
"""
import sqlalchemy as sa
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "connector_secrets",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=False),
        sa.Column("nonce", sa.LargeBinary(), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint("tenant_id", "name", name="uq_connector_secrets_tenant_name"),
    )


def downgrade() -> None:
    op.drop_table("connector_secrets")
```

- [ ] **Step 7: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.`

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_models.py -v`
Expected: 3 passed.

- [ ] **Step 9: Commit**

```bash
git add core/app/secrets/models.py core/alembic/versions/0019_connector_secrets.py \
  core/app/db.py core/pyproject.toml core/tests/test_secrets_models.py
git commit -m "feat(core): secrets module — connector_secrets table + migration"
```

---

## Task 4: Repository — `core/app/secrets/repository.py`

**Files:**
- Create: `core/app/secrets/repository.py`
- Test: `core/tests/test_secrets_repository.py`

**Interfaces:**
- Consumes: `ConnectorSecret` (Task 3), `crypto.encrypt`/`decrypt` (Task 1),
  `SECRET_PAYLOAD_ADAPTER`/`SecretPayload` (Task 2).
- Produces: `get_secret(session, *, tenant_id, secret_id) ->
  ConnectorSecret | None`, `get_secret_by_name(session, *, tenant_id, name)
  -> ConnectorSecret | None`, `create_secret(session, *, tenant_id,
  created_by, name, kind, ciphertext, nonce) -> ConnectorSecret`,
  `list_secrets(session, *, tenant_id) -> list[ConnectorSecret]`,
  `delete_secret(session, secret) -> None`, `get_secret_payload(session, *,
  tenant_id, name) -> SecretPayload | None`. Consumed by Task 5
  (`routes.py`); `get_secret_payload` is consumed by the future SP-15f (out
  of scope here, but its exact signature is load-bearing — do not change it
  without updating this note).

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_secrets_repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy.exc import IntegrityError

from app.db import init_db, make_engine, make_session_factory
from app.secrets import repository as repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant_and_user(session):
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    return tenant, user


def test_create_and_get_secret_by_name(session, tenant_and_user):
    tenant, user = tenant_and_user
    secret = repo.create_secret(
        session, tenant_id=tenant.id, created_by=user.id, name="my-api",
        kind="bearer_token", ciphertext=b"cipher", nonce=b"nonce",
    )
    fetched = repo.get_secret_by_name(session, tenant_id=tenant.id, name="my-api")
    assert fetched.id == secret.id


def test_create_secret_duplicate_name_per_tenant_raises(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name="dup",
                        kind="bearer_token", ciphertext=b"c1", nonce=b"n1")
    with pytest.raises(IntegrityError):
        repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name="dup",
                            kind="bearer_token", ciphertext=b"c2", nonce=b"n2")


def test_list_secrets_scoped_to_tenant(session, tenant_and_user):
    tenant, user = tenant_and_user
    repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name="a",
                        kind="bearer_token", ciphertext=b"c", nonce=b"n")
    assert [s.name for s in repo.list_secrets(session, tenant_id=tenant.id)] == ["a"]
    assert repo.list_secrets(session, tenant_id="other-tenant") == []


def test_get_secret_cross_tenant_returns_none(session, tenant_and_user):
    tenant, user = tenant_and_user
    secret = repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name="a",
                                 kind="bearer_token", ciphertext=b"c", nonce=b"n")
    assert repo.get_secret(session, tenant_id="other-tenant", secret_id=secret.id) is None


def test_delete_secret_removes_row(session, tenant_and_user):
    tenant, user = tenant_and_user
    secret = repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name="a",
                                 kind="bearer_token", ciphertext=b"c", nonce=b"n")
    repo.delete_secret(session, secret)
    assert repo.get_secret(session, tenant_id=tenant.id, secret_id=secret.id) is None


@pytest.mark.parametrize("raw_payload", [
    {"kind": "api_key", "location": "header", "key": "X-API-Key", "value": "abc"},
    {"kind": "api_key", "location": "query", "key": "token", "value": "abc123"},
    {"kind": "bearer_token", "token": "s3cr3t"},
    {"kind": "basic_auth", "username": "u", "password": "p"},
    {"kind": "oauth2_client_credentials", "tokenUrl": "https://example.test/token",
     "clientId": "cid", "clientSecret": "csecret"},
    {"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"},
])
def test_get_secret_payload_round_trip_for_every_kind(session, tenant_and_user, monkeypatch, raw_payload):
    # Spec §8: confirms the Pydantic discriminant recovers the right variant
    # after decryption, for all five kinds (incl. both api_key placements) —
    # not just one, since encrypt/decrypt themselves are kind-agnostic and a
    # coverage gap here would only be caught by luck otherwise.
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    from app.secrets import crypto

    tenant, user = tenant_and_user
    ciphertext, nonce = crypto.encrypt(raw_payload)
    repo.create_secret(session, tenant_id=tenant.id, created_by=user.id, name=raw_payload["kind"],
                        kind=raw_payload["kind"], ciphertext=ciphertext, nonce=nonce)
    payload = repo.get_secret_payload(session, tenant_id=tenant.id, name=raw_payload["kind"])
    assert payload.kind == raw_payload["kind"]


def test_get_secret_payload_missing_name_returns_none(session, tenant_and_user):
    tenant, _user = tenant_and_user
    assert repo.get_secret_payload(session, tenant_id=tenant.id, name="nope") is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.secrets.repository'`.

- [ ] **Step 3: Implement `repository.py`**

Create `core/app/secrets/repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.secrets.crypto import decrypt
from app.secrets.models import ConnectorSecret
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretPayload


def get_secret(session: Session, *, tenant_id: str, secret_id: str) -> ConnectorSecret | None:
    return session.scalar(select(ConnectorSecret).where(
        ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.id == secret_id))


def get_secret_by_name(session: Session, *, tenant_id: str, name: str) -> ConnectorSecret | None:
    return session.scalar(select(ConnectorSecret).where(
        ConnectorSecret.tenant_id == tenant_id, ConnectorSecret.name == name))


def create_secret(
    session: Session, *, tenant_id: str, created_by: str, name: str, kind: str,
    ciphertext: bytes, nonce: bytes,
) -> ConnectorSecret:
    secret = ConnectorSecret(
        id=uuid.uuid4().hex, tenant_id=tenant_id, name=name, kind=kind,
        ciphertext=ciphertext, nonce=nonce, created_by=created_by,
    )
    session.add(secret)
    session.flush()
    session.refresh(secret)
    return secret


def list_secrets(session: Session, *, tenant_id: str) -> list[ConnectorSecret]:
    return list(session.scalars(
        select(ConnectorSecret).where(ConnectorSecret.tenant_id == tenant_id)
        .order_by(ConnectorSecret.name)
    ).all())


def delete_secret(session: Session, secret: ConnectorSecret) -> None:
    session.delete(secret)
    session.flush()


def get_secret_payload(session: Session, *, tenant_id: str, name: str) -> SecretPayload | None:
    """Déchiffre. Usage interne uniquement (ex. futur runtime SP-15f) —
    jamais appelé depuis un handler de route qui sérialise sa sortie en
    JSON (design §5)."""
    secret = get_secret_by_name(session, tenant_id=tenant_id, name=name)
    if secret is None:
        return None
    return SECRET_PAYLOAD_ADAPTER.validate_python(decrypt(secret.ciphertext, secret.nonce))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_repository.py -v`
Expected: 12 passed (5 CRUD/isolation tests + 6 parametrized
round-trip-per-kind cases + 1 missing-name case).

- [ ] **Step 5: Commit**

```bash
git add core/app/secrets/repository.py core/tests/test_secrets_repository.py
git commit -m "feat(core): secrets module — repository (CRUD + decrypt-on-demand)"
```

---

## Task 5: Routes + admin gate + audit + `app.main` wiring

**Files:**
- Create: `core/app/secrets/routes.py`
- Modify: `core/app/main.py` (mount router, eager boot-time key check)
- Modify: `core/tests/conftest.py` (fixed test master key default)
- Test: `core/tests/test_secrets_routes.py`

**Interfaces:**
- Consumes: `repository.*` (Task 4), `crypto.encrypt`/`load_master_key`
  (Task 1), `SecretCreate` (Task 2), `ConnectorSecret` (Task 3).
- Produces: `app.secrets.routes.router` (FastAPI `APIRouter`, mounted in
  `app.main.create_app()`). Terminal task of this plan — SP-15f (out of
  scope) will be the next consumer, of `repository.get_secret_payload`
  only, not of anything in this file.

- [ ] **Step 1: Add the fixed test master key default to `conftest.py`**

Modify `core/tests/conftest.py` — change the docstring and add the
`setdefault` call, right after the imports:

```python
# SPDX-License-Identifier: Apache-2.0
"""Fixtures partagées. Les fixtures SQLite restent locales à chaque fichier
(pattern existant) ; ce conftest ne porte que l'infra PostGIS optionnelle
et la clé de test fixe du coffre de secrets (SP-15e, ci-dessous)."""
import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.db import make_session_factory

# Valeur fixe, committée, dev/test uniquement — create_app() (SP-15e)
# valide CORE_SECRETS_MASTER_KEY de façon eager ; sans ce défaut, TOUT test
# appelant create_app() (le pattern `env()` répété dans tout le dépôt)
# échouerait à la collecte. setdefault() : un test qui monkeypatch.setenv()
# explicitement (ex. test_secrets_crypto.py) reste maître de sa propre
# valeur.
os.environ.setdefault(
    "CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
)
```

(Everything below this point in `conftest.py` — the `pg_engine` fixture
onward — is unchanged.)

- [ ] **Step 2: Write the failing tests**

Create `core/tests/test_secrets_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

BEARER_BODY = {
    "name": "weather-api",
    "payload": {"kind": "bearer_token", "token": "s3cr3t-token-value"},
}


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="a", username="admin",
                                   email=None, first_name="", last_name="", bootstrap_admin=True)
        regular = get_or_create_user(s, tenant_id=tenant.id, oidc_sub="r", username="regular",
                                     email=None, first_name="", last_name="")
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    return app, client, Session, admin, regular


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_create_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.post("/secrets", json=BEARER_BODY).status_code == 403


def test_list_requires_admin(env):
    app, client, _, _admin, regular = env
    _as(app, regular)
    assert client.get("/secrets").status_code == 403


def test_delete_requires_admin(env):
    app, client, _, admin, regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    _as(app, regular)
    assert client.delete(f"/secrets/{created['id']}").status_code == 403


def test_create_and_list(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/secrets", json=BEARER_BODY)
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "weather-api"
    assert body["kind"] == "bearer_token"
    assert set(body) == {"id", "name", "kind", "createdAt", "updatedAt"}
    listed = client.get("/secrets").json()
    assert [s["name"] for s in listed] == ["weather-api"]


def test_create_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    r = client.post("/secrets", json=BEARER_BODY)
    assert "s3cr3t-token-value" not in r.text


def test_list_response_never_leaks_secret_value(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/secrets", json=BEARER_BODY)
    r = client.get("/secrets")
    assert "s3cr3t-token-value" not in r.text


def test_create_duplicate_name_conflicts(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    client.post("/secrets", json=BEARER_BODY)
    r = client.post("/secrets", json=BEARER_BODY)
    assert r.status_code == 409


def test_delete_removes_secret(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    assert client.delete(f"/secrets/{created['id']}").status_code == 204
    assert client.get("/secrets").json() == []


def test_delete_missing_returns_404(env):
    app, client, _, admin, _regular = env
    _as(app, admin)
    assert client.delete("/secrets/does-not-exist").status_code == 404


def test_delete_cross_tenant_returns_404(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()

    with Session() as s:
        other_tenant = Tenant(id=uuid.uuid4().hex, slug="other", name="Other")
        s.add(other_tenant)
        s.flush()
        other_admin = get_or_create_user(
            s, tenant_id=other_tenant.id, oidc_sub="oa", username="other-admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()

    _as(app, other_admin)
    assert client.delete(f"/secrets/{created['id']}").status_code == 404


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular = env
    _as(app, admin)
    created = client.post("/secrets", json=BEARER_BODY).json()
    client.delete(f"/secrets/{created['id']}")

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
        payloads = list(s.scalars(select(AuditLog.payload)))
    assert actions == ["secret.create", "secret.delete"]
    assert all("s3cr3t-token-value" not in str(p) for p in payloads)


def test_create_app_fails_fast_without_master_key(monkeypatch):
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    with pytest.raises(KeyError):
        create_app()
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_secrets_routes.py -v`
Expected: FAIL — every HTTP-hitting test gets a 404 (no `/secrets` route
mounted yet); `test_create_app_fails_fast_without_master_key` fails with
`Failed: DID NOT RAISE <class 'KeyError'>` (the eager check doesn't exist
in `create_app()` yet).

- [ ] **Step 4: Implement `routes.py`**

Create `core/app/secrets/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST du coffre de secrets (design SP-15e §6) — admin-only, ne
retourne jamais une valeur déchiffrée, un ciphertext ou un nonce."""
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.secrets import crypto
from app.secrets import repository as repo
from app.secrets.models import ConnectorSecret
from app.secrets.schemas import SecretCreate
from app.users.models import User

router = APIRouter()


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


class ConnectorSecretOut(BaseModel):
    id: str
    name: str
    kind: str
    createdAt: str
    updatedAt: str


def _to_response(secret: ConnectorSecret) -> ConnectorSecretOut:
    return ConnectorSecretOut(
        id=secret.id, name=secret.name, kind=secret.kind,
        createdAt=secret.created_at.isoformat(), updatedAt=secret.updated_at.isoformat(),
    )


@router.post("/secrets", status_code=201)
def create_secret_route(
    body: SecretCreate,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
) -> ConnectorSecretOut:
    _require_admin(user)
    if repo.get_secret_by_name(session, tenant_id=user.tenant_id, name=body.name):
        raise HTTPException(status_code=409, detail="secret name already exists")
    ciphertext, nonce = crypto.encrypt(body.payload.model_dump())
    secret = repo.create_secret(
        session, tenant_id=user.tenant_id, created_by=user.id, name=body.name,
        kind=body.payload.kind, ciphertext=ciphertext, nonce=nonce,
    )
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="secret.create", object_type="secret", object_id=secret.id,
                payload={"name": secret.name, "kind": secret.kind})
    return _to_response(secret)


@router.get("/secrets")
def list_secrets_route(
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
) -> list[ConnectorSecretOut]:
    _require_admin(user)
    return [_to_response(s) for s in repo.list_secrets(session, tenant_id=user.tenant_id)]


@router.delete("/secrets/{secret_id}", status_code=204)
def delete_secret_route(
    secret_id: str,
    user: User = Depends(get_current_user), session: Session = Depends(get_session),
) -> None:
    _require_admin(user)
    secret = repo.get_secret(session, tenant_id=user.tenant_id, secret_id=secret_id)
    if secret is None:
        raise HTTPException(status_code=404, detail="secret not found")
    name, kind = secret.name, secret.kind
    repo.delete_secret(session, secret)
    write_audit(session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
                action="secret.delete", object_type="secret", object_id=secret_id,
                payload={"name": name, "kind": kind})
```

- [ ] **Step 5: Wire `app.main`**

Modify `core/app/main.py` — add to the import block, between the existing
`from app.public import routes as public_routes` line and `from
app.schemas_routes import router as schemas_router` (alphabetical position
in that block):

```python
from app.public import routes as public_routes
from app.secrets import crypto as secrets_crypto
from app.secrets import routes as secrets_routes
from app.schemas_routes import router as schemas_router
```

In `create_app()`, right after `observability.setup()`, add the eager
boot-time check (before anything touches the DB — a misconfigured key
should fail before the app does any other work):

```python
def create_app() -> FastAPI:
    observability.setup()
    secrets_crypto.load_master_key()  # échec rapide si absente/mal formée (design SP-15e §4/§8)
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
```

In the `app.include_router(...)` block, add right after
`app.include_router(extensions_routes.router)`:

```python
    app.include_router(secrets_routes.router)
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_secrets_routes.py -v`
Expected: 12 passed.

- [ ] **Step 7: Verify the layering contract still holds**

Run: `cd core && uv run lint-imports`
Expected: `Contracts: 1 kept, 0 broken.` (`routes.py` imports `app.audit`,
`app.auth`, `app.users`, `app.db` — all below `app.secrets`'s position in
the layers list, per the Global Constraints check done in Task 1.)

- [ ] **Step 8: Run the full existing test suite to confirm no regression**

Run: `cd core && uv run pytest -v`
Expected: all pre-existing tests still pass — the `CORE_SECRETS_MASTER_KEY`
default added in Step 1 is exactly what keeps every other test file's
`create_app()` call (or equivalent) working unchanged.

- [ ] **Step 9: Commit**

```bash
git add core/app/secrets/routes.py core/app/main.py core/tests/conftest.py \
  core/tests/test_secrets_routes.py
git commit -m "feat(core): secrets module — REST routes, admin gate, audit, app wiring"
```
