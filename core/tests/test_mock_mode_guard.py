# SPDX-License-Identifier: Apache-2.0
import pytest

from app.main import create_app


def test_mock_mode_without_development_marker_refuses_to_boot(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.delenv("CORE_ENV", raising=False)
    with pytest.raises(RuntimeError, match="CORE_AUTH_MODE=mock requires CORE_ENV=development"):
        create_app()


def test_mock_mode_with_development_marker_boots(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.setenv("CORE_ENV", "development")
    create_app()  # doit ne pas lever


def test_oidc_mode_boots_regardless_of_core_env(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.delenv("CORE_ENV", raising=False)
    create_app()  # doit ne pas lever : la garde ne concerne que le mode mock
