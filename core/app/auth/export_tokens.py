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
    except (jwt.PyJWTError, KeyError) as exc:
        # KeyError couvre CORE_EXPORT_TOKEN_SECRET absente (_secret() ci-dessus) :
        # une instance qui n'a jamais déployé le worker d'export ne doit jamais
        # crasher en 500 sur un jeton HS256 forgé par un attaquant, elle doit le
        # rejeter en 401 comme n'importe quel autre jeton d'export invalide.
        raise ExportTokenError(str(exc)) from exc
    if claims.get("typ") != _TYP:
        raise ExportTokenError("wrong token type")
    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise ExportTokenError(f"missing claims: {missing}")
    return ExportTokenClaims(
        tenant_id=claims["tenant_id"], user_id=claims["user_id"], job_id=claims["job_id"],
    )
