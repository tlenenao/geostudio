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

