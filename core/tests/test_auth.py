# SPDX-License-Identifier: Apache-2.0
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app.auth import dependency
from app.db import init_db, make_engine, make_session_factory


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s
    engine.dispose()


def test_mock_mode_resolves_mockuser(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    user = dependency.get_current_user(authorization="Bearer anything", session=session)
    assert user.username == "mockuser"


def test_missing_bearer_prefix_raises_401(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="not-a-bearer-token", session=session)
    assert exc_info.value.status_code == 401


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


def test_missing_bearer_prefix_never_resolves_tenant(monkeypatch, session):
    # REV-012 : get_current_user résolvait (et créait au besoin) le tenant
    # par défaut AVANT de vérifier l'en-tête Authorization — toute requête
    # non authentifiée sur une route protégée faisait donc un accès base
    # avant son 401. Un tenant qui explose à la résolution ne doit jamais
    # être atteint quand le header est absent/mal formé.
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    from fastapi import HTTPException

    def _boom(_session):
        raise AssertionError("tenant resolution must not run before the Bearer check")

    monkeypatch.setattr(dependency, "get_or_create_default_tenant", _boom)

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="not-a-bearer-token", session=session)
    assert exc_info.value.status_code == 401

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="", session=session)
    assert exc_info.value.status_code == 401


def test_oidc_mode_validates_and_provisions_user(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(
        {
            "sub": "sub-123",
            "aud": "geostudio-core",
            "iss": "https://keycloak.example/realms/geostudio",
            "preferred_username": "alice",
            "email": "alice@example.com",
            "given_name": "Alice",
            "family_name": "Doe",
        },
        private_key,
        algorithm="RS256",
    )
    monkeypatch.setattr(dependency, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    user = dependency.get_current_user(authorization=f"Bearer {token}", session=session)
    assert user.username == "alice"
    assert user.email == "alice@example.com"


def test_oidc_mode_rejects_wrong_audience(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    from fastapi import HTTPException

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(
        {
            "sub": "sub-123",
            "aud": "someone-else",
            "iss": "https://keycloak.example/realms/geostudio",
        },
        private_key,
        algorithm="RS256",
    )
    monkeypatch.setattr(dependency, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


def test_oidc_mode_rejects_wrong_issuer(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    from fastapi import HTTPException

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    token = jwt.encode(
        {
            "sub": "sub-123",
            "aud": "geostudio-core",
            "iss": "https://someone-else.example/realms/other",
        },
        private_key,
        algorithm="RS256",
    )
    monkeypatch.setattr(dependency, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization=f"Bearer {token}", session=session)
    assert exc_info.value.status_code == 401


class _RaisingJWKSClient:
    def __init__(self, exc):
        self._exc = exc

    def get_signing_key_from_jwt(self, token):
        raise self._exc


def test_jwks_connection_error_returns_503(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    from fastapi import HTTPException

    monkeypatch.setattr(
        dependency,
        "_jwks_client",
        lambda: _RaisingJWKSClient(jwt.PyJWKClientConnectionError("network down")),
    )

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="Bearer sometoken", session=session)
    assert exc_info.value.status_code == 503


def test_jwks_unknown_kid_returns_401(monkeypatch, session):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_OIDC_AUDIENCE", "geostudio-core")
    from fastapi import HTTPException

    monkeypatch.setattr(
        dependency,
        "_jwks_client",
        lambda: _RaisingJWKSClient(jwt.PyJWKClientError("Unable to find a signing key")),
    )

    with pytest.raises(HTTPException) as exc_info:
        dependency.get_current_user(authorization="Bearer sometoken", session=session)
    assert exc_info.value.status_code == 401


def test_jwks_client_is_memoized(monkeypatch):
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    dependency._jwks_client.cache_clear()

    client1 = dependency._jwks_client()
    client2 = dependency._jwks_client()

    assert client1 is client2


def test_analyst_subs_parses_env(monkeypatch):
    from app.auth.dependency import analyst_subs

    monkeypatch.setenv("CORE_ANALYST_SUBS", " a , b ,, c ")
    assert analyst_subs() == {"a", "b", "c"}


def test_analyst_subs_empty_when_unset(monkeypatch):
    from app.auth.dependency import analyst_subs

    monkeypatch.delenv("CORE_ANALYST_SUBS", raising=False)
    assert analyst_subs() == set()
