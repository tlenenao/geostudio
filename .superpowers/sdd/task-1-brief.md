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

