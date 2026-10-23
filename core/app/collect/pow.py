# SPDX-License-Identifier: Apache-2.0
"""Preuve de travail (hashcash) de la soumission publique (L8, Q5 : pas de captcha tiers).

Le cœur émet un défi `v1.<expiration>.<aléa>.<mac>` lié au jeton public (HMAC dérivé de la clé
maîtresse du coffre, aucun nouveau secret). Le client cherche un `nonce` tel que
SHA-256(`<défi>:<nonce>`) ait au moins `BITS` bits de tête à zéro. Un défi n'est valable qu'une
fois et 60 s. Désactivation réservée aux tests : `CORE_PUBLIC_SUBMIT_POW_DISABLED=1`.

ponytail: le registre des défis consommés est en mémoire de process (comme le limiteur par IP) :
derrière plusieurs réplicas un défi pourrait être rejoué une fois par réplica pendant ses 60 s ;
le quota du jeton et la limite par IP restent les garde-fous. Table partagée si cela compte."""

import hashlib
import hmac
import os
import secrets
import threading
import time

from app.secrets.crypto import load_master_key

BITS = 18
TTL_SECONDS = 60
_used: dict[str, float] = {}
_lock = threading.Lock()


def disabled() -> bool:
    return os.environ.get("CORE_PUBLIC_SUBMIT_POW_DISABLED") == "1"


def _mac(token_prefix: str, expires: str, rand: str) -> str:
    key = hmac.new(load_master_key(), b"gs-collect-pow-v1", hashlib.sha256).digest()
    return hmac.new(key, f"{token_prefix}.{expires}.{rand}".encode(), hashlib.sha256).hexdigest()


def issue(token_prefix: str, *, now: float | None = None) -> dict:
    expires = str(int((now or time.time()) + TTL_SECONDS))
    rand = secrets.token_hex(8)
    challenge = f"v1.{expires}.{rand}.{_mac(token_prefix, expires, rand)}"
    return {"challenge": challenge, "bits": BITS, "expiresAt": int(expires)}


def leading_zero_bits(digest: bytes) -> int:
    n = int.from_bytes(digest, "big")
    return len(digest) * 8 - n.bit_length()


def verify(
    token_prefix: str, challenge: str, nonce: str, *, now: float | None = None, bits: int = BITS
) -> bool:
    """Vrai si le défi est authentique, non expiré, jamais consommé et la preuve suffisante.
    Le défi est consommé dès que sa signature et son expiration sont valides (une preuve
    insuffisante le brûle aussi : pas d'essais gratuits sur un même défi)."""
    parts = challenge.split(".")
    if len(parts) != 4 or parts[0] != "v1" or not nonce or len(nonce) > 64:
        return False
    _, expires, rand, mac = parts
    if not hmac.compare_digest(mac, _mac(token_prefix, expires, rand)):
        return False
    t = now or time.time()
    if not expires.isdigit() or int(expires) < t:
        return False
    with _lock:
        for k in [k for k, exp in _used.items() if exp < t]:
            del _used[k]
        if challenge in _used:
            return False
        _used[challenge] = float(expires)
    digest = hashlib.sha256(f"{challenge}:{nonce}".encode()).digest()
    return leading_zero_bits(digest) >= bits


def reset() -> None:
    with _lock:
        _used.clear()
