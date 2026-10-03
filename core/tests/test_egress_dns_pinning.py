# SPDX-License-Identifier: Apache-2.0
"""REV-273d : épinglage DNS de la couche d'egress (5 copies de la garde)."""

import importlib
import socket

import pytest

EGRESS_MODULES = [
    "app.pipelines.egress",
    "app.alerts.egress",
    "app.harvest.egress",
    "app.copilot.egress",
    "app.search.egress",
]
PUBLIC = "93.184.216.34"


def _resolver(*answers):
    """getaddrinfo qui renvoie successivement `answers` (le dernier se répète)."""
    calls = {"n": 0}

    def fake(host, *args, **kwargs):
        ip = answers[min(calls["n"], len(answers) - 1)]
        calls["n"] += 1
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return fake, calls


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_assert_returns_the_validated_address(monkeypatch, modname):
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC)
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://public.example.com/x") == PUBLIC
    assert mod.assert_egress_allowed("https://93.184.216.34:8443/x") == PUBLIC


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_empty_resolution_is_refused(monkeypatch, modname):
    mod = importlib.import_module(modname)
    monkeypatch.setattr(socket, "getaddrinfo", lambda *a, **k: [])
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("https://empty.example.com/x")


@pytest.mark.parametrize("modname", EGRESS_MODULES)
def test_second_resolution_to_loopback_is_refused(monkeypatch, modname):
    """Double résolveur : 1re réponse publique (contrôle), 2e réponse 127.0.0.1
    (rebinding au moment de la connexion) → la 2e passe par la même garde."""
    mod = importlib.import_module(modname)
    fake, _ = _resolver(PUBLIC, "127.0.0.1")
    monkeypatch.setattr(socket, "getaddrinfo", fake)
    assert mod.assert_egress_allowed("https://rebind.example.com/x") == PUBLIC
    with pytest.raises(mod.EgressBlockedError):
        mod.assert_egress_allowed("https://rebind.example.com/x")
