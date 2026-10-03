# SPDX-License-Identifier: Apache-2.0
import socket

import pytest

from app.alerts.egress import EgressBlockedError, assert_egress_allowed, build_guarded_session


def test_blocks_a_loopback_url():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("http://127.0.0.1:8080/hook")


def test_blocks_a_private_range_url():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("http://10.0.0.5/hook")


def test_blocks_a_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")


def test_allows_a_public_https_url(monkeypatch):
    # example.test est un TLD réservé (RFC 2606) qui ne se résout jamais en
    # DNS réel — on simule la résolution comme les gardes sœurs
    # (test_pipeline_egress.py / test_harvest_egress.py) pour ne pas
    # dépendre du réseau.
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert assert_egress_allowed("https://example.test/hook") == "93.184.216.34"


def test_allowlist_restricts_to_named_hosts(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_ALERTS_EGRESS_ALLOWLIST", "allowed.example.test")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://not-allowed.example.test/hook")


def test_alert_guarded_session_refuses_dns_rebinding_between_check_and_connect(monkeypatch):
    """Double résolveur : le contrôle de send() voit une IP publique, la
    résolution faite au moment de connecter voit 127.0.0.1 → refus."""
    answers = iter(["93.184.216.34", "127.0.0.1"])

    def fake_getaddrinfo(host, *args, **kwargs):
        ip = next(answers, "127.0.0.1")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://rebind.example.com:9/x", timeout=1.0)
