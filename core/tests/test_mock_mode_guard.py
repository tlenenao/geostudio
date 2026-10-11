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
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "https://s3.example.org")  # REV-315
    create_app()  # doit ne pas lever : la garde ne concerne que le mode mock


def test_empty_public_s3_endpoint_outside_development_refuses_to_boot(monkeypatch):
    """REV-315 : liens présignés vers minio:9000 = injoignables du navigateur."""
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_ENV", "production")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "")
    with pytest.raises(RuntimeError, match="S3_PUBLIC_ENDPOINT_URL"):
        create_app()


def test_empty_public_s3_endpoint_in_development_boots(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "oidc")
    monkeypatch.setenv("CORE_ENV", "development")
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "")
    create_app()
