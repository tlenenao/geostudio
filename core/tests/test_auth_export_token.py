# SPDX-License-Identifier: Apache-2.0
import jwt
import pytest
from fastapi import HTTPException

from app.auth.dependency import get_current_user
from app.auth.export_tokens import mint_export_token
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# >=32 bytes: avoids PyJWT's InsecureKeyLengthWarning for HS256, which this
# repo's pytest config (filterwarnings = ["error", ...], pyproject.toml)
# promotes to a hard failure. See test_export_tokens.py for the same fix.
_SECRET = "test-export-secret-padding-01234"


@pytest.fixture(autouse=True)
def export_secret(monkeypatch):
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", _SECRET)
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


def test_get_current_user_rejects_forged_hs256_token_when_export_secret_unset(monkeypatch):
    # Régression du Critical de revue SP-17a : avec CORE_EXPORT_TOKEN_SECRET absente
    # (toute instance à ce jour), un attaquant non authentifié envoyant un JWT HS256
    # forgé de son cru (secret de son choix, aucune connaissance requise) ne doit
    # jamais faire planter get_current_user en 500 (KeyError non attrapée depuis
    # export_tokens._secret()) — il doit obtenir un 401 propre, comme n'importe quel
    # jeton d'export invalide.
    session, _tenant, _user = _session_with_user()
    monkeypatch.delenv("CORE_EXPORT_TOKEN_SECRET", raising=False)
    forged = jwt.encode(
        {"typ": "export", "tenant_id": "t1", "user_id": "u1", "job_id": "j1"},
        "attacker-controlled-secret-of-their-choosing",
        algorithm="HS256",
    )
    with pytest.raises(HTTPException) as exc_info:
        get_current_user(authorization=f"Bearer {forged}", session=session)
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
