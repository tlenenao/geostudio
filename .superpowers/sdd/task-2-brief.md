## Task 2: Interdire le mode mock hors développement (3.1)

**Files:**
- Modify: `core/app/main.py` (add boot guard call in `create_app()`)
- Modify: `core/app/auth/dependency.py` (add `_reject_mock_outside_development()` next to `_mock_mode()`)
- Modify: `core/tests/conftest.py` (add `CORE_ENV` default, mirroring the existing `CORE_SECRETS_MASTER_KEY` default)
- Modify: `docker-compose.yml` (add `CORE_ENV: ${CORE_ENV:-development}` to the `core` service)
- Modify: `.env.example` (document `CORE_ENV`)
- Test: `core/tests/test_mock_mode_guard.py` (new)

**Interfaces:**
- Consumes: nothing new from Task 1.
- Produces: nothing consumed by later tasks in this plan (Task 3's RFC 7807 handler and Task 4's rate limiter don't depend on this guard).

**Context:** `core/app/auth/dependency.py:16-17` defines `_mock_mode()`, read per-request by `get_current_user`. `core/app/main.py:99-101` is `create_app()`'s first two lines — `observability.setup()` then the existing `secrets_crypto.load_master_key()` fail-fast call. The new guard goes immediately after, same style. `core/tests/conftest.py:19` already does `os.environ.setdefault("CORE_SECRETS_MASTER_KEY", ...)` specifically so every test calling `create_app()` doesn't need to set it explicitly — `CORE_ENV` needs the identical treatment or every one of the dozens of `env()`-fixture test files across the suite that call `create_app()` with `CORE_AUTH_MODE=mock` (the default when unset) will start failing at collection/setup time.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_mock_mode_guard.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.main import create_app


def test_mock_mode_without_development_marker_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.delenv("CORE_ENV", raising=False)
    with pytest.raises(RuntimeError, match="CORE_AUTH_MODE=mock requires CORE_ENV=development"):
        create_app()


def test_mock_mode_with_development_marker_boots(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ENV", "development")
    create_app()  # doit ne pas lever


def test_oidc_mode_boots_regardless_of_core_env(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.delenv("CORE_ENV", raising=False)
    create_app()  # doit ne pas lever : la garde ne concerne que le mode mock
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd core
uv run pytest tests/test_mock_mode_guard.py -v
```

Expected: `test_mock_mode_without_development_marker_refuses_to_boot` FAILS (no `RuntimeError` raised — `create_app()` currently boots fine in mock mode with no `CORE_ENV` check). The other two currently PASS already (nothing to break yet), which is fine — only the first assertion is new behavior.

- [ ] **Step 3: Implement the guard**

Edit `core/app/auth/dependency.py`, immediately after `_mock_mode()`:

```python
def _mock_mode() -> bool:
    return os.environ.get("CORE_AUTH_MODE", "oidc") == "mock"


def reject_mock_outside_development() -> None:
    """Appelée une fois au démarrage (create_app()), pas par requête —
    contrairement à _mock_mode() ci-dessus. C6 (revue de projet 2026-08-20) :
    CORE_AUTH_MODE=mock donne bootstrap_admin=True à quiconque présente un
    Bearer non vide (cf. get_current_user plus bas), sans aucune vérification
    d'environnement jusqu'ici. CORE_ENV=development est un marqueur explicite,
    pas une valeur par défaut sûre — un déploiement qui omet CORE_ENV ET met
    CORE_AUTH_MODE=mock est traité comme une erreur de configuration,
    jamais comme "sans doute du dev"."""
    if _mock_mode() and os.environ.get("CORE_ENV") != "development":
        raise RuntimeError("CORE_AUTH_MODE=mock requires CORE_ENV=development")
```

Edit `core/app/main.py`:

```python
def create_app() -> FastAPI:
    observability.setup()
    secrets_crypto.load_master_key()  # échec rapide si absente/mal formée (design SP-15e §4/§8)
    reject_mock_outside_development()  # échec rapide si mock hors dev (design SP-26 §3.1)
    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
```

Add the import near the existing `from app.auth.dependency import (...)` block in `main.py`:

```python
from app.auth.dependency import (
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
    reject_mock_outside_development,
)
```

- [ ] **Step 4: Add the conftest default so the rest of the suite doesn't break**

Edit `core/tests/conftest.py`, right after the existing `CORE_SECRETS_MASTER_KEY` default:

```python
os.environ.setdefault("CORE_SECRETS_MASTER_KEY", "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=")
# Même raison, même patron (SP-26/3.1) : create_app() refuse désormais de
# démarrer en CORE_AUTH_MODE=mock (le défaut de _mock_mode() quand la
# variable est absente) sans CORE_ENV=development. setdefault() : un test
# qui monkeypatch.setenv("CORE_ENV", ...) explicitement reste maître de sa
# propre valeur (ex. test_mock_mode_guard.py ci-dessus).
os.environ.setdefault("CORE_ENV", "development")
```

- [ ] **Step 5: Run the new test file and the full suite**

```bash
cd core
uv run pytest tests/test_mock_mode_guard.py -v
# Expected: 3 passed
uv run pytest -x -q
# Expected: 1878+3 passed (1881), 5 skipped, 0 failed — no regression
# elsewhere from the conftest.py change
```

If any pre-existing test fails, it's calling `create_app()` after an explicit `monkeypatch.delenv("CORE_ENV", ...)` or in a fixture that clears the environment wholesale — find that fixture and add `monkeypatch.setenv("CORE_ENV", "development")` there rather than weakening the guard.

- [ ] **Step 6: Wire `CORE_ENV` into the dev compose and document it**

Edit `docker-compose.yml`, in the `core` service's `environment:` block, right after `CORE_AUTH_MODE`:

```yaml
      CORE_AUTH_MODE: ${CORE_AUTH_MODE:-mock}
      # Marqueur explicite requis par la garde de démarrage SP-26/3.1 :
      # CORE_AUTH_MODE=mock sans CORE_ENV=development refuse de démarrer.
      # docker-compose.prod.yml force déjà CORE_AUTH_MODE=oidc sans
      # indirection par variable — cette garde n'y a donc jamais l'occasion
      # de se déclencher, c'est un filet pour tout déploiement du fichier
      # de base seul, sans l'overlay prod.
      CORE_ENV: ${CORE_ENV:-development}
```

Edit `.env.example`, right after the existing `CORE_AUTH_MODE` block:

```
# ─── Cœur : mode d'authentification ──────────────────────
# "mock" pour dev/e2e (aucun accès réseau à Keycloak requis) ; "oidc" en usage réel.
CORE_AUTH_MODE=mock
# Marqueur explicite requis quand CORE_AUTH_MODE=mock (SP-26/3.1) — le
# cœur refuse de démarrer sinon. Ne jamais mettre "development" sur une
# instance exposée publiquement.
CORE_ENV=development
CORE_OIDC_ISSUER=http://localhost:8180/realms/geostudio
```

- [ ] **Step 7: Verify the deployability guard still passes**

```bash
cd core
uv run pytest tests/test_deployability.py -v
```

Expected: 31 passed (`CORE_ENV` is now both wired to `core` and documented in `.env.example` — neither rule should regress).

- [ ] **Step 8: Commit**

```bash
git add core/app/main.py core/app/auth/dependency.py core/tests/conftest.py core/tests/test_mock_mode_guard.py docker-compose.yml .env.example
git commit -m "$(cat <<'EOF'
feat(core): refuse de démarrer en mode mock hors CORE_ENV=development

CORE_AUTH_MODE=mock donnait bootstrap_admin=True à tout Bearer non vide
sans aucune vérification d'environnement (C6, revue de projet
2026-08-20). Garde fail-fast au boot, même emplacement/patron que
load_master_key().

Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
EOF
)"
```

---

