# SPDX-License-Identifier: Apache-2.0
import socket

import pytest
import requests

from app.pipelines.egress import (
    EgressBlockedError,
    assert_egress_allowed,
    build_guarded_session,
)


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1/x",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/x",
        "http://192.168.1.1/x",
        "http://[::1]/x",
        "http://[fc00::1]/x",
        "http://0.0.0.0/x",
    ],
)
def test_assert_blocks_internal_ip_literals_without_dns(url):
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed(url)


def test_assert_allows_public_ip_literal():
    assert_egress_allowed("https://93.184.216.34/x") is None


def test_assert_blocks_non_http_scheme():
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("file:///etc/passwd")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("ftp://example.com/x")


def test_assert_blocks_hostname_resolving_to_internal(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.1.2.3", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://evil.example.com/x")


def test_assert_allows_hostname_resolving_to_public(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    assert_egress_allowed("https://public.example.com/x") is None


def test_allowlist_restricts_otherwise_allowed_public_host(monkeypatch):
    def fake_getaddrinfo(host, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]

    monkeypatch.setattr(socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "other.example.com")
    with pytest.raises(EgressBlockedError):
        assert_egress_allowed("https://public.example.com/x")
    monkeypatch.setenv("CORE_PIPELINES_EGRESS_ALLOWLIST", "public.example.com,other.example.com")
    assert_egress_allowed("https://public.example.com/x") is None


def test_guarded_session_blocks_before_connection():
    # 127.0.0.1:9 (discard) : la garde doit lever AVANT toute tentative de
    # connexion réseau — donc EgressBlockedError, jamais un ConnectionError.
    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://127.0.0.1:9/x", timeout=1.0)


def test_guarded_session_is_a_real_requests_session():
    session = build_guarded_session()
    assert isinstance(session, requests.Session)
