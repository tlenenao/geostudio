import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app.auth import dependency
from app.db import make_engine, make_session_factory, init_db


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
        {"sub": "sub-123", "aud": "someone-else"}, private_key, algorithm="RS256"
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


def test_jwks_client_is_memoized(monkeypatch):
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    dependency._jwks_client.cache_clear()

    client1 = dependency._jwks_client()
    client2 = dependency._jwks_client()

    assert client1 is client2
