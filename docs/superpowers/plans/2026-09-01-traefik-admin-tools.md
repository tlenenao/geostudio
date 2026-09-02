# URLs cohérentes derrière Traefik pour les outils d'infrastructure — Plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Donner à Martin, Titiler et Grafana une URL `/admin/<outil>` cohérente
avec le reste de la plateforme, protégée par un gate cookie que seul un
admin peut ouvrir depuis le shell — MinIO reste hors de ce gate (limite
technique confirmée, cf. spec §1/§5) mais gagne un lien de découverte dans
la même page.

**Architecture:** Nouveau module `core/app/admin_tools/` : un jeton de
lancement HMAC à usage unique (60s, mint via Bearer JWT authentifié admin)
qui bootstrap un cookie de session HttpOnly/Secure (30 min), vérifié à
chaque requête par le `forwardAuth` de Traefik sur trois nouveaux routeurs
(`/admin/martin`, `/admin/titiler`, `/admin/grafana`). Chaque outil reçoit sa
propre configuration de sous-chemin (vérifiée contre l'image réelle, cf.
spec §5) : `--base-path` pour Martin, `TITILER_API_ROOT_PATH` pour Titiler,
`GF_SERVER_ROOT_URL`/`GF_SERVER_SERVE_FROM_SUB_PATH` pour Grafana (ce
dernier sans `stripprefix`, à la différence des deux autres).

**Tech Stack:** FastAPI (PyJWT `HS256`, même patron que
`app/auth/export_tokens.py`), Traefik v3 (labels Docker, middleware
`forwardauth`), React/TanStack Query (patron `ItemClient` existant).

## Global Constraints

- Docs et identifiants de test en français (CLAUDE.md) ; code/identifiants
  en anglais.
- TDD systématique : test qui échoue avant l'implémentation, à chaque étape.
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), petits, un
  sujet par commit.
- Ne jamais introduire de cookie sans `HttpOnly; Secure; SameSite=Strict` —
  c'est le **premier** cookie de tout ce dépôt (jusqu'ici Bearer-ou-rien,
  `core/app/main.py:61-66`) : périmètre volontairement restreint à ce seul
  usage, ne pas le généraliser ailleurs dans ce plan.
- Après toute modification de route/modèle du cœur : régénérer la spec
  OpenAPI + les types TS (piège n°1 du dépôt) avec l'incantation exacte
  (cf. Tâche 3, dernière étape) — jamais la commande nue.
- `docker compose config` (base seul, puis base+overlay prod) doit rester
  syntaxiquement valide après chaque tâche touchant un fichier compose
  (piège n°2 : « livré ≠ câblé »).
- Aucune tâche de ce plan ne touche `MARTIN_SECRET`, `docker-compose.yml`
  section `minio`, ni aucun fichier de `deploy/postgis/` — hors périmètre.

## Décisions tranchées (questions ouvertes de la spec §8)

- **Pas de révocation de session avant l'expiration TTL** (30 min). Une
  déconnexion du shell (logout OIDC) ne révoque pas un cookie
  `gs_admin_session` déjà posé. Même choix assumé que
  `app/auth/export_tokens.py` (SP-17a) : aucun précédent de jeton à usage
  unique « déjà consommé » dans ce dépôt, révocation par TTL seul.
- **Pas d'entrée `audit_log`** pour `POST /admin-tools/launch/{tool}`. Les
  lignes `audit_log` de ce dépôt sont attachées à un objet cible
  (item/collection/utilisateur) — cette action ne mute aucune donnée et
  n'a pas d'objet cible naturel ; la frontière de sécurité réelle est le
  403 de `_require_admin`, pas une trace d'audit. Cohérent avec
  `GET /collections` (lecture admin, non audité). Aucune tâche de ce plan
  n'écrit dans `audit_log`.

---

## Task 1 : capacité `adminToolsEnabled` (flag + parité `/instance`/`/me`)

**Files:**
- Modify: `core/app/auth/dependency.py` (ajout après `is_copilot_enabled()`,
  fin de fichier, ligne 100)
- Modify: `core/app/instance/routes.py`
- Modify: `core/app/auth/routes.py` (lignes 10-19, 29-45, 82-90)
- Test: `core/tests/test_admin_tools_enabled_flag.py` (nouveau)
- Test: `core/tests/test_auth_me_capabilities.py` (modifier
  `CAPABILITY_KEYS` et `_CAPABILITY_PROBES`)

**Interfaces:**
- Produces: `is_admin_tools_enabled() -> bool` dans
  `app.auth.dependency` — consommée par la Tâche 3 (`app/main.py`,
  `app/admin_tools/routes.py`) et déjà par cette tâche
  (`/instance`, `/me`).

- [ ] **Step 1: Écrire le test du flag (échoue)**

Créer `core/tests/test_admin_tools_enabled_flag.py` :

```python
# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_admin_tools_enabled


def test_is_admin_tools_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_ADMIN_TOOLS_ENABLED", raising=False)
    assert is_admin_tools_enabled() is False


def test_is_admin_tools_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    assert is_admin_tools_enabled() is True
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "false")
    assert is_admin_tools_enabled() is False
```

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd core && uv run pytest tests/test_admin_tools_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_admin_tools_enabled'`

- [ ] **Step 3: Ajouter la fonction dans `dependency.py`**

À la fin de `core/app/auth/dependency.py` (après `is_copilot_enabled()`,
qui se termine ligne 99) :

```python


def is_admin_tools_enabled() -> bool:
    """CORE_ADMIN_TOOLS_ENABLED — capacité instance-wide optionnelle, même
    convention que is_tileset3d_enabled : lue à chaque appel, sans cache.
    Défaut false : les trois routes /admin-tools/* ne sont montées que si
    l'opérateur a explicitement activé la capacité (design URLs admin §3)."""
    return os.environ.get("CORE_ADMIN_TOOLS_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Lancer le test, vérifier qu'il passe**

Run: `cd core && uv run pytest tests/test_admin_tools_enabled_flag.py -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Écrire le test de parité `/instance`/`/me` (échoue)**

Dans `core/tests/test_auth_me_capabilities.py`, modifier `CAPABILITY_KEYS`
(ligne 20-28) :

```python
CAPABILITY_KEYS = {
    "readOnly",
    "etlEnabled",
    "exportEnabled",
    "appExportEnabled",
    "tileset3dEnabled",
    "terrain3dEnabled",
    "copilotEnabled",
    "adminToolsEnabled",
}
```

Et `_CAPABILITY_PROBES` (ligne 121-132), ajouter une entrée après celle de
`copilotEnabled` :

```python
_CAPABILITY_PROBES = [
    ("CORE_READ_ONLY_MODE", "readOnly", "true", "false"),
    ("CORE_ETL_ENABLED", "etlEnabled", "true", "false"),
    ("CORE_EXPORT_ENABLED", "exportEnabled", "true", "false"),
    ("CORE_APPEXPORT_ENABLED", "appExportEnabled", "true", "false"),
    ("CORE_TILESET3D_ENABLED", "tileset3dEnabled", "true", "false"),
    ("CORE_TERRAIN3D_ENABLED", "terrain3dEnabled", "true", "false"),
    ("CORE_LLM_PROVIDER", "copilotEnabled", "openai", ""),
    ("CORE_ADMIN_TOOLS_ENABLED", "adminToolsEnabled", "true", "false"),
]
```

- [ ] **Step 6: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_auth_me_capabilities.py -v`
Expected: FAIL — `KeyError: 'adminToolsEnabled'` (le champ n'existe pas
encore dans les réponses de `/me`/`/instance`)

- [ ] **Step 7: Wire dans `/instance` et `/me`**

`core/app/instance/routes.py` — fichier complet :

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import (
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "appExportEnabled": is_appexport_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
        "terrain3dEnabled": is_terrain3d_enabled(),
        "copilotEnabled": is_copilot_enabled(),
        "adminToolsEnabled": is_admin_tools_enabled(),
    }
```

`core/app/auth/routes.py` — modifier l'import (lignes 10-19) :

```python
from app.auth.dependency import (
    get_current_user,
    is_admin_tools_enabled,
    is_appexport_enabled,
    is_copilot_enabled,
    is_etl_enabled,
    is_export_enabled,
    is_read_only_mode,
    is_terrain3d_enabled,
    is_tileset3d_enabled,
)
```

Puis `MeCapabilities` (lignes 29-45) — ajouter le champ :

```python
class MeCapabilities(BaseModel):
    """Les capacités du déploiement, servies avec le profil.

    Même contenu que `GET /instance`, qui reste servi sans authentification
    (page de connexion, mode démo). Le doublon est délibéré : le shell dérive
    l'état de ses domaines d'un profil unique (spec §6.6) au lieu de croiser
    deux requêtes dans chaque écran. `tests/test_auth_me_capabilities.py`
    interdit aux deux routes de diverger.
    """

    readOnly: bool
    etlEnabled: bool
    exportEnabled: bool
    appExportEnabled: bool
    tileset3dEnabled: bool
    terrain3dEnabled: bool
    copilotEnabled: bool
    adminToolsEnabled: bool
```

Et dans `get_me()` (lignes 82-90) :

```python
        capabilities=MeCapabilities(
            readOnly=is_read_only_mode(),
            etlEnabled=is_etl_enabled(),
            exportEnabled=is_export_enabled(),
            appExportEnabled=is_appexport_enabled(),
            tileset3dEnabled=is_tileset3d_enabled(),
            terrain3dEnabled=is_terrain3d_enabled(),
            copilotEnabled=is_copilot_enabled(),
            adminToolsEnabled=is_admin_tools_enabled(),
        ),
```

- [ ] **Step 8: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_auth_me_capabilities.py tests/test_admin_tools_enabled_flag.py -v`
Expected: PASS (tous)

- [ ] **Step 9: Suite complète du cœur (non-régression)**

Run: `cd core && uv run pytest -q`
Expected: aucune régression par rapport au dernier comptage de référence
(`CLAUDE.md`, section Commandes)

- [ ] **Step 10: Commit**

```bash
git add core/app/auth/dependency.py core/app/instance/routes.py \
  core/app/auth/routes.py core/tests/test_admin_tools_enabled_flag.py \
  core/tests/test_auth_me_capabilities.py
git commit -m "feat(core): capacité adminToolsEnabled sur /instance et /me"
```

---

## Task 2 : jetons de lancement et de session (`app/admin_tools/tokens.py`)

**Files:**
- Create: `core/app/admin_tools/__init__.py` (vide)
- Create: `core/app/admin_tools/tokens.py`
- Test: `core/tests/test_admin_tools_tokens.py`

**Interfaces:**
- Consumes: rien (module autonome, pas de dépendance sur la Tâche 1 au
  niveau code — seulement `CORE_ADMIN_TOOLS_TOKEN_SECRET`, une variable
  d'environnement distincte de `CORE_ADMIN_TOOLS_ENABLED`).
- Produces (consommé par la Tâche 3) :
  `mint_launch_token(*, sub: str, tool: str) -> str`,
  `decode_launch_token(token: str) -> LaunchTokenClaims` (`.sub: str`,
  `.tool: str`), `mint_session_token(*, sub: str) -> str`,
  `decode_session_token(token: str) -> SessionTokenClaims` (`.sub: str`),
  exception `AdminToolsTokenError`.

- [ ] **Step 1: Créer le paquet**

```bash
mkdir -p core/app/admin_tools
touch core/app/admin_tools/__init__.py
```

- [ ] **Step 2: Écrire les tests (échouent)**

Créer `core/tests/test_admin_tools_tokens.py` :

```python
# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest

from app.admin_tools.tokens import (
    AdminToolsTokenError,
    decode_launch_token,
    decode_session_token,
    mint_launch_token,
    mint_session_token,
)

_SECRET = "test-admin-tools-secret-padding-0123456"  # >=32 bytes, cf.
# test_export_tokens.py (InsecureKeyLengthWarning promue en erreur, filterwarnings)


@pytest.fixture(autouse=True)
def admin_tools_secret(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", _SECRET)


def test_launch_token_round_trip():
    token = mint_launch_token(sub="u1", tool="martin")
    claims = decode_launch_token(token)
    assert claims.sub == "u1"
    assert claims.tool == "martin"


def test_session_token_round_trip():
    token = mint_session_token(sub="u1")
    claims = decode_session_token(token)
    assert claims.sub == "u1"


def test_decode_launch_token_rejects_expired(monkeypatch):
    now = int(time.time())
    expired = jwt.encode(
        {"typ": "admin_launch", "sub": "u1", "tool": "martin", "iat": now - 120, "exp": now - 60},
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(expired)


def test_decode_launch_token_rejects_tampered_signature():
    token = mint_launch_token(sub="u1", tool="martin")
    with pytest.raises(AdminToolsTokenError):
        jwt.decode(token, "wrong-secret-padding-0123456789012", algorithms=["HS256"])
        # ligne ci-dessus lève PyJWTError directement (démonstration) ; le
        # vrai test de la fonction du module suit :
    import os

    os.environ["CORE_ADMIN_TOOLS_TOKEN_SECRET"] = "a-different-secret-padding-0123456"
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(token)
    os.environ["CORE_ADMIN_TOOLS_TOKEN_SECRET"] = _SECRET


def test_decode_launch_token_rejects_wrong_typ():
    session_like = mint_session_token(sub="u1")
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(session_like)


def test_decode_session_token_rejects_wrong_typ():
    launch_like = mint_launch_token(sub="u1", tool="martin")
    with pytest.raises(AdminToolsTokenError):
        decode_session_token(launch_like)


def test_decode_launch_token_rejects_missing_claim():
    bad = jwt.encode(
        {"typ": "admin_launch", "sub": "u1"},  # 'tool' manquant
        _SECRET,
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(bad)


def test_decode_raises_clean_error_when_secret_unset(monkeypatch):
    # Même régression que test_export_tokens.py::test_decode_raises_export_token_error_when_secret_unset :
    # un jeton forgé par un attaquant avec un secret arbitraire ne doit
    # jamais faire planter en KeyError brut quand CORE_ADMIN_TOOLS_TOKEN_SECRET
    # est absente (instance qui n'a jamais activé la capacité).
    monkeypatch.delenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", raising=False)
    forged = jwt.encode(
        {"typ": "admin_launch", "sub": "u1", "tool": "martin"},
        "attacker-controlled-secret-of-their-choosing",
        algorithm="HS256",
    )
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(forged)
```

- [ ] **Step 3: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_admin_tools_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.admin_tools.tokens'`

- [ ] **Step 4: Implémenter `tokens.py`**

Créer `core/app/admin_tools/tokens.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Jetons du gate /admin/* (outils d'infrastructure Martin/Titiler/
Grafana) : un jeton de lancement à usage unique (60s), qui bootstrap un
cookie de session (30 min) posé par app.admin_tools.routes — même patron
que app.auth.export_tokens (SP-17a). Pas de suivi « déjà consommé », comme
export_tokens : révocation par TTL seul (SP-17a, même choix assumé)."""

import os
import time

import jwt

_ALGORITHM = "HS256"
_LAUNCH_TYP = "admin_launch"
_SESSION_TYP = "admin_session"
_LAUNCH_TTL_SECONDS = 60
_SESSION_TTL_SECONDS = 1800


class AdminToolsTokenError(Exception):
    pass


class LaunchTokenClaims:
    def __init__(self, *, sub: str, tool: str) -> None:
        self.sub = sub
        self.tool = tool


class SessionTokenClaims:
    def __init__(self, *, sub: str) -> None:
        self.sub = sub


def _secret() -> str:
    return os.environ["CORE_ADMIN_TOOLS_TOKEN_SECRET"]


def mint_launch_token(*, sub: str, tool: str) -> str:
    now = int(time.time())
    claims = {
        "typ": _LAUNCH_TYP,
        "sub": sub,
        "tool": tool,
        "iat": now,
        "exp": now + _LAUNCH_TTL_SECONDS,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def decode_launch_token(token: str) -> LaunchTokenClaims:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except (jwt.PyJWTError, KeyError) as exc:
        raise AdminToolsTokenError(str(exc)) from exc
    if claims.get("typ") != _LAUNCH_TYP:
        raise AdminToolsTokenError("wrong token type")
    missing = [c for c in ("sub", "tool") if c not in claims]
    if missing:
        raise AdminToolsTokenError(f"missing claims: {missing}")
    return LaunchTokenClaims(sub=claims["sub"], tool=claims["tool"])


def mint_session_token(*, sub: str) -> str:
    now = int(time.time())
    claims = {
        "typ": _SESSION_TYP,
        "sub": sub,
        "iat": now,
        "exp": now + _SESSION_TTL_SECONDS,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def decode_session_token(token: str) -> SessionTokenClaims:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except (jwt.PyJWTError, KeyError) as exc:
        raise AdminToolsTokenError(str(exc)) from exc
    if claims.get("typ") != _SESSION_TYP:
        raise AdminToolsTokenError("wrong token type")
    if "sub" not in claims:
        raise AdminToolsTokenError("missing claims: ['sub']")
    return SessionTokenClaims(sub=claims["sub"])
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**

Run: `cd core && uv run pytest tests/test_admin_tools_tokens.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Nettoyer le test de signature falsifiée**

Le Step 2 contient un bloc de démonstration inutile dans
`test_decode_launch_token_rejects_tampered_signature` (le premier
`with pytest.raises` teste `jwt.decode` directement, pas le module). Le
retirer — ne garder que la vérification via `decode_launch_token` :

```python
def test_decode_launch_token_rejects_tampered_signature(monkeypatch):
    token = mint_launch_token(sub="u1", tool="martin")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", "a-different-secret-padding-0123456")
    with pytest.raises(AdminToolsTokenError):
        decode_launch_token(token)
```

(remplace la fonction équivalente du Step 2 ; supprime l'import `os` local
et le bloc de démonstration — utiliser le paramètre `monkeypatch` déjà
disponible comme dans les autres tests du fichier)

- [ ] **Step 7: Relancer les tests, vérifier qu'ils passent toujours**

Run: `cd core && uv run pytest tests/test_admin_tools_tokens.py -v`
Expected: PASS (9 passed)

- [ ] **Step 8: Commit**

```bash
git add core/app/admin_tools/ core/tests/test_admin_tools_tokens.py
git commit -m "feat(core): jetons de lancement/session du gate admin-tools"
```

---

## Task 3 : routes `launch`/`session`/`verify` + montage dans `main.py`

**Files:**
- Create: `core/app/admin_tools/routes.py`
- Modify: `core/app/main.py` (imports lignes 12, 16-25 ; montage après
  ligne 282)
- Test: `core/tests/test_admin_tools_routes.py`
- Modify (régénération, pas d'édition manuelle) : `core/openapi.json`,
  `shell/src/api/generated/core-schema.d.ts`

**Interfaces:**
- Consumes : `mint_launch_token`/`decode_launch_token`/
  `mint_session_token`/`decode_session_token`/`AdminToolsTokenError`
  (Tâche 2) ; `is_admin_tools_enabled` (Tâche 1) ; `get_current_user`,
  `User.is_admin`, `User.id` (existants, `app.auth.dependency`/
  `app.users.models`).
- Produces : `router: APIRouter` exposant `POST /admin-tools/launch/{tool}`,
  `GET /admin-tools/session/{tool}`, `GET /admin-tools/verify` — monté
  conditionnellement dans `app.main.create_app()`.

- [ ] **Step 1: Écrire les tests (échouent)**

Créer `core/tests/test_admin_tools_routes.py`. La fixture `env` charge
deux utilisateurs (admin et membre) hors de toute session de requête, puis
expose `use_as(user_id)` pour basculer `get_current_user` sur l'un ou
l'autre à la volée dans un même test — chaque appel recharge l'utilisateur
dans une session fraîche pour éviter un objet SQLAlchemy détaché entre deux
requêtes :

```python
# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest
from fastapi.testclient import TestClient

from app import db
from app.admin_tools.tokens import mint_launch_token, mint_session_token
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user

_SECRET = "test-admin-tools-secret-padding-0123456"


@pytest.fixture(autouse=True)
def admin_tools_env(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", _SECRET)
    monkeypatch.setenv("CORE_BASE_URL", "http://localhost:8200")


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    session_factory = make_session_factory(engine)
    with session_factory() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        member = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="m", username="member",
            email=None, first_name="", last_name="", bootstrap_admin=False,
        )
        s.commit()
        admin_id, member_id = admin.id, member.id

    app = create_app()

    def override_session():
        with request_scoped_session(session_factory) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session

    def use_as(user_id: str) -> None:
        def _dep():
            with request_scoped_session(session_factory) as session:
                return session.get(User, user_id)

        app.dependency_overrides[get_current_user] = _dep

    return TestClient(app), use_as, admin_id, member_id


def test_routes_absent_when_disabled(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "false")
    client = TestClient(create_app())
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 404


def test_launch_requires_admin(env):
    client, use_as, _admin_id, member_id = env
    use_as(member_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 403


def test_launch_rejects_unknown_tool(env):
    client, use_as, admin_id, _member_id = env
    use_as(admin_id)
    response = client.post("/admin-tools/launch/not-a-real-tool")
    assert response.status_code == 422


def test_launch_returns_session_url_for_admin(env):
    client, use_as, admin_id, _member_id = env
    use_as(admin_id)
    response = client.post("/admin-tools/launch/martin")
    assert response.status_code == 200
    url = response.json()["url"]
    assert url.startswith("http://localhost:8200/admin-tools/session/martin?_at=")


def test_session_redirects_and_sets_cookie_on_valid_token(env):
    client, _use_as, admin_id, _member_id = env
    token = mint_launch_token(sub=admin_id, tool="martin")
    response = client.get(
        f"/admin-tools/session/martin?_at={token}", follow_redirects=False
    )
    assert response.status_code == 302
    assert response.headers["location"] == "/admin/martin/"
    set_cookie = response.headers["set-cookie"]
    assert "gs_admin_session=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "Secure" in set_cookie
    assert "samesite=strict" in set_cookie.lower()
    assert "Path=/admin" in set_cookie


def test_session_rejects_expired_launch_token(env):
    client, _use_as, admin_id, _member_id = env
    now = int(time.time())
    expired = jwt.encode(
        {"typ": "admin_launch", "sub": admin_id, "tool": "martin", "iat": now - 120, "exp": now - 60},
        _SECRET,
        algorithm="HS256",
    )
    response = client.get(f"/admin-tools/session/martin?_at={expired}", follow_redirects=False)
    assert response.status_code == 401


def test_session_rejects_tool_mismatch(env):
    client, _use_as, admin_id, _member_id = env
    token = mint_launch_token(sub=admin_id, tool="martin")
    response = client.get(f"/admin-tools/session/titiler?_at={token}", follow_redirects=False)
    assert response.status_code == 401


def test_verify_accepts_valid_session_cookie(env):
    client, _use_as, admin_id, _member_id = env
    token = mint_session_token(sub=admin_id)
    response = client.get("/admin-tools/verify", cookies={"gs_admin_session": token})
    assert response.status_code == 200


def test_verify_rejects_missing_cookie(env):
    client, _use_as, _admin_id, _member_id = env
    response = client.get("/admin-tools/verify")
    assert response.status_code == 403


def test_verify_rejects_expired_session_cookie(env):
    client, _use_as, admin_id, _member_id = env
    now = int(time.time())
    expired = jwt.encode(
        {"typ": "admin_session", "sub": admin_id, "iat": now - 2000, "exp": now - 1},
        _SECRET,
        algorithm="HS256",
    )
    response = client.get("/admin-tools/verify", cookies={"gs_admin_session": expired})
    assert response.status_code == 403
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd core && uv run pytest tests/test_admin_tools_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.admin_tools.routes'`

- [ ] **Step 3: Implémenter `routes.py`**

Créer `core/app/admin_tools/routes.py` :

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes du gate /admin/* — montées uniquement quand
CORE_ADMIN_TOOLS_ENABLED est actif (app.main, même patron que
app.tileset3d/app.export). Trois endpoints : lancement (Bearer, appelé par
le shell), bootstrap de session (jeton à usage unique -> cookie, atteint
par navigation directe du navigateur depuis l'URL renvoyée par le
lancement), et vérification (appelée par le forwardAuth de Traefik,
jamais par le shell — cf. plan d'implémentation, Tâche 4)."""

import os
from typing import Literal

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response
from fastapi.responses import RedirectResponse

from app.admin_tools.tokens import (
    AdminToolsTokenError,
    decode_launch_token,
    decode_session_token,
    mint_launch_token,
    mint_session_token,
)
from app.auth.dependency import get_current_user
from app.users.models import User

router = APIRouter()

ToolName = Literal["martin", "titiler", "grafana"]
_SESSION_COOKIE = "gs_admin_session"
_SESSION_MAX_AGE_SECONDS = 1800


def _require_admin(user: User) -> None:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="admin role required")


@router.post("/admin-tools/launch/{tool}")
def launch_admin_tool(tool: ToolName, user: User = Depends(get_current_user)) -> dict:
    _require_admin(user)
    base = os.environ.get("CORE_BASE_URL", "http://localhost:8200")
    token = mint_launch_token(sub=user.id, tool=tool)
    return {"url": f"{base}/admin-tools/session/{tool}?_at={token}"}


@router.get("/admin-tools/session/{tool}")
def bootstrap_admin_tool_session(tool: ToolName, _at: str) -> Response:
    try:
        claims = decode_launch_token(_at)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=401, detail="invalid launch token") from exc
    if claims.tool != tool:
        raise HTTPException(status_code=401, detail="invalid launch token")
    session_token = mint_session_token(sub=claims.sub)
    response = RedirectResponse(url=f"/admin/{tool}/", status_code=302)
    response.set_cookie(
        key=_SESSION_COOKIE,
        value=session_token,
        max_age=_SESSION_MAX_AGE_SECONDS,
        httponly=True,
        secure=True,
        samesite="strict",
        path="/admin",
    )
    return response


@router.get("/admin-tools/verify")
def verify_admin_tool_session(gs_admin_session: str | None = Cookie(default=None)) -> Response:
    if gs_admin_session is None:
        raise HTTPException(status_code=403, detail="no admin session")
    try:
        decode_session_token(gs_admin_session)
    except AdminToolsTokenError as exc:
        raise HTTPException(status_code=403, detail="invalid admin session") from exc
    return Response(status_code=200)
```

- [ ] **Step 4: Monter le routeur dans `main.py`**
`core/app/main.py`, ligne 12 — ajouter l'import du module (ordre
alphabétique, `admin_tools` avant `alerts`) :

```python
from app import db, observability
from app.admin_tools import routes as admin_tools_routes
from app.alerts import routes as alerts_routes
```

Lignes 16-25 — ajouter `is_admin_tools_enabled` à l'import existant (ordre
alphabétique, avant `is_appexport_enabled`) :

```python
from app.auth.dependency import (
    is_admin_tools_enabled,
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

Après le bloc existant (juste après `if is_copilot_enabled(): …`, qui suit
`if is_terrain3d_enabled(): …`) :

```python
    if is_copilot_enabled():
        app.include_router(copilot_routes.router)
    if is_admin_tools_enabled():
        app.include_router(admin_tools_routes.router)
```

- [ ] **Step 5: Lancer les tests, vérifier qu'ils passent**
Run: `cd core && uv run pytest tests/test_admin_tools_routes.py -v`
Expected: PASS (9 passed)

- [ ] **Step 6: Suite complète du cœur (non-régression)**
Run: `cd core && uv run pytest -q`
Expected: aucune régression

- [ ] **Step 7: Régénérer la spec OpenAPI et les types TS**
Run:
```bash
cd core && PYTHONPATH=. \
  CORE_SECRETS_MASTER_KEY="AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8=" \
  uv run python scripts/export_openapi.py openapi.json
cd ../shell && npm run gen:api-types
```

Expected: diff sur `core/openapi.json` (trois nouvelles routes) et sur
`shell/src/api/generated/core-schema.d.ts` (types correspondants). Un diff
vide serait suspect ici — contrairement au cas d'une route derrière un flag
éteint en CI, ces trois routes sont bien montées (le flag par défaut
`false` change seulement s'ils répondent 404 à l'exécution, pas s'ils
existent dans le schéma généré à partir du code Python, qui les déclare
inconditionnellement).

- [ ] **Step 8: Portes de qualité**
Run:
```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run lint-imports
```
Expected: aucune erreur.

- [ ] **Step 9: Commit**
```bash
git add core/app/admin_tools/routes.py core/app/main.py \
  core/tests/test_admin_tools_routes.py core/openapi.json \
  shell/src/api/generated/core-schema.d.ts
git commit -m "feat(core): routes launch/session/verify du gate admin-tools"
```

---

## Task 4 : câblage compose (base) — env vars, sous-chemins, labels Traefik

**Files:**
- Modify: `docker-compose.yml` (services `core`, `martin`, `titiler`,
  `otel-lgtm`)
- Modify: `.env.example`

**Interfaces:**
- Consumes : rien côté code (uniquement infra) ; les noms de variable
  `CORE_ADMIN_TOOLS_ENABLED`/`CORE_ADMIN_TOOLS_TOKEN_SECRET` doivent
  correspondre exactement à ceux lus par `core/app/auth/dependency.py`
  (Tâche 1) et `core/app/admin_tools/tokens.py` (Tâche 2).
- Produces : trois routeurs Traefik (`martin`, `titiler`, `grafana`) et un
  middleware `admin-auth` partagé, consommés par la Tâche 5 (overlay prod).

- [ ] **Step 1: Ajouter les deux variables sur `core`**

`docker-compose.yml`, dans le bloc `environment:` du service `core`,
immédiatement après la ligne `CORE_EXPORT_TOKEN_SECRET: ${CORE_EXPORT_TOKEN_SECRET:-}` :

```yaml
      CORE_EXPORT_TOKEN_SECRET: ${CORE_EXPORT_TOKEN_SECRET:-}
      # Gate /admin/* (Martin/Titiler/Grafana) — même convention que les
      # deux lignes ci-dessus : ENABLED contrôle le montage des trois
      # routes, TOKEN_SECRET signe le jeton de lancement (60s) et le
      # cookie de session (30 min) qu'il bootstrap.
      CORE_ADMIN_TOOLS_ENABLED: ${CORE_ADMIN_TOOLS_ENABLED:-false}
      CORE_ADMIN_TOOLS_TOKEN_SECRET: ${CORE_ADMIN_TOOLS_TOKEN_SECRET:-}
      CORE_TILESET3D_ENABLED: ${CORE_TILESET3D_ENABLED:-false}
```

- [ ] **Step 2: Martin — `--base-path`, environnement, labels**

Remplacer le bloc `martin:` (actuel : `image`, `environment`, `volumes`,
`command: --config /config.yaml`, `ports`, `networks`, `depends_on`,
`healthcheck`) en ajoutant `--base-path` à `command:` et un bloc `labels:`
à la fin du service :

```yaml
  martin:
    image: ghcr.io/maplibre/martin:v0.18.0
    environment:
      DATABASE_URL: postgresql://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    volumes:
      - ./martin-config.yaml:/config.yaml
    # --base-path (confirmé contre l'image réelle, v0.18.0 : "Set TileJSON
    # URL path prefix") : Martin réécrit les URLs de tuiles de son propre
    # TileJSON avec ce préfixe — cohérent avec le stripprefix Traefik du
    # label admin-auth ci-dessous (Traefik retire /admin/martin avant de
    # transmettre ; Martin le réintroduit lui-même dans ses réponses).
    command: --config /config.yaml --base-path /admin/martin
    ports:
      - "3010:3000"
    networks: [gis-net]
    depends_on:
      pgbouncer:
        condition: service_started
    healthcheck:
      test: ["CMD", "wget", "--spider", "-q", "http://127.0.0.1:3000/health"]
      interval: 30s
      timeout: 5s
      retries: 3
    labels:
      - traefik.enable=true
      - traefik.http.routers.martin.rule=Host(`${DOMAIN}`) && PathPrefix(`/admin/martin`)
      - traefik.http.routers.martin.entrypoints=websecure
      - traefik.http.routers.martin.tls.certresolver=letsencrypt
      - traefik.http.routers.martin.priority=15
      - traefik.http.routers.martin.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker,strip-admin-martin@docker
      - traefik.http.middlewares.strip-admin-martin.stripprefix.prefixes=/admin/martin
      - traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/admin-tools/verify
      - traefik.http.services.martin.loadbalancer.server.port=3000
```

(Les commentaires existants sur le choix du port hôte 3010 et la sonde
`127.0.0.1` restent inchangés — ne pas les retirer, seuls `command:` et
`labels:` changent.)

- [ ] **Step 3: Titiler — `TITILER_API_ROOT_PATH`, labels**

Dans le bloc `environment:` du service `titiler`, ajouter (après
`AWS_VIRTUAL_HOSTING: "FALSE"`, avant le commentaire sur `PORT`) :

```yaml
      AWS_VIRTUAL_HOSTING: "FALSE"
      # Confirmé dans le code de l'image (titiler.application.main :
      # FastAPI(root_path=api_settings.root_path), pydantic-settings
      # env_prefix="TITILER_API_") : Titiler réécrit les URLs de tuiles de
      # ses réponses avec ce préfixe — même rôle que --base-path pour
      # Martin ci-dessus, cohérent avec le stripprefix Traefik du label
      # admin-auth plus bas (Traefik retire /admin/titiler avant de
      # transmettre).
      TITILER_API_ROOT_PATH: /admin/titiler
```

Et à la fin du service `titiler` (après le bloc `healthcheck:` existant) :

```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.titiler.rule=Host(`${DOMAIN}`) && PathPrefix(`/admin/titiler`)
      - traefik.http.routers.titiler.entrypoints=websecure
      - traefik.http.routers.titiler.tls.certresolver=letsencrypt
      - traefik.http.routers.titiler.priority=15
      - traefik.http.routers.titiler.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker,strip-admin-titiler@docker
      - traefik.http.middlewares.strip-admin-titiler.stripprefix.prefixes=/admin/titiler
      - traefik.http.services.titiler.loadbalancer.server.port=8000
```

- [ ] **Step 4: Grafana (`otel-lgtm`) — `GF_SERVER_*`, labels SANS stripprefix**

Dans le bloc `environment:` du service `otel-lgtm`, ajouter (après
`GRAFANA_ALERT_WEBHOOK_URL: ...`) :

```yaml
      GRAFANA_ALERT_WEBHOOK_URL: ${GRAFANA_ALERT_WEBHOOK_URL:-http://127.0.0.1:1/grafana-alert-webhook-not-configured}
      # Rejoué en conteneur réel (grafana/otel-lgtm:0.11.4) pendant l'écriture
      # de ce plan : avec SERVE_FROM_SUB_PATH=true, Grafana attend le
      # préfixe CONSERVÉ par le proxy (contrairement à Martin/Titiler
      # ci-dessus) — /login sans préfixe répond 301, /admin/grafana/login
      # répond 200. Ne PAS ajouter de stripprefix pour ce service.
      GF_SERVER_ROOT_URL: https://${DOMAIN}/admin/grafana/
      GF_SERVER_SERVE_FROM_SUB_PATH: "true"
```

Et à la fin du service `otel-lgtm` (après le bloc `networks: [gis-net]`
existant) :

```yaml
    labels:
      - traefik.enable=true
      - traefik.http.routers.grafana.rule=Host(`${DOMAIN}`) && PathPrefix(`/admin/grafana`)
      - traefik.http.routers.grafana.entrypoints=websecure
      - traefik.http.routers.grafana.tls.certresolver=letsencrypt
      - traefik.http.routers.grafana.priority=15
      - traefik.http.routers.grafana.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker
      - traefik.http.services.grafana.loadbalancer.server.port=3000
```

- [ ] **Step 5: `.env.example`**

Ajouter, juste après le bloc `CORE_EXPORT_TOKEN_SECRET` (autour de la
ligne 171, avant `SHELL_BASE_URL`) :

```
# ─── Cœur : gate /admin/* (Martin/Titiler/Grafana, outils d'infrastructure) ─
# "false" (défaut) ne monte pas les trois routes /admin-tools/* ; les
# boutons correspondants disparaissent aussi du panneau Administration du
# shell (capacité adminToolsEnabled, GET /instance et GET /me).
CORE_ADMIN_TOOLS_ENABLED=false
# Secret HMAC signant le jeton de lancement (60s) et le cookie de session
# (30 min) du gate /admin/*. Même format que CORE_EXPORT_TOKEN_SECRET,
# requis seulement si CORE_ADMIN_TOOLS_ENABLED=true. Générer avec :
# openssl rand -base64 32
CORE_ADMIN_TOOLS_TOKEN_SECRET=
```

- [ ] **Step 6: Vérifier `docker compose config`**

Run: `docker compose config --quiet && echo OK`
Expected: `OK` (pas d'erreur de syntaxe YAML/Traefik)

Run: `docker compose config | grep -A3 "routers.grafana.rule\|routers.martin.rule\|routers.titiler.rule"`
Expected : les trois règles `Host(...) && PathPrefix(...)` apparaissent
résolues (variable `${DOMAIN}` substituée si un `.env` est présent, ou
laissée telle quelle sinon — pas d'erreur dans les deux cas).

- [ ] **Step 7: Portes de qualité du dépôt sur les fichiers déployabilité**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS — en particulier
`test_every_core_env_var_is_wired_to_a_service` (les deux nouvelles
variables sont maintenant dans l'`environment:` de `core`) et
`test_every_compose_substitution_is_documented` (les deux apparaissent
dans `.env.example`).

- [ ] **Step 8: Commit**

```bash
git add docker-compose.yml .env.example
git commit -m "feat(deploy): routes Traefik /admin/martin, /admin/titiler, /admin/grafana"
```

---

## Task 5 : câblage compose (overlay prod) — labels sans ACME

**Files:**
- Modify: `docker-compose.prod.yml`

**Interfaces:**
- Consumes : les mêmes noms de routeur/service/middleware que la Tâche 4
  (`martin`, `titiler`, `grafana`, `admin-auth`) — cette tâche ne fait que
  substituer leurs attributs `entrypoints`/`tls`, jamais leurs noms.

- [ ] **Step 1: Ajouter `labels: !override` sur `martin`**

Dans `docker-compose.prod.yml`, service `martin` (actuellement `restart:`,
`ports: !reset []`, et un commentaire) — ajouter après le commentaire
existant :

```yaml
  martin:
    restart: unless-stopped
    ports: !reset []
    # Plus de route publique depuis SP-24 : Martin se connecte en propriétaire
    # des tables (donc hors RLS) et n'a aucune notion de collection ni de
    # can(). Les tuiles vectorielles d'une collection passent désormais par
    # GET /collections/{id}/tiles/{z}/{x}/{y}.mvt, servi par le cœur. Le
    # service reste joignable sur le réseau interne.
    #
    # /admin/martin (ce plan) reste une exception délibérée : connexion
    # directe d'un outil desktop (QGIS) par un admin authentifié, en toute
    # connaissance du bypass RLS — pas une réouverture de la route
    # applicative retirée par SP-24.
    labels:
      - traefik.enable=true
      - traefik.http.routers.martin.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/admin/martin`)
      - traefik.http.routers.martin.entrypoints=web
      - traefik.http.routers.martin.priority=15
      - traefik.http.routers.martin.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker,strip-admin-martin@docker
      - traefik.http.middlewares.strip-admin-martin.stripprefix.prefixes=/admin/martin
      - traefik.http.middlewares.admin-auth.forwardauth.address=http://core:8200/admin-tools/verify
      - traefik.http.services.martin.loadbalancer.server.port=3000
```

- [ ] **Step 2: Ajouter `labels: !override` sur `titiler`**

Service `titiler` (actuellement `restart:`, `ports: !reset []`) :

```yaml
  titiler:
    restart: unless-stopped
    ports: !reset []
    labels:
      - traefik.enable=true
      - traefik.http.routers.titiler.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/admin/titiler`)
      - traefik.http.routers.titiler.entrypoints=web
      - traefik.http.routers.titiler.priority=15
      - traefik.http.routers.titiler.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker,strip-admin-titiler@docker
      - traefik.http.middlewares.strip-admin-titiler.stripprefix.prefixes=/admin/titiler
      - traefik.http.services.titiler.loadbalancer.server.port=8000
```

- [ ] **Step 3: Ajouter le service `otel-lgtm` (absent de l'overlay jusqu'ici) avec ses labels**

`docker-compose.prod.yml` ne mentionne actuellement `otel-lgtm` nulle
part — le profil `observability` du fichier de base s'applique tel quel en
prod, sans override. Ajouter un nouveau bloc de service (à la suite de
`keycloak`, avant `core`, ou à tout autre endroit cohérent avec l'ordre du
fichier — l'ordre des services dans un fichier compose n'a pas d'effet
fonctionnel) :

```yaml
  otel-lgtm:
    environment:
      GF_SERVER_ROOT_URL: https://${GEOSTUDIO_PUBLIC_HOST}/admin/grafana/
    labels:
      - traefik.enable=true
      - traefik.http.routers.grafana.rule=Host(`${GEOSTUDIO_PUBLIC_HOST}`) && PathPrefix(`/admin/grafana`)
      - traefik.http.routers.grafana.entrypoints=web
      - traefik.http.routers.grafana.priority=15
      - traefik.http.routers.grafana.middlewares=admin-auth@docker,security-headers@docker,rate-limit@docker
      - traefik.http.services.grafana.loadbalancer.server.port=3000
```

Ceci **fusionne** avec le service `otel-lgtm` du fichier de base
(`environment:`/`labels:` s'additionnent aux clés existantes — pas de
`!reset`/`!override` nécessaire ici puisque le fichier de base n'a ni
`labels:` ni cette variable précise sur ce service, donc pas de conflit à
trancher).

- [ ] **Step 4: Vérifier la config résolue**

Run:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config --quiet && echo OK
```
Expected: `OK`

Run:
```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml config \
  | grep -A2 "routers.martin.entrypoints\|routers.titiler.entrypoints\|routers.grafana.entrypoints"
```
Expected: les trois valent `web` (pas `websecure`), confirmant que
l'`!override` du fichier de base a bien été appliqué — un `websecure`
résiduel signifierait que la fusion Compose a laissé les labels du fichier
de base survivre à côté (piège déjà documenté pour `build:` dans l'en-tête
de ce fichier).

- [ ] **Step 5: Commit**

```bash
git add docker-compose.prod.yml
git commit -m "feat(deploy): overlay prod pour /admin/martin, /admin/titiler, /admin/grafana"
```

---

## Task 6 : `ItemClient.launchAdminTool` + hook shell

**Files:**
- Modify: `shell/src/api/types.ts` (ajout `adminToolsEnabled` à
  `InstanceInfo`, ligne 53-61 ; ajout de la méthode à l'interface
  `ItemClient`, après `deleteHarvestSource`/`runHarvestSource`, cf. ligne
  293-294)
- Modify: `shell/src/api/itemClient.ts` (implémentation, après
  `setExtensionEnabled`, ligne 742-744)
- Modify: `shell/src/api/hooks.ts` (nouveau hook, après
  `useSetExtensionEnabled`, ligne 450)
- Test: `shell/src/api/itemClient.test.ts` (nouveau test, patron de
  `listAllExtensions requests all=true...`, ligne ~2211)

**Interfaces:**
- Produces : `ItemClient.launchAdminTool(tool: "martin" | "titiler" |
  "grafana"): Promise<{ url: string }>` ; hook
  `useLaunchAdminTool(): UseMutationResult<{ url: string }, Error,
  "martin" | "titiler" | "grafana">` — consommés par la Tâche 7.

- [ ] **Step 1: Écrire le test de l'implémentation `ItemClient` (échoue)**

Dans `shell/src/api/itemClient.test.ts`, ajouter (à la suite des tests
existants sur les extensions) :

```ts
test("launchAdminTool POSTs to /admin-tools/launch/{tool} and returns the url", async () => {
  server.use(
    http.post("https://core.test/admin-tools/launch/martin", () =>
      HttpResponse.json({ url: "https://core.test/admin-tools/session/martin?_at=abc" }),
    ),
  );
  const result = await makeClient().launchAdminTool("martin");
  expect(result.url).toBe("https://core.test/admin-tools/session/martin?_at=abc");
});
```

(Vérifier au préalable la signature exacte de `makeClient()` déjà définie
plus haut dans ce fichier — même fonction que celle utilisée par
`listAllExtensions requests all=true...`, ligne ~2234 : `makeClient().listAllExtensions()`.)

- [ ] **Step 2: Lancer le test, vérifier qu'il échoue**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t launchAdminTool`
Expected: FAIL — `TypeError: makeClient(...).launchAdminTool is not a function`

- [ ] **Step 3: Ajouter le type et la méthode à l'interface**

`shell/src/api/types.ts`, ligne 53-61 — ajouter le champ à `InstanceInfo` :

```ts
export type InstanceInfo = {
  readOnly: boolean;
  etlEnabled: boolean;
  exportEnabled: boolean;
  appExportEnabled: boolean;
  tileset3dEnabled: boolean;
  terrain3dEnabled: boolean;
  copilotEnabled: boolean;
  adminToolsEnabled: boolean;
};

export type AdminToolName = "martin" | "titiler" | "grafana";
```

Puis, dans l'interface `ItemClient` (après `runHarvestSource(id: string):
Promise<void>;`, ligne 294) :

```ts
  runHarvestSource(id: string): Promise<void>;
  launchAdminTool(tool: AdminToolName): Promise<{ url: string }>;
```

- [ ] **Step 4: Implémenter dans `CoreItemClient`**

`shell/src/api/itemClient.ts`, après `setExtensionEnabled` (ligne 742-744) :

```ts
    async setExtensionEnabled(id: string, enabled: boolean): Promise<void> {
      await request<void>("PATCH", `/extensions/${id}`, { enabled });
    },

    async launchAdminTool(tool: AdminToolName): Promise<{ url: string }> {
      return request<{ url: string }>("POST", `/admin-tools/launch/${tool}`);
    },
```

Ajouter `AdminToolName` à l'import de types en tête du fichier (même ligne
d'import que `AdminExtension`, `CollectionAdmin`, etc.).

- [ ] **Step 5: Lancer le test, vérifier qu'il passe**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t launchAdminTool`
Expected: PASS

- [ ] **Step 6: Ajouter le hook**

`shell/src/api/hooks.ts`, après `useSetExtensionEnabled` (ligne 450) :

```ts
export function useLaunchAdminTool() {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: (tool: AdminToolName) => client.launchAdminTool(tool),
  });
}
```

Ajouter `AdminToolName` à l'import de types en tête de `hooks.ts` (même
ligne que les autres types importés depuis `./types`).

- [ ] **Step 7: Suite de tests complète du fichier `itemClient.test.ts`**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (aucune régression)

- [ ] **Step 8: Vérification de types**

Run: `cd shell && npm run build`
Expected: `tsc --noEmit` passe sans erreur.

- [ ] **Step 9: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts \
  shell/src/api/hooks.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient.launchAdminTool + useLaunchAdminTool"
```

---

## Task 7 : page `AdminInfrastructurePage` + route + découvrabilité

**Files:**
- Create: `shell/src/pages/AdminInfrastructurePage.tsx`
- Create: `shell/src/pages/AdminInfrastructurePage.test.tsx`
- Modify: `shell/src/shell/routes.tsx` (import + route, après le bloc
  `/admin/harvest`, lignes 291-298)
- Modify: `shell/src/pages/AdminExtensionsPage.tsx` (lien de découverte
  dans le panneau `browse`, lignes 19-25)

**Interfaces:**
- Consumes : `useInstanceInfo` (existant, `../api/hooks`),
  `useLaunchAdminTool` (Tâche 6), `RequireRole` (existant,
  `../auth/RequireRole`), `Panel`/`Button` (existants, `../ui/kit/*`),
  `TriptychLayout` (existant, `../shell/chrome/TriptychLayout`).

- [ ] **Step 1: Écrire les tests (échouent)**

Créer `shell/src/pages/AdminInfrastructurePage.test.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AdminInfrastructurePage } from "./AdminInfrastructurePage";

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => stubMatchMedia(false));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminInfrastructurePage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("affiche les trois boutons protégés et le lien MinIO quand la capacité est active", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Martin" });
  expect(screen.getByRole("button", { name: "Titiler" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Grafana" })).toBeInTheDocument();
  const minioLink = screen.getByRole("link", { name: /MinIO/ });
  expect(minioLink).toHaveAttribute("href", expect.stringContaining(":9001"));
});

test("masque les trois boutons protégés quand la capacité est désactivée, garde le lien MinIO", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ adminToolsEnabled: false })),
  );
  render(<Harness />);
  await screen.findByRole("link", { name: /MinIO/ });
  expect(screen.queryByRole("button", { name: "Martin" })).not.toBeInTheDocument();
});

test("cliquer sur Martin appelle launch et ouvre l'URL retournée dans un nouvel onglet", async () => {
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    http.post("https://core.test/admin-tools/launch/martin", () =>
      HttpResponse.json({ url: "https://core.test/admin-tools/session/martin?_at=abc" }),
    ),
  );
  render(<Harness />);
  const button = await screen.findByRole("button", { name: "Martin" });
  await userEvent.click(button);
  await waitFor(() =>
    expect(openSpy).toHaveBeenCalledWith(
      "https://core.test/admin-tools/session/martin?_at=abc",
      "_blank",
      "noopener",
    ),
  );
});
```

- [ ] **Step 2: Lancer les tests, vérifier qu'ils échouent**

Run: `cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx`
Expected: FAIL — le module `./AdminInfrastructurePage` n'existe pas

- [ ] **Step 3: Implémenter la page**

Créer `shell/src/pages/AdminInfrastructurePage.tsx` :

```tsx
// SPDX-License-Identifier: Apache-2.0
import { Link } from "react-router-dom";
import type { AdminToolName } from "../api/types";
import { useInstanceInfo, useLaunchAdminTool } from "../api/hooks";
import { Button } from "../ui/kit/Button";
import { Panel } from "../ui/kit/Panel";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

const PROTECTED_TOOLS: { tool: AdminToolName; label: string }[] = [
  { tool: "martin", label: "Martin" },
  { tool: "titiler", label: "Titiler" },
  { tool: "grafana", label: "Grafana" },
];

function minioUrl(): string {
  return `${window.location.protocol}//${window.location.hostname}:9001`;
}

export function AdminInfrastructurePage() {
  const instanceQuery = useInstanceInfo();
  const launch = useLaunchAdminTool();
  const adminToolsEnabled = instanceQuery.data?.adminToolsEnabled === true;

  return (
    <div className="-m-6 flex flex-1 flex-col overflow-hidden">
      <TriptychLayout
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
            </Panel>
          ),
        }}
        work={{
          id: "infrastructure",
          label: "Infrastructure",
          content: (
            <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
              <h1 className="text-lg font-bold text-ink">Outils d'infrastructure</h1>
              {!adminToolsEnabled && (
                <p className="text-sm text-ink-2">
                  Non activé sur cette instance (CORE_ADMIN_TOOLS_ENABLED).
                </p>
              )}
              {adminToolsEnabled && (
                <div className="flex flex-wrap gap-2">
                  {PROTECTED_TOOLS.map(({ tool, label }) => (
                    <Button
                      key={tool}
                      variant="outline"
                      disabled={launch.isPending}
                      onClick={async () => {
                        const { url } = await launch.mutateAsync(tool);
                        window.open(url, "_blank", "noopener");
                      }}
                    >
                      {label}
                    </Button>
                  ))}
                </div>
              )}
              <p className="text-sm text-ink-2">
                <a href={minioUrl()} target="_blank" rel="noopener noreferrer" className="text-accent hover:underline">
                  Console MinIO
                </a>{" "}
                — accès direct, non protégé par ce garde-fou ; fonctionne
                seulement si le port 9001 est exposé sur cet hôte.
              </p>
              {launch.isError && (
                <p role="alert" className="text-sm text-danger">
                  Échec de l'ouverture de l'outil.
                </p>
              )}
            </div>
          ),
        }}
        inspect={{ id: "detail", label: "Détail", content: null }}
      />
    </div>
  );
}
```

- [ ] **Step 4: Lancer les tests, vérifier qu'ils passent**

Run: `cd shell && npx vitest run src/pages/AdminInfrastructurePage.test.tsx`
Expected: PASS (3 passed)

- [ ] **Step 5: Enregistrer la route**

`shell/src/shell/routes.tsx` — ajouter l'import (à côté de
`AdminExtensionsPage`, ligne 17) :

```tsx
import { AdminExtensionsPage } from "../pages/AdminExtensionsPage";
import { AdminInfrastructurePage } from "../pages/AdminInfrastructurePage";
```

Et la route, après le bloc `/admin/harvest` (ligne 291-298) :

```tsx
        <Route
          path="/admin/harvest"
          element={
            <RequireRole role="admin" deniedMessage="Accès réservé aux administrateurs.">
              <HarvestSourcesAdminPage />
            </RequireRole>
          }
        />
        <Route
          path="/admin/infrastructure"
          element={
            <RequireRole role="admin" deniedMessage="Accès réservé aux administrateurs.">
              <AdminInfrastructurePage />
            </RequireRole>
          }
        />
```

- [ ] **Step 6: Lien de découverte depuis `AdminExtensionsPage`**

`shell/src/pages/AdminExtensionsPage.tsx`, dans le panneau `browse`
(lignes 19-25), ajouter un second lien après « Retour au catalogue » :

```tsx
        browse={{
          id: "back",
          label: "Catalogue",
          content: (
            <Panel className="m-3 flex flex-col gap-3 text-sm">
              <Link to="/" className="text-accent hover:underline">
                ← Retour au catalogue
              </Link>
              <Link to="/admin/infrastructure" className="text-accent hover:underline">
                Outils d'infrastructure →
              </Link>
            </Panel>
          ),
        }}
```

- [ ] **Step 7: Test de non-régression sur `AdminExtensionsPage`**

Run: `cd shell && npx vitest run src/pages/AdminExtensionsPage.test.tsx`
Expected: PASS (aucune régression — le nouveau lien n'entre en conflit
avec aucune assertion existante, qui cible des rôles `checkbox`/`alert`/
`tab`, pas `link`)

- [ ] **Step 8: Suite Vitest complète**

Run: `cd shell && npm run test`
Expected: PASS, pas de régression sur le comptage de référence (`CLAUDE.md`)

- [ ] **Step 9: Portes de qualité shell**

Run:
```bash
cd shell
npm run lint && npm run format:check
npm run build
```
Expected: aucune erreur.

- [ ] **Step 10: Commit**

```bash
git add shell/src/pages/AdminInfrastructurePage.tsx \
  shell/src/pages/AdminInfrastructurePage.test.tsx \
  shell/src/shell/routes.tsx shell/src/pages/AdminExtensionsPage.tsx
git commit -m "feat(shell): page Administration > Infrastructure (Martin/Titiler/Grafana/MinIO)"
```

---

## Task 8 : vérification finale — suites complètes + smoke test réel

**Files:** aucun fichier de code — vérification uniquement.

- [ ] **Step 1: Suite complète du cœur**

Run: `cd core && uv run pytest -q`
Expected: pas de régression par rapport au comptage de référence
(`CLAUDE.md`, section Commandes) ; les deux échecs préexistants documentés
restent les deux SEULS échecs possibles.

- [ ] **Step 2: Portes de qualité du cœur**

Run:
```bash
cd core
uv run ruff check . && uv run ruff format --check .
uv run mypy --strict app/auth app/secrets app/analytics app/copilot
uv run lint-imports
uv run python scripts/check_coverage.py coverage.xml .coverage-threshold
```
Expected: tout passe ; couverture non régressive (seuil 85).

- [ ] **Step 3: Suite complète du shell (Vitest + E2E)**

Run:
```bash
cd shell
rm -rf dist dist-export  # avant mesure de couverture (piège documenté)
npm run test
npm run e2e
```
Expected: pas de régression par rapport au comptage de référence ; E2E
118 passed / 4 skipped / 0 failed inchangé (aucun nouveau spec E2E dans ce
plan, cf. spec §7).

- [ ] **Step 4: `test_deployability.py` (déjà couvert Tâche 4, relancé ici en contexte complet)**

Run: `cd core && uv run pytest tests/test_deployability.py -v`
Expected: PASS intégral.

- [ ] **Step 5: pre-commit complet**

Run: `uvx pre-commit run --all-files`
Expected: 5/5 hooks passent.

- [ ] **Step 6: Smoke test réel — stack levée, gate testé au niveau HTTP**

Préparer un `.env` local avec `CORE_ADMIN_TOOLS_ENABLED=true`,
`CORE_ADMIN_TOOLS_TOKEN_SECRET=$(openssl rand -base64 32)`, et
`DOMAIN=admin.localhost` (n'importe quel nom résolvable en 127.0.0.1 —
`*.localhost` l'est nativement sur la plupart des systèmes, sans entrée
`/etc/hosts`).

```bash
docker compose up -d --build core martin titiler otel-lgtm traefik pgbouncer postgis
```

Attendre que `core` soit `healthy` (`docker compose ps`), puis :

```bash
# 1. Sans cookie : le forwardAuth doit refuser (403), donc la requête
#    n'atteint jamais Martin.
curl -sk --resolve admin.localhost:443:127.0.0.1 \
  https://admin.localhost/admin/martin/ -o /dev/null -w "%{http_code}\n"
# Expected: 403 (ou 401 selon la version de Traefik qui relaie le code de
# l'auth server — dans tous les cas PAS 200)

# 2. Lancement direct de l'API (simulateur du shell, sans jeton Bearer
#    réel puisqu'on est en mode mock) :
curl -sk --resolve admin.localhost:443:127.0.0.1 \
  -X POST -H "Authorization: Bearer mock" \
  https://admin.localhost/api/admin-tools/launch/martin
# Expected: {"url":"https://admin.localhost/api/admin-tools/session/martin?_at=..."}
# (CORE_BASE_URL doit être réglé sur https://admin.localhost/api dans le
# .env pour que cette valeur soit correcte — sinon elle reflète le défaut
# localhost:8200, à corriger dans le .env de test avant ce step)

# 3. Suivre le jeton — doit rediriger et poser le cookie :
curl -sk --resolve admin.localhost:443:127.0.0.1 -D - -o /dev/null \
  "https://admin.localhost/api/admin-tools/session/martin?_at=<TOKEN_DU_STEP_2>"
# Expected: "location: /admin/martin/" et un en-tête
# "set-cookie: gs_admin_session=...; HttpOnly; Secure; SameSite=Strict; Path=/admin"

# 4. Avec le cookie posé à l'étape 3, la route doit maintenant répondre :
curl -sk --resolve admin.localhost:443:127.0.0.1 \
  --cookie "gs_admin_session=<VALEUR_DU_STEP_3>" \
  https://admin.localhost/admin/martin/ -o /dev/null -w "%{http_code}\n"
# Expected: 200 (ou toute réponse Martin normale — pas 401/403)
```

Si l'étape 4 échoue en 403/401 : vérifier d'abord que
`forwardauth.trustForwardHeader`/la transmission du cookie se comporte
comme documenté (spec §5, dernier point non rejoué empiriquement dans
cette session) — piste : ajouter `trustForwardHeader=true` explicitement
sur le label `admin-auth` si le comportement par défaut de Traefik
`v3.0.4` s'avère différent de l'hypothèse de conception.

- [ ] **Step 7: Vérification visuelle des trois outils (Titiler, Grafana en plus de Martin)**

Dans un navigateur configuré pour ignorer l'avertissement de certificat
(auto-signé, ACME ne peut pas émettre pour `admin.localhost`) :
1. Se connecter au shell en admin (`https://admin.localhost/`, mode mock).
2. Aller sur Administration → Extensions → « Outils d'infrastructure ».
3. Cliquer Martin, Titiler, Grafana : chacun doit s'ouvrir dans un nouvel
   onglet et afficher son UI normale sous son sous-chemin (pas de page
   blanche, pas d'assets cassés — vérifier l'onglet réseau du navigateur
   pour des 404 sur des fichiers statiques, signe d'un problème de
   sous-chemin non résolu par la configuration des Tâches 4-5).
4. Cliquer le lien MinIO : doit ouvrir `http://<host>:9001` (accès direct,
   sans gate — comportement attendu, pas une régression).

- [ ] **Step 8: Nettoyage**

```bash
docker compose down
```

- [ ] **Step 9: Mise à jour de `CLAUDE.md`**

Ajouter une ligne dans la section `### Livré` (au format des entrées SP
existantes — ce chantier n'a pas de numéro SP, l'indiquer explicitement)
décrivant ce qui a été livré, tout suivi non bloquant trouvé pendant les
Steps 1-7 ci-dessus, et l'état des jalons/questions ouvertes pertinentes
(cf. gabarit des entrées `### Livré` déjà présentes, et
`docs/superpowers/2026-08-27-historique-execution-sp0-sp26.md` pour le
niveau de détail attendu dans l'historique séparé si ce chantier grossit).

- [ ] **Step 10: Commit final**

```bash
git add CLAUDE.md
git commit -m "docs: consigne le chantier Traefik /admin/* dans CLAUDE.md"
```
