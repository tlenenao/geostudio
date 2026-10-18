# SPDX-License-Identifier: Apache-2.0
"""AUD-056 : cache et concurrence bornée du proxy de tuiles TiTiler."""

import threading

import pytest
from pytest_httpserver import HTTPServer

from app.tile_proxy import TileProxyBusyError, fetch_tile


def test_second_identical_call_is_served_from_cache(httpserver: HTTPServer):
    httpserver.expect_oneshot_request("/t.png").respond_with_data(b"PNG", content_type="image/png")
    url = httpserver.url_for("/t.png")
    assert fetch_tile(url, {"a": "1"}) == (200, b"PNG")
    assert fetch_tile(url, {"a": "1"}) == (200, b"PNG")  # un second appel réseau ferait échouer


def test_errors_are_not_cached(httpserver: HTTPServer):
    url = httpserver.url_for("/t.png")
    httpserver.expect_oneshot_request("/t.png").respond_with_data(b"", status=500)
    assert fetch_tile(url, {})[0] == 500
    httpserver.expect_oneshot_request("/t.png").respond_with_data(b"OK")
    assert fetch_tile(url, {}) == (200, b"OK")


def test_saturation_raises_busy(monkeypatch, httpserver: HTTPServer):
    monkeypatch.setenv("CORE_TILE_PROXY_CONCURRENCY", "1")
    release, started = threading.Event(), threading.Event()

    def slow(_request):
        started.set()
        release.wait(5)
        from werkzeug.wrappers import Response

        return Response(b"x")

    httpserver.expect_request("/slow.png").respond_with_handler(slow)
    url = httpserver.url_for("/slow.png")
    first = threading.Thread(target=lambda: fetch_tile(url, {"k": "1"}, timeout=4.0))
    first.start()
    assert started.wait(3)
    try:
        with pytest.raises(TileProxyBusyError):
            fetch_tile(url, {"k": "2"}, timeout=0.4)
    finally:
        release.set()
        first.join()
