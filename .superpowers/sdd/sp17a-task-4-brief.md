### Task 4: Jeton d'export dans `app.auth` + extension de `get_current_user`

> **Placement délibéré** : le jeton d'export vit dans `app.auth`, pas dans `app.export`. Le contrat de couches import-linter place `app.auth` tout en bas (juste au-dessus de `app.audit`/`app.users`/`app.tenants`) — `app.export` sera ajouté bien plus haut (à côté de `app.pipelines`/`app.alerts`, Tâche 13). Si le jeton vivait dans `app.export`, `get_current_user` (dans `app.auth`) devrait l'importer — une violation de couche ascendante. En le mettant dans `app.auth`, c'est `app.export` (haut) qui importera `app.auth` (bas) pour *minter* un jeton, exactement comme `app.pipelines.jobs` importe déjà `app.auth.dependency.is_etl_enabled`.

**Files:**
- Create: `core/app/auth/export_tokens.py`
- Modify: `core/app/auth/dependency.py:59-108` (fonction `get_current_user`)
- Test: `core/tests/test_export_tokens.py`
- Test: `core/tests/test_auth_export_token.py`

**Interfaces:**
- Produces (`app.auth.export_tokens`) : `class ExportTokenError(Exception)`, `class ExportTokenClaims` (attributs `tenant_id: str`, `user_id: str`, `job_id: str`), `mint_export_token(*, tenant_id: str, user_id: str, job_id: str, ttl_seconds: int = 120) -> str`, `is_export_token(token: str) -> bool`, `decode_export_token(token: str) -> ExportTokenClaims` (lève `ExportTokenError`).
- Consumes (dans `dependency.py`) : les quatre symboles ci-dessus.

- [ ] **Step 1: Écrire le test du module de jeton, qui échoue**

```python
# core/tests/test_export_tokens.py
# SPDX-License-Identifier: Apache-2.0
import time

import jwt
import pytest

from app.auth.export_tokens import (
    ExportTokenError,
    decode_export_token,
    is_export_token,
    mint_export_token,
)


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")


def test_mint_and_decode_round_trip():
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    claims = decode_export_token(token)
    assert claims.tenant_id == "t1"
    assert claims.user_id == "u1"
    assert claims.job_id == "j1"


def test_is_export_token_true_for_export_token_false_for_rs256():
    export_token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    assert is_export_token(export_token) is True
    rs256_like = jwt.encode({"sub": "x"}, "irrelevant", algorithm="HS512")
    assert is_export_token(rs256_like) is False
    assert is_export_token("not-even-a-jwt") is False


def test_decode_rejects_expired_token(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1", ttl_seconds=-1)
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_tampered_signature(monkeypatch):
    token = mint_export_token(tenant_id="t1", user_id="u1", job_id="j1")
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "a-different-secret")
    with pytest.raises(ExportTokenError):
        decode_export_token(token)


def test_decode_rejects_wrong_typ_claim():
    bad = jwt.encode({"typ": "not-export", "tenant_id": "t1", "user_id": "u1", "job_id": "j1",
                       "iat": int(time.time()), "exp": int(time.time()) + 60}, "test-export-secret", algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)


def test_decode_rejects_missing_claim():
    bad = jwt.encode({"typ": "export", "tenant_id": "t1"}, "test-export-secret", algorithm="HS256")
    with pytest.raises(ExportTokenError):
        decode_export_token(bad)
```

- [ ] **Step 2: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_export_tokens.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.auth.export_tokens'`

- [ ] **Step 3: Implémenter le module de jeton**

```python
# core/app/auth/export_tokens.py
# SPDX-License-Identifier: Apache-2.0
"""Jeton d'export éphémère (SP-17a) : permet au worker Playwright de
naviguer la page runtime avec les droits réels de l'utilisateur qui a
demandé l'export, sans compte de service à droits larges. Révocation par
TTL court uniquement (~2 min) — pas de suivi « déjà consommé » : aucun
précédent de jeton à usage unique n'existe dans ce dépôt (les liens S3
présignés, seul mécanisme comparable, sont eux aussi révoqués par TTL
seul). Colocalisé dans app.auth (pas app.export) : voir la note de
placement dans le plan d'implémentation, tâche 4."""
import os
import time

import jwt

_ALGORITHM = "HS256"
_TYP = "export"
_REQUIRED_CLAIMS = ("tenant_id", "user_id", "job_id")


class ExportTokenError(Exception):
    pass


class ExportTokenClaims:
    def __init__(self, *, tenant_id: str, user_id: str, job_id: str) -> None:
        self.tenant_id = tenant_id
        self.user_id = user_id
        self.job_id = job_id


def _secret() -> str:
    return os.environ["CORE_EXPORT_TOKEN_SECRET"]


def mint_export_token(*, tenant_id: str, user_id: str, job_id: str, ttl_seconds: int = 120) -> str:
    now = int(time.time())
    claims = {
        "typ": _TYP, "tenant_id": tenant_id, "user_id": user_id, "job_id": job_id,
        "iat": now, "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def is_export_token(token: str) -> bool:
    try:
        header = jwt.get_unverified_header(token)
    except jwt.PyJWTError:
        return False
    return header.get("alg") == _ALGORITHM


def decode_export_token(token: str) -> ExportTokenClaims:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except jwt.PyJWTError as exc:
        raise ExportTokenError(str(exc)) from exc
    if claims.get("typ") != _TYP:
        raise ExportTokenError("wrong token type")
    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise ExportTokenError(f"missing claims: {missing}")
    return ExportTokenClaims(
        tenant_id=claims["tenant_id"], user_id=claims["user_id"], job_id=claims["job_id"],
    )
```

- [ ] **Step 4: Vérifier que le test du module de jeton passe**

Run: `cd core && uv run pytest tests/test_export_tokens.py -v`
Expected: PASS (6 tests)

- [ ] **Step 5: Écrire le test de `get_current_user`, qui échoue**

```python
# core/tests/test_auth_export_token.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException

from app.auth.dependency import get_current_user
from app.auth.export_tokens import mint_export_token
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret")
    monkeypatch.delenv("CORE_AUTH_MODE", raising=False)


def _session_with_user():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    session = Session()
    tenant = get_or_create_default_tenant(session)
    user = get_or_create_user(
        session, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="Alice", last_name="", bootstrap_admin=False,
    )
    session.commit()
    return session, tenant, user


def test_get_current_user_accepts_valid_export_token():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id=user.id, job_id="job-1")
    resolved = get_current_user(authorization=f"Bearer {token}", session=session)
    assert resolved.id == user.id


def test_get_current_user_rejects_expired_export_token():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id=user.id, job_id="job-1", ttl_seconds=-1)
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_export_token_for_wrong_tenant():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id="some-other-tenant", user_id=user.id, job_id="job-1")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_export_token_for_deleted_user():
    session, tenant, user = _session_with_user()
    token = mint_export_token(tenant_id=tenant.id, user_id="never-existed", job_id="job-1")
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_rejects_missing_bearer():
    session, _tenant, _user = _session_with_user()
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="", session=session)
    assert exc_info.value.status_code == 401


def test_get_current_user_falls_through_to_oidc_path_for_non_hs256_garbage(monkeypatch):
    # Un jeton qui n'est structurellement pas un jeton d'export (alg != HS256,
    # ou pas un JWT du tout) doit continuer vers le chemin OIDC existant, pas
    # planter — et échouer là avec le même 401/503 qu'avant cette tâche.
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example.test/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio")
    session, _tenant, _user = _session_with_user()
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization="Bearer not-a-jwt-at-all", session=session)
    assert exc_info.value.status_code in (401, 503)
```

- [ ] **Step 6: Vérifier que le test échoue**

Run: `cd core && uv run pytest tests/test_auth_export_token.py -v`
Expected: FAIL — jeton d'export non reconnu, `get_current_user` tente la validation RS256/JWKS et lève une erreur différente (probablement 503 réseau ou 401 générique sans passer par le chemin attendu) sur le premier test.

- [ ] **Step 7: Implémenter l'extension de `get_current_user`**

Dans `core/app/auth/dependency.py`, ajouter l'import en tête (après les imports existants, ligne 12) :

```python
from app.auth.export_tokens import ExportTokenError, decode_export_token, is_export_token
```

Puis, dans `get_current_user` (lignes 59-108), insérer le nouveau chemin juste après le bloc `if _mock_mode(): ...` (après la ligne 80, avant le `try:` du décodage RS256 ligne 82) :

```python
    if is_export_token(token):
        try:
            claims = decode_export_token(token)
        except ExportTokenError as exc:
            raise HTTPException(status_code=401, detail="invalid export token") from exc
        if claims.tenant_id != tenant.id:
            raise HTTPException(status_code=401, detail="invalid export token")
        user = session.get(User, claims.user_id)
        if user is None:
            raise HTTPException(status_code=401, detail="invalid export token")
        return user
```

- [ ] **Step 8: Vérifier que le test passe**

Run: `cd core && uv run pytest tests/test_auth_export_token.py -v`
Expected: PASS (6 tests)

- [ ] **Step 9: Vérifier l'absence de régression sur la suite auth existante**

Run: `cd core && uv run pytest tests/ -k auth -v`
Expected: PASS (tous les tests d'auth existants, notamment ceux qui exercent le mode mock et le chemin RS256/JWKS réel, restent verts)

- [ ] **Step 10: Documenter la variable d'environnement**

Dans `.env.example`, juste après `CORE_EXPORT_ENABLED=false` (ajouté Tâche 2) :

```
# Secret HMAC signant les jetons d'export éphémères (SP-17a) — chaîne
# quelconque, pas de format base64 requis (contrairement à
# CORE_SECRETS_MASTER_KEY). Lu paresseusement (os.environ[...], échec
# rapide) seulement quand un jeton est réellement minté/décodé — une
# instance qui n'active jamais CORE_EXPORT_ENABLED n'a pas besoin de le
# définir. Générer avec : openssl rand -base64 32
CORE_EXPORT_TOKEN_SECRET=
```

- [ ] **Step 11: Commit**

```bash
git add core/app/auth/export_tokens.py core/app/auth/dependency.py core/tests/test_export_tokens.py core/tests/test_auth_export_token.py .env.example
git commit -m "feat(core): SP-17a — jeton d'export HS256 + extension de get_current_user"
```

---

