# SPDX-License-Identifier: Apache-2.0
"""Identité portée par le jeton MCP présenté à POST /copilot/turn (SP-20).

La route authentifie son appelant par le header Authorization (audience
REST, `get_current_user`) mais ouvre la session MCP avec un **second**
jeton, fourni dans le corps de la requête (audience MCP). Sans la
vérification ci-dessous les deux identités ne sont jamais comparées :
quiconque détient un jeton d'audience MCP appartenant à un autre
utilisateur peut faire exécuter les outils d'écriture (`create_item`,
`create_form_app`) sous cette identité en présentant simplement son propre
header Authorization — un confused deputy (C1 de la revue de projet
2026-08-20).

Décodage volontairement dupliqué de `app.mcp.auth.KeycloakTokenVerifier` :
`app.mcp` est AU-DESSUS de `app.copilot` dans le contrat de couches
(pyproject.toml), donc l'importer est interdit. Même précédent que
`app.mcp.auth`, qui duplique déjà `app.auth.dependency._jwks_client`, et
que `app.pipelines.egress`, qui duplique la garde SSRF d'`app.harvest`
pour la même raison de couches.
"""

import os
from functools import lru_cache

import jwt


class McpTokenError(Exception):
    """Jeton MCP illisible, expiré, mal signé, de mauvais issuer ou de
    mauvaise audience."""


@lru_cache(maxsize=1)
def _jwks_client() -> jwt.PyJWKClient:
    issuer = os.environ["CORE_OIDC_ISSUER"]
    jwks_url = os.environ.get("CORE_OIDC_JWKS_URL", f"{issuer}/protocol/openid-connect/certs")
    return jwt.PyJWKClient(jwks_url, lifespan=600)


def mcp_token_subject(token: str) -> str:
    """`sub` du jeton, après validation signature/audience/issuer/exp.

    L'audience exigée est CORE_MCP_AUDIENCE (défaut `geostudio-mcp`),
    jamais celle du header Authorization : un jeton REST — que l'appelant
    possède forcément — ne doit pas pouvoir satisfaire la comparaison
    d'identité.

    En mode mock, renvoie le sujet fixe `mock-sub` sans rien décoder :
    c'est exactement ce que fait `MockTokenVerifier` côté `/mcp` (tout
    jeton y résout cette identité) et ce que renvoie `get_current_user`
    dans ce mode — la comparaison reste donc vraie en dev/CI, sans
    Keycloak.
    """
    if os.environ.get("CORE_AUTH_MODE", "oidc") == "mock":
        return "mock-sub"

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
    except jwt.PyJWTError as exc:
        raise McpTokenError(str(exc)) from exc

    sub = claims.get("sub")
    if not sub:
        raise McpTokenError("jeton MCP sans sub")
    return sub
