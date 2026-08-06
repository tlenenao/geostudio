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
