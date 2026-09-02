# SPDX-License-Identifier: Apache-2.0
from app.auth.dependency import is_admin_tools_enabled


def test_is_admin_tools_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_ADMIN_TOOLS_ENABLED", raising=False)
    assert is_admin_tools_enabled() is False


def test_is_admin_tools_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "true")
    assert is_admin_tools_enabled() is True
    monkeypatch.setenv("CORE_ADMIN_TOOLS_ENABLED", "false")
    assert is_admin_tools_enabled() is False
