# SPDX-License-Identifier: Apache-2.0
import base64

import pytest
from cryptography.exceptions import InvalidTag

from app.secrets import crypto

TEST_KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def test_encrypt_decrypt_round_trip(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"kind": "bearer_token", "token": "s3cr3t"})
    assert crypto.decrypt(ciphertext, nonce) == {"kind": "bearer_token", "token": "s3cr3t"}


def test_decrypt_rejects_tampered_ciphertext(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"token": "s3cr3t"})
    tampered = bytes([ciphertext[0] ^ 0xFF]) + ciphertext[1:]
    with pytest.raises(InvalidTag):
        crypto.decrypt(tampered, nonce)


def test_decrypt_rejects_wrong_key(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    ciphertext, nonce = crypto.encrypt({"token": "s3cr3t"})
    other_key = base64.b64encode(bytes(range(1, 33))).decode()
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", other_key)
    with pytest.raises(InvalidTag):
        crypto.decrypt(ciphertext, nonce)


def test_load_master_key_missing_raises(monkeypatch):
    monkeypatch.delenv("CORE_SECRETS_MASTER_KEY", raising=False)
    with pytest.raises(KeyError):
        crypto.load_master_key()


def test_load_master_key_malformed_base64_raises(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", "not-valid-base64!!")
    with pytest.raises(RuntimeError, match="valid base64"):
        crypto.load_master_key()


def test_load_master_key_wrong_length_raises(monkeypatch):
    short_key = base64.b64encode(b"short").decode()
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", short_key)
    with pytest.raises(RuntimeError, match="32 bytes"):
        crypto.load_master_key()
