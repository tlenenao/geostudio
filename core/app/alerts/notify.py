# SPDX-License-Identifier: Apache-2.0
"""Notification delivery for AlertRule (design SP-16b §5). Webhook is
egress-guarded (user-supplied URL); email is not (admin-configured SMTP
secret) — see Global Constraints in the plan for the trust-model
rationale.

Webhook delivery goes through `app.alerts.egress.build_guarded_session()`
rather than a bare `requests.post()`: `requests` follows HTTP redirects by
default, and a one-time `assert_egress_allowed()` check on the original
URL does not cover any redirect hop — a webhook URL that looks public but
302s to an internal target (e.g. the cloud metadata endpoint
`http://169.254.169.254/...`) would pass the one-time check and then get
followed anyway, defeating the guard. The guarded session's adapter
re-checks egress on every hop `resolve_redirects()` sends through it (see
`app/alerts/egress.py`), not just the first request, so the upfront check
below (kept for a fast, clear failure before doing anything else) is
belt-and-suspenders on top of the session-level guard that actually
matters for redirects."""

import smtplib
from email.message import EmailMessage

import requests
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, assert_egress_allowed, build_guarded_session
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

    session = build_guarded_session()
    try:
        resp = session.post(channel.url, json=payload, timeout=10)
        resp.raise_for_status()
    except EgressBlockedError as exc:
        # Raised by the guarded session's adapter on a redirect hop that
        # resolves to an internal target — see module docstring.
        raise NotifyError(f"webhook egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        raise NotifyError(f"webhook delivery failed: {exc}") from exc


def send_email(
    session: Session,
    *,
    tenant_id: str,
    channel: AlertChannelEmail,
    subject: str,
    body: str,
) -> None:
    payload = secrets_repo.get_secret_payload(
        session, tenant_id=tenant_id, name=channel.smtpSecretName
    )
    if payload is None:
        raise NotifyError(f"secret '{channel.smtpSecretName}' not found")
    if payload.kind != "smtp":
        raise NotifyError(f"secret has kind '{payload.kind}', not usable for email (expected smtp)")

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
