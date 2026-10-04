# SPDX-License-Identifier: Apache-2.0
import socket
import ssl
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
        from app.items import repository as items_repo

        item_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="alert", title="rule"
        ).id
        s.commit()
    yield Session, tenant_id, item_id
    engine.dispose()


def test_send_email_delivers_via_smtp_secret(smtp_secret_session):
    Session, tenant_id, item_id = smtp_secret_session
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        with patch("app.alerts.notify.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
            send_email(
                s,
                tenant_id=tenant_id,
                item_id=item_id,
                channel=channel,
                subject="Alert",
                body="value=150",
            )
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("alerts@example.test", "s3cret")
    mock_smtp.send_message.assert_called_once()


def test_send_email_raises_when_secret_is_missing(smtp_secret_session):
    Session, tenant_id, item_id = smtp_secret_session
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="does-not-exist")
    with Session() as s:
        with pytest.raises(NotifyError):
            send_email(
                s,
                tenant_id=tenant_id,
                item_id=item_id,
                channel=channel,
                subject="Alert",
                body="value=150",
            )


def test_send_email_refuses_secret_the_rule_owner_cannot_use(smtp_secret_session):
    # P16.08 : le propriétaire de la règle n'est pas propriétaire du secret
    # SMTP et n'a pas admin.secrets.manage -> secret traité comme absent.
    Session, tenant_id, _item_id = smtp_secret_session
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        mallory = get_or_create_user(
            s,
            tenant_id=tenant_id,
            oidc_sub="m",
            username="mallory",
            email=None,
            first_name="",
            last_name="",
        )
        from app.items import repository as items_repo

        rule_id = items_repo.create_item(
            s, tenant_id=tenant_id, owner_id=mallory.id, resource_type="alert", title="r2"
        ).id
        with patch("app.alerts.notify.smtplib.SMTP") as mock_smtp_cls:
            with pytest.raises(NotifyError):
                send_email(
                    s,
                    tenant_id=tenant_id,
                    item_id=rule_id,
                    channel=channel,
                    subject="A",
                    body="b",
                )
        mock_smtp_cls.assert_not_called()


def test_send_webhook_signs_the_exact_body_with_the_channel_secret(monkeypatch):
    # P20.04 (j09b-003)
    import hashlib
    import hmac

    from app.alerts import notify
    from app.secrets.schemas import BearerTokenPayload

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_public)
    monkeypatch.setattr(notify, "_owner_user", lambda *a, **k: object())
    monkeypatch.setattr(
        notify.secrets_repo,
        "get_secret_payload",
        lambda *a, **k: BearerTokenPayload(token="s3cr3t"),
    )
    channel = AlertChannelWebhook(url="https://example.test/hook", signingSecretName="sig")
    mock_session = MagicMock()
    mock_session.post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
    with patch("app.alerts.notify.build_guarded_session", return_value=mock_session):
        send_webhook(
            channel, payload={"state": "firing"}, session=MagicMock(), tenant_id="t", item_id="i"
        )
    kwargs = mock_session.post.call_args.kwargs
    expected = hmac.new(b"s3cr3t", kwargs["data"], hashlib.sha256).hexdigest()
    assert kwargs["headers"]["X-GeoStudio-Signature"] == f"sha256={expected}"


def test_send_webhook_fails_when_the_signing_secret_is_unusable(monkeypatch):
    from app.alerts import notify

    monkeypatch.setattr(socket, "getaddrinfo", _fake_getaddrinfo_public)
    monkeypatch.setattr(notify, "_owner_user", lambda *a, **k: object())
    monkeypatch.setattr(notify.secrets_repo, "get_secret_payload", lambda *a, **k: None)
    channel = AlertChannelWebhook(url="https://example.test/hook", signingSecretName="sig")
    with pytest.raises(NotifyError, match="signing secret"):
        send_webhook(channel, payload={}, session=MagicMock(), tenant_id="t", item_id="i")


def test_secret_references_include_webhook_signing_secret():
    """P20 revue finale : supprimer un secret de signature encore cité par une
    alerte doit être refusé comme pour smtpSecretName (jumelle de find_usages)."""
    from app.secrets.repository import _references

    cfg = {"alert": {"channels": [{"kind": "webhook", "signingSecretName": "sig"}]}}
    assert _references(cfg, "sig")


@pytest.fixture()
def smtp_variant_session(monkeypatch, request):
    """Comme smtp_secret_session mais host/port/useTls pilotés par request.param."""
    host, port, use_tls = request.param
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
        # Construit via model_construct : simule un secret STOCKÉ avant L2c-2
        # (la validation d'écriture de SecretCreate ne s'applique pas à la lecture).
        payload = SmtpCredentialsPayload.model_construct(
            kind="smtp",
            host=host,
            port=port,
            username="alerts@example.test",
            password="s3cret",
            useTls=use_tls,
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
        from app.items import repository as items_repo

        item_id = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="alert", title="rule"
        ).id
        s.commit()
        tenant_id = tenant.id
    yield Session, tenant_id, item_id
    engine.dispose()


def _send(Session, tenant_id, item_id):
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        send_email(s, tenant_id=tenant_id, item_id=item_id, channel=channel, subject="A", body="b")


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 25, False)], indirect=True)
def test_send_email_refuses_stored_secret_without_tls_on_remote_host(smtp_variant_session):
    with (
        patch("app.alerts.notify.smtplib.SMTP") as smtp_cls,
        patch("app.alerts.notify.smtplib.SMTP_SSL") as ssl_cls,
    ):
        with pytest.raises(NotifyError, match="useTls=false.*PUT /v1/secrets"):
            _send(*smtp_variant_session)
    smtp_cls.assert_not_called()
    ssl_cls.assert_not_called()


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 465, True)], indirect=True)
def test_send_email_uses_smtp_ssl_on_port_465(smtp_variant_session):
    with (
        patch("app.alerts.notify.smtplib.SMTP") as smtp_cls,
        patch("app.alerts.notify.smtplib.SMTP_SSL") as ssl_cls,
    ):
        server = ssl_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    smtp_cls.assert_not_called()
    ctx = ssl_cls.call_args.kwargs["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True
    server.starttls.assert_not_called()
    server.login.assert_called_once_with("alerts@example.test", "s3cret")
    server.send_message.assert_called_once()


@pytest.mark.parametrize("smtp_variant_session", [("smtp.example.test", 587, True)], indirect=True)
def test_send_email_starttls_verifies_the_certificate(smtp_variant_session):
    import ssl

    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    ctx = server.starttls.call_args.kwargs["context"]
    assert ctx.verify_mode == ssl.CERT_REQUIRED and ctx.check_hostname is True


@pytest.mark.parametrize("smtp_variant_session", [("localhost", 25, False)], indirect=True)
def test_send_email_allows_plain_smtp_on_localhost(smtp_variant_session):
    with patch("app.alerts.notify.smtplib.SMTP") as smtp_cls:
        server = smtp_cls.return_value.__enter__.return_value
        _send(*smtp_variant_session)
    server.starttls.assert_not_called()
    server.send_message.assert_called_once()
