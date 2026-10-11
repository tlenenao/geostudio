# SPDX-License-Identifier: Apache-2.0
"""REV-299 (b)(c) + proxys IPv6 : limiteur share-link."""

from fastapi.testclient import TestClient

from app.main import _EXPORT_PATH_RE, create_app, trusted_proxy_hosts
from app.ratelimit.limiter import route_group


def _app(monkeypatch, **env):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    monkeypatch.delenv("CORE_TRUSTED_PROXIES", raising=False)
    monkeypatch.delenv("CORE_RATELIMIT_SHARE_LINK_PER_MIN", raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    return create_app()


def _get(client, path, xff, **extra):
    return client.get(path, headers={"X-Forwarded-For": xff, **extra}).status_code


def test_route_group_share_token_header_joins_share_link_group():
    assert route_group("/v1/items", "GET", _EXPORT_PATH_RE, has_share_token=True) == "share-link"
    assert route_group("/v1/items", "GET", _EXPORT_PATH_RE) is None


def test_share_token_header_is_rate_limited_per_ip(monkeypatch):
    client = TestClient(_app(monkeypatch), client=("10.1.2.3", 5), raise_server_exceptions=False)
    for i in range(60):
        assert _get(client, "/v1/items", "9.9.9.9", **{"X-Share-Link-Token": f"t{i}"}) != 429
    assert _get(client, "/v1/items", "9.9.9.9", **{"X-Share-Link-Token": "t"}) == 429
    # même groupe que la route publique : le budget est partagé
    assert _get(client, "/v1/share-links/zz", "9.9.9.9") == 429


def test_share_link_budget_is_configurable(monkeypatch):
    app = _app(monkeypatch, CORE_RATELIMIT_SHARE_LINK_PER_MIN="3")
    client = TestClient(app, client=("10.1.2.3", 5), raise_server_exceptions=False)
    for i in range(3):
        assert _get(client, f"/v1/share-links/b{i}", "9.9.9.9") != 429
    assert _get(client, "/v1/share-links/b3", "9.9.9.9") == 429


def test_default_trusted_proxies_cover_ipv6_ula(monkeypatch):
    monkeypatch.delenv("CORE_TRUSTED_PROXIES", raising=False)
    assert "fc00::/7" in trusted_proxy_hosts()


def test_forwarded_for_ipv6_trusted_vs_untrusted(monkeypatch):
    trusted = TestClient(_app(monkeypatch), client=("fd00::1", 5), raise_server_exceptions=False)
    for i in range(60):
        _get(trusted, f"/v1/share-links/a{i}", "9.9.9.9")
    assert _get(trusted, "/v1/share-links/a", "9.9.9.9") == 429
    assert _get(trusted, "/v1/share-links/b", "8.8.8.8") != 429

    untrusted = TestClient(
        _app(monkeypatch), client=("2001:db8::1", 5), raise_server_exceptions=False
    )
    for i in range(60):
        _get(untrusted, f"/v1/share-links/c{i}", f"7.7.7.{i}")
    assert _get(untrusted, "/v1/share-links/z", "6.6.6.6") == 429
