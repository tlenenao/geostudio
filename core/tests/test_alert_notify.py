# SPDX-License-Identifier: Apache-2.0
import socket
from unittest.mock import MagicMock, patch

import pytest
import requests

from app.alerts.egress import EgressBlockedError
from app.alerts.notify import NotifyError, send_email, send_webhook
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.db import init_db, make_engine, make_session_factory
from app.secrets import crypto as secrets_crypto
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SmtpCredentialsPayload
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

# 32 raw bytes, base64-encoded — matches the fixture key used in
# test_secrets_repository.py's own round-trip test.
TEST_KEY_B64 = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="


def _fake_getaddrinfo_public(host, *args, **kwargs):
    # example.test is an RFC 2606 reserved TLD that never resolves in real
    # DNS — mocked the same way the sister guard tests do (test_alert_egress.py
    # / test_pipeline_egress.py / test_harvest_egress.py) so these tests don't
    # depend on network access.
    return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0))]


def test_send_webhook_blocks_an_internal_url():
    channel = AlertChannelWebhook(url="http://127.0.0.1/hook")
    with pytest.raises(NotifyError):
        send_webhook(channel, payload={"state": "firing"})


def test_send_webhook_posts_json_to_the_url(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_public)
    channel = AlertChannelWebhook(url="https://example.test/hook")
    mock_session = MagicMock()
    mock_session.post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
    with patch("app.alerts.notify.build_guarded_session", return_value=mock_session):
        send_webhook(channel, payload={"state": "firing"})
    mock_session.post.assert_called_once()
    assert mock_session.post.call_args.args[0] == "https://example.test/hook"
    assert mock_session.post.call_args.kwargs["json"] == {"state": "firing"}


def test_send_webhook_wraps_a_request_failure(monkeypatch):
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_public)
    channel = AlertChannelWebhook(url="https://example.test/hook")
    mock_session = MagicMock()
    mock_session.post.side_effect = requests.ConnectionError("boom")
    with patch("app.alerts.notify.build_guarded_session", return_value=mock_session):
        with pytest.raises(NotifyError):
            send_webhook(channel, payload={"state": "firing"})


def test_send_webhook_rechecks_egress_on_redirect_hops(monkeypatch):
    """Regression for the SSRF gap that a one-time assert_egress_allowed()
    check on the original URL does not cover: `requests` follows redirects
    by default, so a webhook URL that looks public but 302s to an internal
    target (e.g. the cloud metadata endpoint) must still be blocked on the
    redirect hop, not just on the original URL.

    Only the actual network I/O (HTTPAdapter.send, the real base class that
    would otherwise open a socket) is faked here — Session.send(),
    resolve_redirects(), and our own _GuardedHTTPAdapter.send()'s egress
    check all run for real, via the real build_guarded_session(). This
    proves the guard is re-applied on the second hop, not just mocked away.
    """
    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_public)

    redirect_response = requests.Response()
    redirect_response.status_code = 302
    redirect_response.headers = {"location": "http://169.254.169.254/latest/meta-data/"}
    redirect_response.raw = None

    def fake_adapter_send(self, request, **kwargs):
        redirect_response.request = request
        redirect_response.url = request.url
        return redirect_response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", fake_adapter_send)

    channel = AlertChannelWebhook(url="https://public.example.test/hook")
    with pytest.raises(NotifyError) as exc_info:
        send_webhook(channel, payload={"state": "firing"})
    assert isinstance(exc_info.value.__cause__, EgressBlockedError)


def test_guarded_session_used_by_send_webhook_blocks_before_connection():
    # Direct evidence (no mocking at all) that the real session
    # build_guarded_session() hands to send_webhook enforces the guard on
    # its own — same style as test_pipeline_egress.py's
    # test_guarded_session_blocks_before_connection.
    from app.alerts.egress import build_guarded_session

    session = build_guarded_session()
    with pytest.raises(EgressBlockedError):
        session.get("http://127.0.0.1:9/x", timeout=1.0)


@pytest.fixture()
def smtp_secret_session(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_KEY_B64)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        payload = SmtpCredentialsPayload(
            host="smtp.example.test",
            port=587,
            username="alerts@example.test",
            password="s3cret",
            useTls=True,
            fromAddress="alerts@example.test",
        )
        ciphertext, nonce = secrets_crypto.encrypt(SECRET_PAYLOAD_ADAPTER.dump_python(payload))
        secrets_repo.create_secret(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            name="smtp-main",
            kind="smtp",
            ciphertext=ciphertext,
            nonce=nonce,
        )
        s.commit()
        tenant_id = tenant.id
    yield Session, tenant_id
    engine.dispose()


def test_send_email_delivers_via_smtp_secret(smtp_secret_session):
    Session, tenant_id = smtp_secret_session
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        with patch("app.alerts.notify.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
            send_email(s, tenant_id=tenant_id, channel=channel, subject="Alert", body="value=150")
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("alerts@example.test", "s3cret")
    mock_smtp.send_message.assert_called_once()


def test_send_email_raises_when_secret_is_missing(smtp_secret_session):
    Session, tenant_id = smtp_secret_session
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="does-not-exist")
    with Session() as s:
        with pytest.raises(NotifyError):
            send_email(s, tenant_id=tenant_id, channel=channel, subject="Alert", body="value=150")
