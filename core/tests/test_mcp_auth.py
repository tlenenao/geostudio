# SPDX-License-Identifier: Apache-2.0
import os

import pytest
from cryptography.hazmat.primitives.asymmetric import rsa
import jwt

from app.mcp import auth as mcp_auth


class _FakeSigningKey:
    def __init__(self, key):
        self.key = key


class _FakeJWKSClient:
    def __init__(self, public_key):
        self._public_key = public_key

    def get_signing_key_from_jwt(self, token):
        return _FakeSigningKey(self._public_key)


@pytest.fixture()
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    return private_key, private_key.public_key()


def _make_token(private_key, *, audience="geostudio-mcp", issuer="https://keycloak.example/realms/geostudio", **claims):
    payload = {"sub": "sub-123", "aud": audience, "iss": issuer, **claims}
    return jwt.encode(payload, private_key, algorithm="RS256")


@pytest.mark.anyio
async def test_keycloak_verifier_accepts_valid_mcp_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    token = _make_token(private_key, preferred_username="alice")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is not None
    assert result.subject == "sub-123"
    assert result.claims["preferred_username"] == "alice"


@pytest.mark.anyio
async def test_keycloak_verifier_rejects_rest_api_audience(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    # A token valid for the shell's REST API (audience geostudio-core) must
    # NOT be accepted here — the two surfaces have distinct audiences.
    token = _make_token(private_key, audience="geostudio-core")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is None


@pytest.mark.anyio
async def test_keycloak_verifier_rejects_wrong_issuer(monkeypatch, rsa_keypair):
    private_key, public_key = rsa_keypair
    monkeypatch.setenv("CORE_OIDC_ISSUER", "https://keycloak.example/realms/geostudio")
    monkeypatch.setenv("CORE_MCP_AUDIENCE", "geostudio-mcp")
    monkeypatch.setattr(mcp_auth, "_jwks_client", lambda: _FakeJWKSClient(public_key))

    token = _make_token(private_key, issuer="https://someone-else.example/realms/other")
    verifier = mcp_auth.KeycloakTokenVerifier()
    result = await verifier.verify_token(token)

    assert result is None


@pytest.mark.anyio
async def test_mock_verifier_always_resolves_mock_subject():
    verifier = mcp_auth.MockTokenVerifier()
    result = await verifier.verify_token("anything-at-all")

    assert result is not None
    assert result.subject == "mock-sub"


@pytest.fixture
def anyio_backend():
    return "asyncio"
