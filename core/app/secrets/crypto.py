# SPDX-License-Identifier: Apache-2.0
"""Chiffrement applicatif AES-256-GCM des secrets connecteurs (design
SP-15e §2/§4 —
docs/superpowers/specs/2026-08-06-sp15e-connector-secrets-store-design.md).
La clé maître ne doit JAMAIS être loguée, incluse dans un message d'erreur,
un span OTel ou une entrée audit_log."""

import base64
import json
import os
from typing import Any

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE_BYTES = 12
_KEY_SIZE_BYTES = 32


def decode_key_material(raw: str, *, source: str) -> bytes:
    """Factorise la validation déjà faite par `load_master_key()` — décodage
    base64 puis longueur exacte 32 octets. `source` sert uniquement au
    message d'erreur (nom de la variable d'origine), jamais la valeur
    elle-même (design §4 : la clé ne doit jamais apparaître dans un message
    d'erreur)."""
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError(f"{source} must be valid base64") from exc
    if len(key) != _KEY_SIZE_BYTES:
        raise RuntimeError(f"{source} must decode to {_KEY_SIZE_BYTES} bytes, got {len(key)}")
    return key


def load_master_key() -> bytes:
    """Lit CORE_SECRETS_MASTER_KEY (32 octets encodés base64). Lève
    `KeyError` si absente, `RuntimeError` si mal formée — échec rapide,
    jamais un défaut silencieux (design §4)."""
    raw = os.environ["CORE_SECRETS_MASTER_KEY"]
    return decode_key_material(raw, source="CORE_SECRETS_MASTER_KEY")


def encrypt(payload: dict[str, Any], key: bytes | None = None) -> tuple[bytes, bytes]:
    key = key if key is not None else load_master_key()
    nonce = os.urandom(_NONCE_SIZE_BYTES)
    plaintext = json.dumps(payload).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes, key: bytes | None = None) -> dict[str, Any]:
    key = key if key is not None else load_master_key()
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    doc: dict[str, Any] = json.loads(plaintext)
    return doc
