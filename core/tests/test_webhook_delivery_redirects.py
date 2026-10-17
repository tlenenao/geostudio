# SPDX-License-Identifier: Apache-2.0
"""AUD-169 : un POST signé ne suit jamais une redirection ; 3xx = échec."""

import pytest
import requests

from app.alerts import notify
from app.configs.schemas import AlertChannelWebhook
from app.webhooks import delivery


class _Resp:
    def __init__(self, status):
        self.status_code = status
        self.is_redirect = 300 <= status < 400

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(str(self.status_code), response=self)


def _session(status, seen):
    class _Session:
        def post(self, url, **kw):
            seen.update(kw)
            return _Resp(status)

    return _Session()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_redirect_is_a_delivery_failure_and_is_not_followed(monkeypatch, status):
    seen: dict = {}
    monkeypatch.setattr(delivery, "build_guarded_session", lambda: _session(status, seen))
    with pytest.raises(delivery.DeliveryError):
        delivery._http_post("https://hook.example/x", b"{}", {})
    assert seen["allow_redirects"] is False


@pytest.mark.parametrize("status", [301, 307, 308])
def test_alert_webhook_redirect_is_a_failure_and_is_not_followed(monkeypatch, status):
    seen: dict = {}
    monkeypatch.setattr(notify, "assert_egress_allowed", lambda url: None)
    monkeypatch.setattr(notify, "build_guarded_session", lambda: _session(status, seen))
    channel = AlertChannelWebhook(url="https://hook.example/x")
    with pytest.raises(notify.NotifyError):
        notify.send_webhook(channel, payload={"a": 1})
    assert seen["allow_redirects"] is False


def test_alert_webhook_2xx_still_delivers(monkeypatch):
    seen: dict = {}
    monkeypatch.setattr(notify, "assert_egress_allowed", lambda url: None)
    monkeypatch.setattr(notify, "build_guarded_session", lambda: _session(204, seen))
    notify.send_webhook(AlertChannelWebhook(url="https://h.example/"), payload={})
    assert seen["allow_redirects"] is False
