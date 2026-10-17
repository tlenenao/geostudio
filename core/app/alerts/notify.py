# SPDX-License-Identifier: Apache-2.0
"""Notification delivery for AlertRule (design SP-16b §5). Webhook is
egress-guarded (user-supplied URL); email is not (admin-configured SMTP
secret) — see Global Constraints in the plan for the trust-model
rationale.

Webhook delivery goes through `app.alerts.egress.build_guarded_session()`
(egress guard + DNS pinning) and never follows redirects (AUD-169): a 3xx
is a delivery failure, so a public-looking URL cannot bounce the POST — and
its `X-GeoStudio-Signature` header, re-sent as-is on 307/308 — to another
target. The upfront `assert_egress_allowed()` check gives a fast, clear
failure before doing anything else."""

import hashlib
import hmac
import json
import smtplib
from email.message import EmailMessage

import requests
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.alerts.egress import EgressBlockedError, assert_egress_allowed, build_guarded_session
from app.configs.schemas import AlertChannelEmail, AlertChannelWebhook
from app.items.models import Item
from app.secrets import repository as secrets_repo
from app.secrets.schemas import SMTP_LOCAL_HOSTS, smtp_tls_violation
from app.secrets.smtp_send import send_smtp_message
from app.users.models import User


class NotifyError(Exception):
    """Notification delivery failed — always caught by the caller (Task 9)
    and turned into an audit_log entry + evaluation error, never left to
    crash the evaluation task."""


def _owner_user(session: Session, *, tenant_id: str, item_id: str) -> User | None:
    owner_id = session.scalar(
        select(Item.owner_id).where(Item.id == item_id, Item.tenant_id == tenant_id)
    )
    user = session.get(User, owner_id) if owner_id else None
    return user if user is not None and user.erased_at is None else None  # AUD-094


def send_webhook(
    channel: AlertChannelWebhook,
    *,
    payload: dict,
    session: Session | None = None,
    tenant_id: str | None = None,
    item_id: str | None = None,
) -> None:
    try:
        assert_egress_allowed(channel.url)
    except EgressBlockedError as exc:
        raise NotifyError(f"webhook egress blocked: {exc}") from exc

    request_kwargs: dict = {"json": payload}
    if channel.signingSecretName:
        # P20.04 : clé = secret du coffre, utilisé comme le propriétaire de l'item
        # (même modèle que send_email, P16.08) ; HMAC-SHA256 du corps exact envoyé.
        secret = None
        if session is not None and tenant_id and item_id:
            owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)
            if owner is not None:
                secret = secrets_repo.get_secret_payload(
                    session, tenant_id=tenant_id, name=channel.signingSecretName, user=owner
                )
        if secret is None or secret.kind != "bearer_token":
            raise NotifyError(f"signing secret '{channel.signingSecretName}' not usable")
        body = json.dumps(payload, separators=(",", ":"), sort_keys=True).encode()
        digest = hmac.new(secret.token.encode(), body, hashlib.sha256).hexdigest()
        request_kwargs = {
            "data": body,
            "headers": {
                "Content-Type": "application/json",
                "X-GeoStudio-Signature": f"sha256={digest}",
            },
        }

    session_http = build_guarded_session()
    try:
        resp = session_http.post(channel.url, timeout=10, allow_redirects=False, **request_kwargs)
        if 300 <= resp.status_code < 400:  # AUD-169 : jamais suivie, jamais « délivrée »
            raise requests.HTTPError(f"redirect refused ({resp.status_code})", response=resp)
        resp.raise_for_status()
    except EgressBlockedError as exc:
        # Raised by the guarded session's adapter (pinned connection re-check).
        raise NotifyError(f"webhook egress blocked: {exc}") from exc
    except requests.RequestException as exc:
        raise NotifyError(f"webhook delivery failed: {exc}") from exc


def send_email(
    session: Session,
    *,
    tenant_id: str,
    item_id: str,
    channel: AlertChannelEmail,
    subject: str,
    body: str,
) -> None:
    # P16.08 : l'alerte agit comme son propriétaire — il doit avoir le droit
    # d'usage sur le secret SMTP (indistinguable d'un secret absent sinon).
    owner = _owner_user(session, tenant_id=tenant_id, item_id=item_id)
    payload = (
        secrets_repo.get_secret_payload(
            session, tenant_id=tenant_id, name=channel.smtpSecretName, user=owner
        )
        if owner is not None
        else None
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

    violation = smtp_tls_violation(payload)
    if violation:
        # Secret stocké avant la validation d'écriture (REV-273e) : refus explicite,
        # jamais de bascule silencieuse vers TLS (le serveur peut ne pas le supporter).
        raise NotifyError(
            f"secret '{channel.smtpSecretName}' : {violation} — "
            "mettez à jour le secret (PUT /v1/secrets/{id}) avec useTls=true"
        )

    # REV-338 : le secret smtp est écrit par un utilisateur, pas forcément un admin —
    # même garde d'egress que writer.email (relais locaux de dev exemptés).
    host = payload.host.lower()
    if host not in SMTP_LOCAL_HOSTS:
        try:
            assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")
        except EgressBlockedError as exc:
            raise NotifyError(f"email egress blocked: {exc}") from exc

    try:
        send_smtp_message(payload, message)
    except (smtplib.SMTPException, OSError) as exc:
        raise NotifyError(f"email delivery failed: {exc}") from exc
