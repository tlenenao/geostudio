# SPDX-License-Identifier: Apache-2.0
"""Identité portée par le jeton MCP du corps de POST /copilot/turn (SP-20,
C1 de la revue de projet 2026-08-20 : confused deputy).

Vraie paire de clés RSA + vrais jetons signés : le décodage est le point
même qu'on vérifie ici, un `jwt.decode` mocké ne prouverait rien.
"""
import datetime

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa

from app.copilot.mcp_token import McpTokenError, mcp_token_subject

ISSUER = "https://keycloak.example/realms/geostudio"
AUDIENCE = "geostudio-mcp"


@pytest.fixture(scope="module")
def keypair():
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = private.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return pem, private.public_key()


def _token(pem, *, sub="alice-sub", aud=AUDIENCE, iss=ISSUER, expired=False):
    now = datetime.datetime.now(tz=datetime.timezone.utc)
    exp = now - datetime.timedelta(minutes=5) if expired else now + datetime.timedelta(minutes=5)
    return jwt.encode(
        {"sub": sub, "aud": aud, "iss": iss, "iat": now, "exp": exp},
        pem, algorithm="RS256",
    )


@pytest.fixture()
def oidc_mode(monkeypatch, keypair):
    """Mode OIDC réel, JWKS remplacé par la clé publique locale (aucun
    réseau) — le reste du chemin (signature, audience, issuer, exp) est le
    vrai code de production."""
    _, public_key = keypair
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_OIDC_ISSUER", ISSUER)
    monkeypatch.setenv("CORE_MCP_AUDIENCE", AUDIENCE)

    class _StubKey:
        key = public_key

    class _StubJwks:
        def get_signing_key_from_jwt(self, token):
            return _StubKey()

    import app.copilot.mcp_token as mcp_token_module
    monkeypatch.setattr(mcp_token_module, "_jwks_client", lambda: _StubJwks())


def test_returns_the_subject_of_a_valid_mcp_token(oidc_mode, keypair):
    pem, _ = keypair
    assert mcp_token_subject(_token(pem, sub="alice-sub")) == "alice-sub"


def test_rejects_a_token_minted_for_the_rest_audience(oidc_mode, keypair):
    """Un jeton d'audience geostudio-core (celui du header Authorization)
    ne doit jamais passer pour un jeton MCP : sinon la vérification
    d'identité serait satisfaite par le jeton que l'appelant possède
    forcément déjà, et ne prouverait rien."""
    pem, _ = keypair
    with pytest.raises(McpTokenError):
        mcp_token_subject(_token(pem, aud="geostudio-core"))


def test_rejects_a_token_from_another_issuer(oidc_mode, keypair):
    pem, _ = keypair
    with pytest.raises(McpTokenError):
        mcp_token_subject(_token(pem, iss="https://evil.example/realms/geostudio"))


def test_rejects_an_expired_token(oidc_mode, keypair):
    pem, _ = keypair
    with pytest.raises(McpTokenError):
        mcp_token_subject(_token(pem, expired=True))


def test_rejects_garbage(oidc_mode):
    with pytest.raises(McpTokenError):
        mcp_token_subject("not-a-jwt")


def test_mock_mode_resolves_the_fixed_mock_subject_without_decoding(monkeypatch):
    """Miroir de MockTokenVerifier côté /mcp (n'importe quel jeton y résout
    mock-sub) et de la branche mock de get_current_user (oidc_sub =
    mock-sub) : la comparaison d'identité reste vraie en dev/CI sans
    Keycloak."""
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    assert mcp_token_subject("anything") == "mock-sub"
