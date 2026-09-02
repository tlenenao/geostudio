# SPDX-License-Identifier: Apache-2.0
"""Garde de démarrage pour CORE_ADMIN_TOOLS_ENABLED=true avec
CORE_ADMIN_TOOLS_TOKEN_SECRET vide/absent — même patron que
test_mock_mode_guard.py::reject_mock_outside_development. Sans cette
garde, POST /admin-tools/launch/{tool} lève InvalidKeyError("HMAC key
must not be empty.") non attrapé (jwt.encode(..., "")), un 500 opaque
plutôt qu'une erreur de configuration claire au démarrage — CLAUDE.md
nomme cette classe de bug (valeur par défaut vide) comme déjà payée
plusieurs fois dans ce dépôt."""

import pytest

from app.main import create_app


def test_admin_tools_enabled_without_secret_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    monkeypatch.delenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", raising=False)
    with pytest.raises(
        RuntimeError,
        match="CORE_ADMIN_TOOLS_ENABLED=true requires a non-empty CORE_ADMIN_TOOLS_TOKEN_SECRET",
    ):
        create_app()


def test_admin_tools_enabled_with_empty_string_secret_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", "")
    with pytest.raises(
        RuntimeError,
        match="CORE_ADMIN_TOOLS_ENABLED=true requires a non-empty CORE_ADMIN_TOOLS_TOKEN_SECRET",
    ):
        create_app()


def test_admin_tools_enabled_with_secret_boots(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    monkeypatch.setenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", "test-admin-tools-secret-padding")
    create_app()  # doit ne pas lever


def test_admin_tools_disabled_boots_regardless_of_secret(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "false")
    monkeypatch.delenv("CORE_ADMIN_TOOLS_TOKEN_SECRET", raising=False)
    create_app()  # doit ne pas lever : la garde ne concerne que la capacité active
