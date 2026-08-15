# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_appexport_enabled


def test_appexport_disabled_by_default(monkeypatch):
    monkeypatch.delenv("CORE_APPEXPORT_ENABLED", raising=False)
    assert is_appexport_enabled() is False


def test_appexport_enabled_via_env(monkeypatch):
    monkeypatch.setenv("CORE_APPEXPORT_ENABLED", "true")
    assert is_appexport_enabled() is True
