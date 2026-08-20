# SPDX-License-Identifier: Apache-2.0
"""Chiffrement applicatif AES-256-GCM des secrets connecteurs (design
SP-15e §2/§4 —
docs/superpowers/specs/2026-08-06-sp15e-connector-secrets-store-design.md).
La clé maître ne doit JAMAIS être loguée, incluse dans un message d'erreur,
un span OTel ou une entrée audit_log."""

import base64
import json
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

_NONCE_SIZE_BYTES = 12
_KEY_SIZE_BYTES = 32


def load_master_key() -> bytes:
    """Lit CORE_SECRETS_MASTER_KEY (32 octets encodés base64). Lève
    `KeyError` si absente, `RuntimeError` si mal formée — échec rapide,
    jamais un défaut silencieux (design §4)."""
    raw = os.environ["CORE_SECRETS_MASTER_KEY"]
    try:
        key = base64.b64decode(raw, validate=True)
    except Exception as exc:
        raise RuntimeError("CORE_SECRETS_MASTER_KEY must be valid base64") from exc
    if len(key) != _KEY_SIZE_BYTES:
        raise RuntimeError(
            f"CORE_SECRETS_MASTER_KEY must decode to {_KEY_SIZE_BYTES} bytes, got {len(key)}"
        )
    return key


def encrypt(payload: dict) -> tuple[bytes, bytes]:
    key = load_master_key()
    nonce = os.urandom(_NONCE_SIZE_BYTES)
    plaintext = json.dumps(payload).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, None)
    return ciphertext, nonce


def decrypt(ciphertext: bytes, nonce: bytes) -> dict:
    key = load_master_key()
    plaintext = AESGCM(key).decrypt(nonce, ciphertext, None)
    return json.loads(plaintext)
