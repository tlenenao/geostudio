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
