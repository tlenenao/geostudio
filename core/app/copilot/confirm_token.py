# SPDX-License-Identifier: Apache-2.0
"""Jeton de confirmation d'écriture du copilote (AUD-102).

Un outil d'écriture proposé par le LLM revient au shell sous forme d'op
`confirmWrite` ; le clic humain le renvoie. Sans lien cryptographique entre la
proposition et l'exécution, `confirmWrite.arguments` serait un dict libre rejoué
tel quel. Le jeton lie utilisateur + nom d'outil + sha256(arguments) + échéance :
modifier un seul argument, changer d'outil ou d'utilisateur invalide la confirmation.

Clé : dérivée de `CORE_SECRETS_MASTER_KEY` (déjà obligatoire), jamais utilisée telle quelle."""

import hashlib
import hmac
import time
from typing import Any

from app.audit.context import args_sha256
from app.secrets.crypto import load_master_key

CONFIRM_TTL_SECONDS = 600


class ConfirmTokenError(Exception):
    pass


def _mac(user_id: str, name: str, arguments: dict[str, Any], exp: int) -> str:
    key = hmac.new(load_master_key(), b"copilot-confirm-write-v1", hashlib.sha256).digest()
    msg = f"{user_id}\n{name}\n{args_sha256(arguments)}\n{exp}".encode()
    return hmac.new(key, msg, hashlib.sha256).hexdigest()


def sign_confirmation(
    user_id: str, name: str, arguments: dict[str, Any], *, now: float | None = None
) -> str:
    exp = int((time.time() if now is None else now) + CONFIRM_TTL_SECONDS)
    return f"{exp}.{_mac(user_id, name, arguments, exp)}"


def verify_confirmation(
    token: str, user_id: str, name: str, arguments: dict[str, Any], *, now: float | None = None
) -> None:
    try:
        exp_s, mac = token.split(".", 1)
        exp = int(exp_s)
    except ValueError as exc:
        raise ConfirmTokenError("jeton de confirmation malformé") from exc
    if (time.time() if now is None else now) > exp:
        raise ConfirmTokenError("jeton de confirmation expiré")
    if not hmac.compare_digest(mac, _mac(user_id, name, arguments, exp)):
        raise ConfirmTokenError("jeton de confirmation invalide pour ces arguments")
