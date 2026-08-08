### Task 8: `app/alerts/notify.py` — webhook + email delivery

**Files:**
- Create: `core/app/alerts/notify.py`
- Test: `core/tests/test_alert_notify.py`

**Interfaces:**
- Consumes: `app.alerts.egress.assert_egress_allowed` (Task 6), `app.secrets.repository.get_secret_payload` (existing), `SmtpCredentialsPayload` (Task 7), `AlertChannelWebhook`/`AlertChannelEmail` (Task 2).
- Produces: `NotifyError`, `send_webhook(channel: AlertChannelWebhook, *, payload: dict) -> None`, `send_email(session, *, tenant_id: str, channel: AlertChannelEmail, subject: str, body: str) -> None`. Consumed by Task 9 (`app.alerts.jobs`).

- [ ] **Step 1: Write the failing tests**

```python
# core/tests/test_alert_notify.py
# SPDX-License-Identifier: Apache-2.0
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


def test_send_webhook_blocks_an_internal_url():
    channel = AlertChannelWebhook(url="http://127.0.0.1/hook")
    with pytest.raises(NotifyError):
        send_webhook(channel, payload={"state": "firing"})


def test_send_webhook_posts_json_to_the_url():
    channel = AlertChannelWebhook(url="https://example.test/hook")
    with patch("app.alerts.notify.requests.post") as mock_post:
        mock_post.return_value = MagicMock(status_code=200, raise_for_status=lambda: None)
        send_webhook(channel, payload={"state": "firing"})
    mock_post.assert_called_once()
    assert mock_post.call_args.args[0] == "https://example.test/hook"
    assert mock_post.call_args.kwargs["json"] == {"state": "firing"}


def test_send_webhook_wraps_a_request_failure():
    channel = AlertChannelWebhook(url="https://example.test/hook")
    with patch("app.alerts.notify.requests.post", side_effect=requests.ConnectionError("boom")):
        with pytest.raises(NotifyError):
            send_webhook(channel, payload={"state": "firing"})


def _make_session_with_smtp_secret():
    if not secrets_crypto._MASTER_KEY:  # ensure test harness has a master key loaded
        secrets_crypto.load_master_key()
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        payload = SmtpCredentialsPayload(
            host="smtp.example.test", port=587, username="alerts@example.test",
            password="s3cret", useTls=True, fromAddress="alerts@example.test",
        )
        ciphertext, nonce = secrets_crypto.encrypt(SECRET_PAYLOAD_ADAPTER.dump_python(payload))
        secrets_repo.create_secret(
            s, tenant_id=tenant.id, created_by=user.id, name="smtp-main", kind="smtp",
            ciphertext=ciphertext, nonce=nonce,
        )
        s.commit()
        tenant_id = tenant.id
    return Session, tenant_id


def test_send_email_delivers_via_smtp_secret():
    Session, tenant_id = _make_session_with_smtp_secret()
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="smtp-main")
    with Session() as s:
        with patch("app.alerts.notify.smtplib.SMTP") as mock_smtp_cls:
            mock_smtp = MagicMock()
            mock_smtp_cls.return_value.__enter__.return_value = mock_smtp
            send_email(s, tenant_id=tenant_id, channel=channel, subject="Alert", body="value=150")
    mock_smtp.starttls.assert_called_once()
    mock_smtp.login.assert_called_once_with("alerts@example.test", "s3cret")
    mock_smtp.send_message.assert_called_once()


def test_send_email_raises_when_secret_is_missing():
    Session, tenant_id = _make_session_with_smtp_secret()
    channel = AlertChannelEmail(to="ops@example.test", smtpSecretName="does-not-exist")
    with Session() as s:
        with pytest.raises(NotifyError):
            send_email(s, tenant_id=tenant_id, channel=channel, subject="Alert", body="value=150")
```

Check the real names of `app.secrets.crypto`'s encrypt function and master-key-loaded flag before finalizing this test (used above as `secrets_crypto.encrypt`/`secrets_crypto._MASTER_KEY`/`secrets_crypto.load_master_key`) — read `core/app/secrets/crypto.py` and `core/tests/test_secrets_repository.py` for the exact fixture pattern used there to set up a decryptable secret in a test, and align this test's setup to match verbatim rather than guessing the private attribute name.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_notify.py`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.alerts.notify'`

- [ ] **Step 3: Write the implementation**

```python
# core/app/alerts/notify.py
# SPDX-License-Identifier: Apache-2.0
"""Notification delivery for AlertRule (design SP-16b §5). Webhook is
egress-guarded (user-supplied URL); email is not (admin-configured SMTP
secret) — see Global Constraints in the plan for the trust-model
rationale."""
import smtplib
from email.message import EmailMessage

import requests
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, assert_egress_allowed
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.secrets import repository as secrets_repo


class NotifyError(Exception):
    """Notification delivery failed — always caught by the caller (Task 9)
    and turned into an audit_log entry + evaluation error, never left to
    crash the evaluation task."""


def send_webhook(channel: AlertChannelWebhook, *, payload: dict) -> None:
    try:
        assert_egress_allowed(channel.url)
    except EgressBlockedError as exc:
        raise NotifyError(f"webhook egress blocked: {exc}") from exc
    try:
        resp = requests.post(channel.url, json=payload, timeout=10)
        resp.raise_for_status()
    except requests.RequestException as exc:
        raise NotifyError(f"webhook delivery failed: {exc}") from exc


def send_email(
    session: Session, *, tenant_id: str, channel: AlertChannelEmail, subject: str, body: str,
) -> None:
    payload = secrets_repo.get_secret_payload(session, tenant_id=tenant_id, name=channel.smtpSecretName)
    if payload is None:
        raise NotifyError(f"secret '{channel.smtpSecretName}' not found")
    if payload.kind != "smtp":
        raise NotifyError(
            f"secret has kind '{payload.kind}', not usable for email (expected smtp)"
        )

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = payload.fromAddress
    message["To"] = channel.to
    message.set_content(body)

    try:
        with smtplib.SMTP(payload.host, payload.port, timeout=10) as smtp:
            if payload.useTls:
                smtp.starttls()
            smtp.login(payload.username, payload.password)
            smtp.send_message(message)
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"email delivery failed: {exc}") from exc
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && PYTHONPATH=. CORE_SECRETS_MASTER_KEY="$(head -c32 /dev/zero | base64)" uv run pytest -q tests/test_alert_notify.py`
Expected: `5 passed`

- [ ] **Step 5: Commit**

```bash
git add core/app/alerts/notify.py core/tests/test_alert_notify.py
git commit -m "feat(core): SP-16b — app.alerts.notify (webhook + SMTP email delivery)"
```

---

