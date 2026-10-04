# SPDX-License-Identifier: Apache-2.0
"""Garde d'egress du géocodage (REV-102) : plages internes bloquées, allowlist
propre (CORE_GEOCODING_EGRESS_ALLOWLIST, défaut data.geopf.fr)."""

import socket

import httpx
import pytest

from app.geocoding.egress import EgressBlockedError, assert_egress_allowed, build_guarded_client

PUBLIC = "93.184.216.34"


def _public(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda host, *a, **k: [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (PUBLIC, 0))],
    )


@pytest.mark.parametrize("url", ["http://127.0.0.1/x", "http://10.0.0.5/x", "http://[::1]/x"])
def test_internal_targets_are_blocked(monkeypatch, url):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_default_allowlist_is_the_geoplateforme_only(monkeypatch):
    monkeypatch.delenv("CORE_GEOCODING_EGRESS_ALLOWLIST", raising=False)
    _public(monkeypatch)
    assert assert_egress_allowed("https://data.geopf.fr/geocodage/search") == PUBLIC
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/geocodage/search")


def test_operator_allowlist_overrides_the_default(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "geocodeur.interne.example")
    _public(monkeypatch)
    assert assert_egress_allowed("https://geocodeur.interne.example/search") == PUBLIC
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://data.geopf.fr/geocodage/search")


def test_guarded_client_blocks_before_connecting(monkeypatch):
    monkeypatch.setenv("CORE_GEOCODING_EGRESS_ALLOWLIST", "")
    with build_guarded_client() as client, pytest.raises(EgressBlockedError):
        client.get("http://127.0.0.1:1/x")


def test_guarded_client_does_not_follow_redirects():
    with build_guarded_client() as client:
        assert client.follow_redirects is False
        assert isinstance(client, httpx.Client)
