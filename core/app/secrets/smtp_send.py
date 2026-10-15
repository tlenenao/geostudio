# SPDX-License-Identifier: Apache-2.0
"""Envoi SMTP TLS à partir d'un secret `smtp` — point unique partagé par les alertes
(`app.alerts.notify.send_email`) et le writer de pipeline `writer.email`. Placé sous
`app.secrets` (couche basse) : `app.pipelines` ne peut pas importer `app.alerts`."""

import smtplib
import ssl
from collections.abc import Iterator
from contextlib import contextmanager
from email.message import EmailMessage

from app.secrets.schemas import SmtpCredentialsPayload


@contextmanager
def smtp_connection(
    payload: SmtpCredentialsPayload, *, timeout: int = 10
) -> Iterator[smtplib.SMTP]:
    """Connexion authentifiée (SMTPS sur 465, sinon STARTTLS). Lève `smtplib.SMTPException`/
    `OSError` ; l'appelant a déjà vérifié `smtp_tls_violation(payload)` (refus explicite,
    jamais de bascule silencieuse)."""
    ctx = ssl.create_default_context()
    server_cm: smtplib.SMTP
    if payload.useTls and payload.port == 465:
        server_cm = smtplib.SMTP_SSL(payload.host, payload.port, timeout=timeout, context=ctx)
    else:
        server_cm = smtplib.SMTP(payload.host, payload.port, timeout=timeout)
    with server_cm as smtp:
        if payload.useTls and payload.port != 465:
            smtp.starttls(context=ctx)
        smtp.login(payload.username, payload.password)
        yield smtp


def send_smtp_message(
    payload: SmtpCredentialsPayload, message: EmailMessage, *, timeout: int = 10
) -> None:
    with smtp_connection(payload, timeout=timeout) as smtp:
        smtp.send_message(message)
