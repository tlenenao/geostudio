# SPDX-License-Identifier: Apache-2.0
"""Jeton de lien de partage à échéance (GAP-12, chantier 4.23) — calqué sur
app.auth.export_tokens (SP-17a), adapté : TTL configurable par l'appelant
(jours, pas une constante ~2 min, bornée par _MAX_TTL_SECONDS), claims sans
user_id (un lien de partage n'authentifie pas un utilisateur donné, il donne
accès en lecture seule à UN item précis). Contrairement au jeton d'export,
ce jeton doit aussi pouvoir être révoqué avant expiration — la vérification
de révocation (consultation de la ligne share_link par son id, embarqué
dans les claims) vit dans app.sharing.repository::get_active_share_link,
pas ici : ce module ne connaît que le JWT lui-même, jamais la base."""

import os
import time

import jwt

_ALGORITHM = "HS256"
_TYP = "share_link"
_REQUIRED_CLAIMS = ("share_link_id", "tenant_id", "item_id")
_MAX_TTL_SECONDS = 30 * 86400


class ShareLinkTokenError(Exception):
    pass


class ShareLinkTokenClaims:
    def __init__(self, *, share_link_id: str, tenant_id: str, item_id: str) -> None:
        self.share_link_id = share_link_id
        self.tenant_id = tenant_id
        self.item_id = item_id


def _secret() -> str:
    return os.environ["CORE_SHARE_LINK_TOKEN_SECRET"]


def mint_share_link_token(
    *, share_link_id: str, tenant_id: str, item_id: str, ttl_seconds: int
) -> str:
    if ttl_seconds > _MAX_TTL_SECONDS:
        raise ValueError(f"ttl_seconds must not exceed {_MAX_TTL_SECONDS} (30 days)")
    now = int(time.time())
    claims = {
        "typ": _TYP,
        "share_link_id": share_link_id,
        "tenant_id": tenant_id,
        "item_id": item_id,
        "iat": now,
        "exp": now + ttl_seconds,
    }
    return jwt.encode(claims, _secret(), algorithm=_ALGORITHM)


def decode_share_link_token(token: str) -> ShareLinkTokenClaims:
    try:
        claims = jwt.decode(token, _secret(), algorithms=[_ALGORITHM])
    except (jwt.PyJWTError, KeyError) as exc:
        # KeyError couvre CORE_SHARE_LINK_TOKEN_SECRET absente (_secret()
        # ci-dessus) : une instance qui n'a jamais configuré ce secret ne
        # doit jamais planter en 500 sur un jeton HS256 forgé par un
        # attaquant, elle doit le rejeter en 401 comme n'importe quel autre
        # jeton de lien invalide (même discipline qu'export_tokens.py).
        raise ShareLinkTokenError(str(exc)) from exc
    if claims.get("typ") != _TYP:
        raise ShareLinkTokenError("wrong token type")
    missing = [c for c in _REQUIRED_CLAIMS if c not in claims]
    if missing:
        raise ShareLinkTokenError(f"missing claims: {missing}")
    return ShareLinkTokenClaims(
        share_link_id=claims["share_link_id"],
        tenant_id=claims["tenant_id"],
        item_id=claims["item_id"],
    )
