import os
from functools import lru_cache

import jwt
from mcp.server.auth.provider import AccessToken, TokenVerifier


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    # Deliberately duplicated from app.auth.dependency._jwks_client rather
    # than imported — the two auth surfaces (shell REST API vs. MCP) must be
    # free to evolve independently (see plan Architecture).
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get(
        "CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs"
    )
    return jwt.PyJWKClient(jwks_url, lifespan=600)


class KeycloakTokenVerifier(TokenVerifier):
    """Validates MCP bearer tokens against CORE_MCP_AUDIENCE — a distinct
    audience from CORE_OIDC_AUDIENCE, so a token valid for the shell's REST
    API is never valid here, and vice versa."""

    async def verify_token(self, token: str) -> AccessToken | None:
        issuer = os.environ["CORE_OIDC_ISSUER"]
        audience = os.environ.get("CORE_MCP_AUDIENCE", "geostudio-mcp")
        try:
            signing_key = _jwks_client().get_signing_key_from_jwt(token)
            claims = jwt.decode(
                token,
                signing_key.key,
                algorithms=["RS256"],
                audience=audience,
                issuer=issuer,
            )
        except jwt.PyJWTError:
            return None

        return AccessToken(
            token=token,
            client_id=claims.get("azp", "unknown"),
            scopes=claims.get("scope", "").split() if claims.get("scope") else [],
            expires_at=claims.get("exp"),
            resource=audience,
            subject=claims["sub"],
            claims=claims,
        )


class MockTokenVerifier(TokenVerifier):
    """Dev/CI verifier: never contacts Keycloak, always resolves the same
    fixed identity — mirrors get_current_user's CORE_AUTH_MODE=mock branch
    (same mock-sub/mockuser convention)."""

    async def verify_token(self, token: str) -> AccessToken | None:
        return AccessToken(
            token=token,
            client_id="mock-client",
            scopes=[],
            expires_at=None,
            resource=os.environ.get("CORE_MCP_AUDIENCE", "geostudio-mcp"),
            subject="mock-sub",
            claims={
                "sub": "mock-sub",
                "preferred_username": "mockuser",
                "given_name": "Mock",
                "family_name": "User",
            },
        )


def get_token_verifier() -> TokenVerifier:
    if os.environ.get("CORE_AUTH_MODE", "oidc") == "mock":
        return MockTokenVerifier()
    return KeycloakTokenVerifier()
