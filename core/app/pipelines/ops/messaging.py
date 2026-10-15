# SPDX-License-Identifier: Apache-2.0
"""Module de voie E — messagerie & notification.
Plan : docs/superpowers/plans/2026-10-15-fme-fermeture-108-planned.md.

Writers (un message par ligne, plafonné) : `writer.email`, `writer.slack`, `writer.trello`,
`writer.servicebus`, `writer.azurequeue`, `writer.sns`, `writer.kinesis`, `writer.rabbitmq`.
Readers (lecture BORNÉE et NON DESTRUCTIVE d'un lot dans le run, pas un démon) :
`reader.azurequeue`, `reader.kinesis`. Transform : `transform.mcpCall`.

Règles communes (revues des voies A-D) :
- Un writer a un effet de bord irréversible : jamais d'aperçu (`preview_pipeline` refuse un
  nœud writer) ; `transform.mcpCall` n'appelle RIEN en aperçu (colonnes NULL, statut
  `skipped_preview`). L'audit est commité AVANT l'envoi dans une session courte SÉPARÉE
  (commiter la session du run casserait sa transaction).
- Livraison au moins une fois : un run repris/rejoué renvoie les messages déjà partis (aucun
  point de reprise par message). Le dédoublonnage est délégué au broker quand il existe
  (`messageIdColumn` Service Bus/RabbitMQ, `deduplicationIdColumn` SNS FIFO) : les
  identifiants viennent des données, donc sont identiques d'un rejeu à l'autre.
- Annulation (`should_cancel`) vérifiée avant chaque message ; plafond de messages, d'octets de
  réponse, débit (`ratePerSecond`) ; échec = le nœud échoue en disant combien sont partis.
- Réseau : secret du coffre via l'identité de l'utilisateur du run, dont le `baseUrl` doit
  COUVRIR l'URL appelée (REV-294) ; session `requests` gardée (SSRF + épinglage DNS), redirections
  désactivées (jamais d'en-tête d'authentification suivi vers un autre hôte). AWS : signature
  SigV4 (botocore) envoyée par cette même session — pas de client boto3 qui ferait sa propre
  connexion hors garde. AMQP : connexion épinglée sur l'IP validée, TLS obligatoire.
- Masquage GAP-22 : les colonnes masquées sont retirées par les readers amont (`reader.collection`
  → `hide_sensitive_columns`) ; ces ops ne lisent que des colonnes de la vue d'entrée (les
  colonnes géométrie ne sont jamais envoyées).
- Pas de nouveau kind de secret : SMTP → `smtp` ; Slack/Azure/MCP → `bearer_token`/`api_key` ;
  Trello et AWS (clé d'accès/secret) → `basic_auth` lié à l'hôte par `baseUrl` ; RabbitMQ →
  `basic_auth` dont `baseUrl` (`https://hôte:port`) désigne l'hôte AMQP.

Ne jamais importer contracts/runtime/registries au niveau module (cycle d'import)."""

import base64
import contextlib
import json
import re
import smtplib
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from email.message import EmailMessage
from typing import Any
from urllib.parse import quote, urlsplit
from xml.etree import ElementTree

import pandas as pd
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.pipelines.errors import PipelineCancelledError, PipelineRuntimeError
from app.pipelines.ops.operation_contract import OperationContract
from app.sql_ident import quote_ident_duckdb as _qi

CONTRACTS: list[OperationContract] = []
READERS: dict[str, Callable] = {}
WRITERS: dict[str, Callable] = {}

_MAX_RESPONSE_BYTES = 10 * 1024 * 1024
_MAX_MESSAGE_BYTES = 256 * 1024
_HTTP_TIMEOUT = (10, 30)


# --------------------------------------------------------------------------- briques communes


class _WriterParams(BaseModel):
    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    maxMessages: int = Field(1000, ge=1, le=10000, description="Plafond de messages par run")
    payloadColumns: list[str] | None = Field(
        None,
        max_length=200,
        description="Colonnes du message JSON (défaut : toutes sauf géométrie)",
    )
    ratePerSecond: float = Field(10, gt=0, le=1000, description="Débit maximal (messages/s)")

    def extra_columns(self) -> list[str]:
        """Colonnes lues en plus du corps (destinataire, identifiant…)."""
        return []

    def needed_columns(self) -> list[str]:
        return [*(self.payloadColumns or []), *self.extra_columns()]

    def select_columns(self) -> list[str] | None:
        return None if self.payloadColumns is None else list(dict.fromkeys(self.needed_columns()))


def _secret(session, tenant_id, user, op: str, name: str, kinds: tuple[str, ...]):
    from app.pipelines.connector_runtime import PostgresSecretResolver

    try:
        payload = PostgresSecretResolver(session, tenant_id, user).get(name)
    except KeyError:
        raise PipelineRuntimeError(f"{op}: secret '{name}' not found") from None
    if payload.kind not in kinds:
        raise PipelineRuntimeError(
            f"{op}: secret has kind '{payload.kind}', expected {' or '.join(kinds)}"
        )
    return payload


def _audit(session, *, tenant_id: str, user, op: str, obj: str, payload: dict) -> None:
    """Audit commité AVANT l'effet, dans une session courte séparée (cf. dbio)."""
    with Session(session.get_bind()) as audit_session:
        write_audit(
            audit_session,
            tenant_id=tenant_id,
            actor_id=user.id,
            actor_kind="user",
            action="pipeline.external_write",
            object_type="connector_secret",
            object_id=obj,
            payload={"op": op, **payload},
        )
        audit_session.commit()


def _fetch_rows(
    conn, view: str, limit: int, op: str, needed: list[str], only: list[str] | None = None
) -> list[dict]:
    desc = conn.execute(f"SELECT * FROM {_qi(view)} LIMIT 0").description
    types = {d[0]: d[1] for d in desc}
    if missing := [c for c in needed if c not in types]:
        raise PipelineRuntimeError(f"{op}: column(s) not found in input: {missing}")
    keep = [c for c in (only or types) if c in types and types[c].id != "geometry"]
    if not keep:
        raise PipelineRuntimeError(f"{op}: no sendable (non-geometry) column in input")
    cur = conn.execute(
        f"SELECT {', '.join(_qi(c) for c in keep)} FROM {_qi(view)} LIMIT {limit + 1}"
    )
    rows = [dict(zip(keep, r, strict=True)) for r in cur.fetchall()]
    if len(rows) > limit:
        raise PipelineRuntimeError(f"{op}: plafond de {limit} messages dépassé")
    return rows


def _row_json(row: dict, columns: list[str] | None = None) -> str:
    data = {k: row[k] for k in (columns or row)}
    body = json.dumps(data, default=str, ensure_ascii=False, separators=(",", ":"))
    if len(body.encode()) > _MAX_MESSAGE_BYTES:
        raise PipelineRuntimeError("message larger than the 256 KiB cap")
    return body


def _text(row: dict, column: str) -> str:
    v = row.get(column)
    if v is None:
        raise PipelineRuntimeError(f"column '{column}' is NULL")
    return str(v)


def _run_writer(
    op: str,
    model: type[_WriterParams],
    kinds: tuple[str, ...],
    open_sender: Callable[[Any, Any], Any],
    session,
    conn,
    *,
    node,
    view_by_node: dict,
    tenant_id: str,
    user,
    should_cancel: Callable[[], bool] | None = None,
    **_extra: Any,
):
    from app.pipelines.runtime import NodeStat

    p = model.model_validate(node.params)
    payload = _secret(session, tenant_id, user, op, p.secretName, kinds)
    rows = _fetch_rows(
        conn,
        view_by_node[node.id],
        p.maxMessages,
        op,
        p.needed_columns(),
        only=p.select_columns(),
    )
    if not rows:
        return NodeStat(node.id, op, 0, {"sent": 0})
    sender_cm = open_sender(p, payload)  # valide portée du secret/egress AVANT l'audit
    with sender_cm as send:
        _audit(
            session,
            tenant_id=tenant_id,
            user=user,
            op=op,
            obj=p.secretName,
            payload={"messages": len(rows)},
        )
        sent = 0
        for i, row in enumerate(rows):
            if should_cancel is not None and should_cancel():
                raise PipelineCancelledError(f"{op}: cancelled after {sent} message(s) sent")
            try:
                send(row, i)
            except (PipelineRuntimeError, OSError, smtplib.SMTPException, ValueError) as exc:
                raise PipelineRuntimeError(
                    f"{op}: message {i + 1}/{len(rows)} failed after {sent} sent "
                    f"(a rerun resends them, at-least-once): {exc}"
                ) from exc
            sent += 1
            if sent < len(rows):
                time.sleep(1.0 / p.ratePerSecond)
    return NodeStat(node.id, op, sent, {"sent": sent})


def _apply_auth(op: str, payload, headers: dict, params: dict) -> None:
    if payload.kind == "bearer_token":
        headers["Authorization"] = f"Bearer {payload.token}"
    elif payload.kind == "api_key":
        if payload.location == "header":
            headers[payload.key] = payload.value
        else:
            params[payload.key] = payload.value


def _redact(text: str, payload) -> str:
    """Expurge les valeurs secrètes (jeton, clé d'API, mot de passe) d'un message d'erreur."""
    for attr in ("token", "value", "password"):
        v = getattr(payload, attr, None)
        if v and len(v) >= 4:
            text = text.replace(v, "***").replace(quote(v, safe=""), "***")
    return text


def _http(
    op: str,
    payload,
    method: str,
    url: str,
    *,
    headers: dict | None = None,
    params: dict | None = None,
    body: bytes | None = None,
    auth: bool = True,
    max_bytes: int = _MAX_RESPONSE_BYTES,
    deadline_s: float = 60.0,
):
    """Appel REST sous la portée du secret, session gardée, sans redirection, réponse bornée.
    Retourne (statut, corps, en-têtes)."""
    from app.pipelines.connector_runtime import _url_within_scope
    from app.pipelines.egress import build_guarded_session

    scope = getattr(payload, "baseUrl", None)
    if not scope or not _url_within_scope(scope, url):
        raise PipelineRuntimeError(
            f"{op}: secret baseUrl must cover '{url}' (set it on the secret)"
        )
    h = dict(headers or {})
    q = dict(params or {})
    if auth:
        _apply_auth(op, payload, h, q)
    sess = build_guarded_session()
    try:
        resp = sess.request(
            method,
            url,
            headers=h,
            params=q or None,
            data=body,
            stream=True,
            allow_redirects=False,
            timeout=_HTTP_TIMEOUT,
        )
        try:
            buf = bytearray()
            deadline = time.monotonic() + deadline_s
            for chunk in resp.iter_content(65536):
                if time.monotonic() > deadline:
                    raise PipelineRuntimeError(f"{op}: response not completed within {deadline_s}s")
                buf += chunk
                if len(buf) > max_bytes:
                    raise PipelineRuntimeError(f"{op}: response larger than the byte cap")
            return resp.status_code, bytes(buf), resp.headers
        finally:
            resp.close()
    except PipelineRuntimeError:
        raise
    except Exception as exc:  # EgressBlockedError, requests.RequestException
        raise PipelineRuntimeError(
            _redact(f"{op}: request failed: {type(exc).__name__}: {exc}", payload)
        ) from None
    finally:
        sess.close()


def _expect(op: str, status: int, body: bytes, ok: tuple[int, ...], payload=None) -> None:
    if status not in ok:
        # le corps d'erreur du fournisseur peut citer des données : tronqué, jamais les secrets
        raise PipelineRuntimeError(
            _redact(
                f"{op}: provider answered HTTP {status}: {body[:200].decode(errors='replace')}",
                payload,
            )
        )


def _materialize(conn, view_name: str, df: pd.DataFrame) -> None:
    conn.register("_msg_frame", df)
    try:
        conn.execute(f"CREATE TEMP TABLE {_qi(view_name)} AS SELECT * FROM _msg_frame")
    finally:
        conn.unregister("_msg_frame")


def _https_origin(v: str) -> str:
    parts = urlsplit(v)
    if (
        parts.scheme != "https"
        or not parts.hostname
        or parts.username
        or parts.query
        or parts.fragment
        or parts.path.strip("/")
    ):
        raise ValueError("expected 'https://<host>[:port]' (no path, credentials or query)")
    return v.rstrip("/")


def _register_writer(op: str, model, kinds, open_sender, *, engine: str, license_: str) -> None:
    def writer(session, conn, **kw):
        return _run_writer(op, model, kinds, open_sender, session, conn, **kw)

    WRITERS[op] = writer
    CONTRACTS.append(
        OperationContract(
            op=op,
            kind="writer",
            params_schema=model,
            engine=engine,
            engine_license=license_,
        )
    )


# --------------------------------------------------------------------------- Emailer

_EMAIL_RE = re.compile(r"^[^@\s<>,;\"']+@[^@\s<>,;\"']+\.[^@\s<>,;\"']+$")


class WriterEmailParams(_WriterParams):
    """Envoie un e-mail par ligne via un secret SMTP du coffre (TLS obligatoire hors
    localhost) : le destinataire vient de `toColumn`, le corps de `bodyColumn` (sinon la ligne
    en JSON). `allowedRecipientDomains` borne les domaines destinataires. Livraison au moins
    une fois : un rejeu renvoie les e-mails déjà partis. Aucun aperçu."""

    toColumn: str = Field(..., min_length=1)
    subject: str = Field(..., min_length=1, max_length=200)
    bodyColumn: str | None = None
    allowedRecipientDomains: list[str] | None = Field(None, max_length=50)
    maxMessages: int = Field(100, ge=1, le=1000, description="Plafond de messages par run")
    ratePerSecond: float = Field(5, gt=0, le=50)

    def extra_columns(self) -> list[str]:
        return [self.toColumn, *([self.bodyColumn] if self.bodyColumn else [])]

    @model_validator(mode="after")
    def _single_line_subject(self):
        if "\n" in self.subject or "\r" in self.subject:
            raise ValueError("subject: une seule ligne")
        return self


def _open_email(p: WriterEmailParams, payload):
    from app.secrets.schemas import smtp_tls_violation
    from app.secrets.smtp_send import smtp_connection

    if violation := smtp_tls_violation(payload):
        raise PipelineRuntimeError(f"writer.email: secret '{p.secretName}' : {violation}")
    domains = {d.lower() for d in (p.allowedRecipientDomains or [])}
    from app.pipelines import egress
    from app.secrets.schemas import SMTP_LOCAL_HOSTS

    host = payload.host.lower()
    if host not in SMTP_LOCAL_HOSTS:  # même exemption que smtp_tls_violation (relais de dev)
        try:  # ponytail: pas d'épinglage IP (smtplib/STARTTLS lie le nom) ; résidu TOCTOU assumé
            egress.assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")
        except egress.EgressBlockedError as exc:
            raise PipelineRuntimeError(f"writer.email: egress blocked: {exc}") from exc

    @contextmanager
    def cm() -> Iterator[Callable]:
        try:
            with smtp_connection(payload) as smtp:

                def send(row: dict, i: int) -> None:
                    to = _text(row, p.toColumn).strip()
                    if not _EMAIL_RE.match(to):
                        raise PipelineRuntimeError(f"invalid recipient address on row {i + 1}")
                    if domains and to.rsplit("@", 1)[1].lower() not in domains:
                        raise PipelineRuntimeError(
                            f"recipient domain not allowed on row {i + 1} (allowedRecipientDomains)"
                        )
                    msg = EmailMessage()
                    msg["Subject"] = p.subject
                    msg["From"] = payload.fromAddress
                    msg["To"] = to
                    msg.set_content(
                        _text(row, p.bodyColumn)
                        if p.bodyColumn
                        else _row_json(row, p.payloadColumns)
                    )
                    smtp.send_message(msg)

                yield send
        except (smtplib.SMTPException, OSError) as exc:
            raise PipelineRuntimeError(f"writer.email: SMTP failure: {exc}") from exc

    return cm()


_register_writer(
    "writer.email",
    WriterEmailParams,
    ("smtp",),
    _open_email,
    engine="python",
    license_="PSF-2.0 (smtplib, stdlib) ; SMTP partagé avec app.alerts via app.secrets.smtp_send",
)


# --------------------------------------------------------------------------- Slack

_SLACK_URL = "https://slack.com/api/chat.postMessage"


class WriterSlackParams(_WriterParams):
    """Poste un message Slack par ligne (`chat.postMessage`) dans `channel`, texte = colonne
    `textColumn`. `secretName` : secret bearer_token (jeton bot `xoxb-…`) dont le baseUrl couvre
    `https://slack.com/api/`. Les caractères `& < >` du texte sont échappés (pas de mention
    `<!channel>` injectée par les données). Aucun aperçu."""

    channel: str = Field(..., min_length=1, max_length=80)
    textColumn: str = Field(..., min_length=1)
    maxMessages: int = Field(100, ge=1, le=1000, description="Plafond de messages par run")
    ratePerSecond: float = Field(1, gt=0, le=5)

    def extra_columns(self) -> list[str]:
        return [self.textColumn]


def _slack_escape(s: str) -> str:
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")[:4000]


def _open_slack(p: WriterSlackParams, payload):
    op = "writer.slack"

    def send(row: dict, i: int) -> None:
        body = json.dumps(
            {"channel": p.channel, "text": _slack_escape(_text(row, p.textColumn))}
        ).encode()
        status, resp, headers = _http(
            op,
            payload,
            "POST",
            _SLACK_URL,
            headers={"Content-Type": "application/json; charset=utf-8"},
            body=body,
            max_bytes=1024 * 1024,
        )
        if status == 429:
            raise PipelineRuntimeError(
                f"rate limited by Slack (Retry-After {headers.get('Retry-After', '?')}s)"
            )
        _expect(op, status, resp, (200,), payload)
        try:
            ok = json.loads(resp).get("ok")
            err = json.loads(resp).get("error")
        except ValueError as exc:
            raise PipelineRuntimeError("invalid JSON answer from Slack") from exc
        if not ok:
            raise PipelineRuntimeError(f"Slack error: {err}")

    return contextlib.nullcontext(send)


_register_writer(
    "writer.slack",
    WriterSlackParams,
    ("bearer_token",),
    _open_slack,
    engine="python",
    license_="Apache-2.0 (requests) ; API REST Slack",
)


# --------------------------------------------------------------------------- Trello

_TRELLO_URL = "https://api.trello.com/1/cards"


class WriterTrelloParams(_WriterParams):
    """Crée une carte Trello par ligne dans la liste `listId` (nom = `nameColumn`, description
    optionnelle = `descColumn`). `secretName` : secret basic_auth (identifiant = clé d'API,
    mot de passe = jeton) dont le baseUrl couvre `https://api.trello.com/`. Création seule (pas
    de mise à jour de carte). Livraison au moins une fois : un rejeu recrée les cartes. Aucun
    aperçu."""

    listId: str = Field(..., pattern=r"^[A-Za-z0-9]{8,64}$")
    nameColumn: str = Field(..., min_length=1)
    descColumn: str | None = None
    maxMessages: int = Field(100, ge=1, le=1000, description="Plafond de messages par run")
    ratePerSecond: float = Field(5, gt=0, le=10)

    def extra_columns(self) -> list[str]:
        return [self.nameColumn, *([self.descColumn] if self.descColumn else [])]


def _open_trello(p: WriterTrelloParams, payload):
    op = "writer.trello"
    auth = f'OAuth oauth_consumer_key="{payload.username}", oauth_token="{payload.password}"'

    def send(row: dict, i: int) -> None:
        card = {"idList": p.listId, "name": _text(row, p.nameColumn)[:16384]}
        if p.descColumn and row.get(p.descColumn) is not None:
            card["desc"] = str(row[p.descColumn])[:16384]
        status, resp, _ = _http(
            op,
            payload,
            "POST",
            _TRELLO_URL,
            headers={"Authorization": auth, "Content-Type": "application/json"},
            body=json.dumps(card).encode(),
            auth=False,
            max_bytes=1024 * 1024,
        )
        _expect(op, status, resp, (200,), payload)

    return contextlib.nullcontext(send)


_register_writer(
    "writer.trello",
    WriterTrelloParams,
    ("basic_auth",),
    _open_trello,
    engine="python",
    license_="Apache-2.0 (requests) ; API REST Trello",
)


# --------------------------------------------------------------------------- Azure Service Bus


class WriterServiceBusParams(_WriterParams):
    """Envoie un message Azure Service Bus par ligne (API REST, corps = ligne JSON) dans la file
    ou le topic `entity` de `namespaceUrl` (`https://<ns>.servicebus.windows.net`). `secretName` :
    secret bearer_token (jeton Entra ID) ou api_key en-tête `Authorization` (jeton SAS), baseUrl
    = `namespaceUrl`. `messageIdColumn` (optionnel) fixe le MessageId pour le dédoublonnage du
    broker lors d'un rejeu. Écriture seule (la réception destructive n'est pas exposée). Aucun
    aperçu."""

    namespaceUrl: str
    entity: str = Field(..., pattern=r"^[A-Za-z0-9._/-]{1,260}$")
    messageIdColumn: str | None = None
    ratePerSecond: float = Field(20, gt=0, le=200)

    @model_validator(mode="after")
    def _origin(self):
        self.namespaceUrl = _https_origin(self.namespaceUrl)
        if ".." in self.entity.split("/"):
            raise ValueError("entity: segment '..' interdit")
        return self

    def extra_columns(self) -> list[str]:
        return [self.messageIdColumn] if self.messageIdColumn else []


def _open_servicebus(p: WriterServiceBusParams, payload):
    op = "writer.servicebus"
    url = f"{p.namespaceUrl}/{quote(p.entity, safe='/')}/messages"

    def send(row: dict, i: int) -> None:
        headers = {"Content-Type": "application/json"}
        if p.messageIdColumn:
            headers["BrokerProperties"] = json.dumps(
                {"MessageId": _text(row, p.messageIdColumn)[:128]}
            )
        status, resp, _ = _http(
            op,
            payload,
            "POST",
            url,
            headers=headers,
            body=_row_json(row, p.payloadColumns).encode(),
            max_bytes=1024 * 1024,
        )
        _expect(op, status, resp, (201,), payload)

    return contextlib.nullcontext(send)


_register_writer(
    "writer.servicebus",
    WriterServiceBusParams,
    ("bearer_token", "api_key"),
    _open_servicebus,
    engine="python",
    license_="Apache-2.0 (requests) ; API REST Azure Service Bus",
)


# --------------------------------------------------------------------------- Azure Queue Storage

_AZQ_VERSION = "2021-08-06"
_AZQ_MAX_RAW = 48 * 1024  # 64 Kio une fois encodé en base64


def _check_azq_account(v: str) -> str:
    return _https_origin(v)


class WriterAzureQueueParams(_WriterParams):
    """Poste un message Azure Queue Storage par ligne (corps = ligne JSON, base64) dans la file
    `queue` du compte `accountUrl` (`https://<compte>.queue.core.windows.net`). `secretName` :
    secret bearer_token (jeton Microsoft Entra ID, rôle « Queue Data Message Sender ») dont le
    baseUrl = `accountUrl` ; les jetons SAS (plusieurs paramètres d'URL) ne sont pas pris en
    charge. Aucun aperçu."""

    accountUrl: str
    queue: str = Field(..., pattern=r"^[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]$")
    ratePerSecond: float = Field(20, gt=0, le=200)

    @model_validator(mode="after")
    def _origin(self):
        self.accountUrl = _check_azq_account(self.accountUrl)
        return self


def _open_azurequeue_writer(p: WriterAzureQueueParams, payload):
    op = "writer.azurequeue"
    url = f"{p.accountUrl}/{p.queue}/messages"

    def send(row: dict, i: int) -> None:
        raw = _row_json(row, p.payloadColumns).encode()
        if len(raw) > _AZQ_MAX_RAW:
            raise PipelineRuntimeError("message larger than the 48 KiB Queue Storage cap")
        xml = (
            "<QueueMessage><MessageText>"
            + base64.b64encode(raw).decode()
            + "</MessageText></QueueMessage>"
        )
        status, resp, _ = _http(
            op,
            payload,
            "POST",
            url,
            headers={"x-ms-version": _AZQ_VERSION, "Content-Type": "application/xml"},
            body=xml.encode(),
            max_bytes=1024 * 1024,
        )
        _expect(op, status, resp, (201,), payload)

    return contextlib.nullcontext(send)


_register_writer(
    "writer.azurequeue",
    WriterAzureQueueParams,
    ("bearer_token",),
    _open_azurequeue_writer,
    engine="python",
    license_="Apache-2.0 (requests) ; API REST Azure Queue Storage",
)


class ReaderAzureQueueParams(BaseModel):
    """Lit (sans les consommer ni les masquer : « peek ») les `maxMessages` premiers messages
    d'une file Azure Queue Storage : colonnes message_id, insertion_time, expiration_time,
    dequeue_count, message_text (base64 décodé en UTF-8 quand c'est possible). Lecture non
    destructive : le même lot est relu à chaque exécution tant que la file n'est pas vidée
    par un autre consommateur (au plus 32 messages par appel, limite du service). Même secret
    que `writer.azurequeue` (rôle « Queue Data Message Processor/Reader »)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    accountUrl: str
    queue: str = Field(..., pattern=r"^[a-z0-9](?:[a-z0-9-]{1,61})[a-z0-9]$")
    maxMessages: int = Field(32, ge=1, le=32)

    @model_validator(mode="after")
    def _origin(self):
        self.accountUrl = _check_azq_account(self.accountUrl)
        return self


def _decode_text(b64: str) -> str:
    try:
        return base64.b64decode(b64, validate=True).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return b64


def _parse_queue_xml(body: bytes) -> list[dict]:
    low = body[:4096].lower()
    if b"<!doctype" in low or b"<!entity" in low:
        raise PipelineRuntimeError("reader.azurequeue: DTD/entities refused in XML answer")
    try:
        root = ElementTree.fromstring(body)  # noqa: S314 - DTD refusée ci-dessus
    except ElementTree.ParseError as exc:
        raise PipelineRuntimeError("reader.azurequeue: invalid XML answer") from exc
    out = []
    for m in root.iter("QueueMessage"):

        def g(tag: str, m=m) -> str | None:
            return m.findtext(tag) or None

        out.append(
            {
                "message_id": g("MessageId"),
                "insertion_time": g("InsertionTime"),
                "expiration_time": g("ExpirationTime"),
                "dequeue_count": int(g("DequeueCount") or 0),
                "message_text": _decode_text(g("MessageText") or ""),
            }
        )
    return out


def read_azurequeue(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.azurequeue"
    p = ReaderAzureQueueParams.model_validate(params)
    payload = _secret(session, tenant_id, user, op, p.secretName, ("bearer_token",))
    status, body, _ = _http(
        op,
        payload,
        "GET",
        f"{p.accountUrl}/{p.queue}/messages",
        headers={"x-ms-version": _AZQ_VERSION},
        params={"peekonly": "true", "numofmessages": str(p.maxMessages)},
    )
    _expect(op, status, body, (200,), payload)
    rows = _parse_queue_xml(body) if body.strip() else []
    cols = ["message_id", "insertion_time", "expiration_time", "dequeue_count", "message_text"]
    _materialize(conn, view_name, pd.DataFrame(rows, columns=cols))
    return 4326


READERS["reader.azurequeue"] = read_azurequeue
CONTRACTS.append(
    OperationContract(
        op="reader.azurequeue",
        kind="reader",
        params_schema=ReaderAzureQueueParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) ; API REST Azure Queue Storage via requests (Apache-2.0)",
    )
)


# --------------------------------------------------------------------------- AWS (SigV4)

_REGION_RE = r"^[a-z]{2}(?:-[a-z]+)+-\d$"


def _aws_call(
    op: str,
    payload,
    *,
    service: str,
    region: str,
    endpoint: str,
    body: bytes,
    content_type: str,
    extra: dict | None = None,
    max_bytes: int = _MAX_RESPONSE_BYTES,
):
    """POST signé SigV4 (botocore.auth) envoyé par la session gardée : le secret basic_auth porte
    la clé d'accès (identifiant) et le secret (mot de passe) ; son baseUrl couvre l'endpoint."""
    from botocore.auth import SigV4Auth
    from botocore.awsrequest import AWSRequest
    from botocore.credentials import Credentials

    url = endpoint.rstrip("/") + "/"
    headers = {"Content-Type": content_type, **(extra or {})}
    req = AWSRequest(method="POST", url=url, data=body, headers=dict(headers))
    SigV4Auth(Credentials(payload.username, payload.password), service, region).add_auth(req)
    signed = {k: str(v) for k, v in req.headers.items()}
    return _http(
        op, payload, "POST", url, headers=signed, body=body, auth=False, max_bytes=max_bytes
    )


def _aws_endpoint(service: str, region: str, custom: str | None) -> str:
    return _https_origin(custom) if custom else f"https://{service}.{region}.amazonaws.com"


class WriterSnsParams(_WriterParams):
    """Publie une notification Amazon SNS par ligne sur `topicArn` (message = colonne
    `messageColumn`, sinon la ligne en JSON). `secretName` : secret basic_auth (identifiant = clé
    d'accès AWS, mot de passe = clé secrète) dont le baseUrl couvre l'endpoint SNS
    (`https://sns.<région>.amazonaws.com` ou `endpointUrl`). Topic FIFO : `messageGroupId` et
    `deduplicationIdColumn` (identifiant stable → pas de doublon lors d'un rejeu). Aucun aperçu."""

    topicArn: str
    region: str = Field(..., pattern=_REGION_RE)
    endpointUrl: str | None = None
    messageColumn: str | None = None
    subject: str | None = Field(None, max_length=100)
    messageGroupId: str | None = Field(None, max_length=128)
    deduplicationIdColumn: str | None = None
    maxMessages: int = Field(1000, ge=1, le=10000, description="Plafond de messages par run")
    ratePerSecond: float = Field(20, gt=0, le=300)

    @model_validator(mode="after")
    def _check(self):
        m = re.match(
            r"^arn:aws[a-z-]*:sns:([a-z0-9-]+):\d{12}:[A-Za-z0-9_.-]{1,256}$", self.topicArn
        )
        if not m or m.group(1) != self.region:
            raise ValueError("topicArn: ARN SNS invalide ou région différente de `region`")
        if self.endpointUrl:
            _https_origin(self.endpointUrl)
        return self

    def extra_columns(self) -> list[str]:
        return [c for c in (self.messageColumn, self.deduplicationIdColumn) if c]


def _open_sns(p: WriterSnsParams, payload):
    op = "writer.sns"
    endpoint = _aws_endpoint("sns", p.region, p.endpointUrl)

    def send(row: dict, i: int) -> None:
        from urllib.parse import urlencode

        msg = _text(row, p.messageColumn) if p.messageColumn else _row_json(row, p.payloadColumns)
        if len(msg.encode()) > _MAX_MESSAGE_BYTES:
            raise PipelineRuntimeError("message larger than the 256 KiB SNS cap")
        form = {
            "Action": "Publish",
            "Version": "2010-03-31",
            "TopicArn": p.topicArn,
            "Message": msg,
        }
        if p.subject:
            form["Subject"] = p.subject
        if p.messageGroupId:
            form["MessageGroupId"] = p.messageGroupId
        if p.deduplicationIdColumn:
            form["MessageDeduplicationId"] = _text(row, p.deduplicationIdColumn)[:128]
        status, resp, _ = _aws_call(
            op,
            payload,
            service="sns",
            region=p.region,
            endpoint=endpoint,
            body=urlencode(form).encode(),
            content_type="application/x-www-form-urlencoded; charset=utf-8",
            max_bytes=1024 * 1024,
        )
        _expect(op, status, resp, (200,), payload)

    return contextlib.nullcontext(send)


_register_writer(
    "writer.sns",
    WriterSnsParams,
    ("basic_auth",),
    _open_sns,
    engine="python",
    license_="Apache-2.0 (botocore SigV4 + requests) ; API Amazon SNS",
)


_KINESIS_CT = "application/x-amz-json-1.1"


def _kinesis(op: str, payload, region: str, endpoint: str, target: str, doc: dict):
    status, resp, _ = _aws_call(
        op,
        payload,
        service="kinesis",
        region=region,
        endpoint=endpoint,
        body=json.dumps(doc).encode(),
        content_type=_KINESIS_CT,
        extra={"X-Amz-Target": f"Kinesis_20131202.{target}"},
    )
    _expect(op, status, resp, (200,), payload)
    try:
        return json.loads(resp or b"{}")
    except ValueError as exc:
        raise PipelineRuntimeError(f"{op}: invalid JSON answer from Kinesis") from exc


class WriterKinesisParams(_WriterParams):
    """Publie un enregistrement Amazon Kinesis Data Streams par ligne (`PutRecord`, données =
    ligne JSON) dans `streamName`. Clé de partition = colonne `partitionKeyColumn` (sinon la
    valeur fixe `partitionKey`). Secret basic_auth (clé d'accès / clé secrète AWS) dont le baseUrl
    couvre `https://kinesis.<région>.amazonaws.com` (ou `endpointUrl`). Livraison au moins une
    fois : un rejeu republie les enregistrements. Aucun aperçu."""

    streamName: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    region: str = Field(..., pattern=_REGION_RE)
    endpointUrl: str | None = None
    partitionKeyColumn: str | None = None
    partitionKey: str = Field("geostudio", min_length=1, max_length=256)
    ratePerSecond: float = Field(50, gt=0, le=1000)

    @model_validator(mode="after")
    def _check(self):
        if self.endpointUrl:
            _https_origin(self.endpointUrl)
        return self

    def extra_columns(self) -> list[str]:
        return [self.partitionKeyColumn] if self.partitionKeyColumn else []


def _open_kinesis_writer(p: WriterKinesisParams, payload):
    op = "writer.kinesis"
    endpoint = _aws_endpoint("kinesis", p.region, p.endpointUrl)

    def send(row: dict, i: int) -> None:
        key = _text(row, p.partitionKeyColumn)[:256] if p.partitionKeyColumn else p.partitionKey
        _kinesis(
            op,
            payload,
            p.region,
            endpoint,
            "PutRecord",
            {
                "StreamName": p.streamName,
                "PartitionKey": key,
                "Data": base64.b64encode(_row_json(row, p.payloadColumns).encode()).decode(),
            },
        )

    return contextlib.nullcontext(send)


_register_writer(
    "writer.kinesis",
    WriterKinesisParams,
    ("basic_auth",),
    _open_kinesis_writer,
    engine="python",
    license_="Apache-2.0 (botocore SigV4 + requests) ; API Amazon Kinesis",
)


class ReaderKinesisParams(BaseModel):
    """Lit un lot BORNÉ d'enregistrements d'un flux Amazon Kinesis (jusqu'à `maxRecords`, ou
    `maxSeconds` d'attente) sur les `maxShards` premiers shards : colonnes shard_id,
    sequence_number, partition_key, arrival_time, data (UTF-8). `iteratorType` : TRIM_HORIZON
    (depuis le plus ancien), LATEST (rien de nouveau sans écriture concurrente) ou AT_TIMESTAMP
    (`timestamp`, epoch en secondes). Lecture sans effet de bord (pas de checkpoint) : chaque
    exécution relit la fenêtre demandée. Même secret que `writer.kinesis`."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    streamName: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    region: str = Field(..., pattern=_REGION_RE)
    endpointUrl: str | None = None
    iteratorType: str = Field("TRIM_HORIZON", pattern=r"^(TRIM_HORIZON|LATEST|AT_TIMESTAMP)$")
    timestamp: float | None = Field(None, ge=0)
    maxRecords: int = Field(1000, ge=1, le=10000)
    maxShards: int = Field(5, ge=1, le=10)
    maxSeconds: int = Field(10, ge=1, le=60)

    @model_validator(mode="after")
    def _check(self):
        if self.iteratorType == "AT_TIMESTAMP" and self.timestamp is None:
            raise ValueError("timestamp requis avec AT_TIMESTAMP")
        if self.endpointUrl:
            _https_origin(self.endpointUrl)
        return self


def read_kinesis(conn, *, session, tenant_id, node_id, params, view_name, user, base_uri) -> int:
    op = "reader.kinesis"
    p = ReaderKinesisParams.model_validate(params)
    payload = _secret(session, tenant_id, user, op, p.secretName, ("basic_auth",))
    endpoint = _aws_endpoint("kinesis", p.region, p.endpointUrl)
    k = lambda target, doc: _kinesis(op, payload, p.region, endpoint, target, doc)  # noqa: E731
    shards = k("ListShards", {"StreamName": p.streamName, "MaxResults": p.maxShards}).get(
        "Shards", []
    )[: p.maxShards]
    deadline = time.monotonic() + p.maxSeconds
    rows: list[dict] = []
    for shard in shards:
        sid = shard["ShardId"]
        req = {"StreamName": p.streamName, "ShardId": sid, "ShardIteratorType": p.iteratorType}
        if p.iteratorType == "AT_TIMESTAMP":
            req["Timestamp"] = p.timestamp
        it = k("GetShardIterator", req).get("ShardIterator")
        while it and len(rows) < p.maxRecords:
            out = k(
                "GetRecords", {"ShardIterator": it, "Limit": min(1000, p.maxRecords - len(rows))}
            )
            for r in out.get("Records", []):
                rows.append(
                    {
                        "shard_id": sid,
                        "sequence_number": r.get("SequenceNumber"),
                        "partition_key": r.get("PartitionKey"),
                        "arrival_time": r.get("ApproximateArrivalTimestamp"),
                        "data": base64.b64decode(r.get("Data", "")).decode("utf-8", "replace"),
                    }
                )
            it = out.get("NextShardIterator")
            if not out.get("Records") and not out.get("MillisBehindLatest"):
                break  # fin de shard / rien de plus
            if time.monotonic() > deadline:
                break
            time.sleep(0.25)  # 5 GetRecords/s/shard
        if len(rows) >= p.maxRecords or time.monotonic() > deadline:
            break
    cols = ["shard_id", "sequence_number", "partition_key", "arrival_time", "data"]
    _materialize(conn, view_name, pd.DataFrame(rows[: p.maxRecords], columns=cols))
    return 4326


READERS["reader.kinesis"] = read_kinesis
CONTRACTS.append(
    OperationContract(
        op="reader.kinesis",
        kind="reader",
        params_schema=ReaderKinesisParams,
        engine="duckdb",
        engine_license="MIT (DuckDB) ; API Amazon Kinesis via botocore SigV4 (Apache-2.0)",
    )
)


# --------------------------------------------------------------------------- RabbitMQ (AMQP)


def _amqp_connection(op: str, payload, *, host: str, port: int, vhost: str):
    """Connexion AMQPS (TLS obligatoire, certificat vérifié) épinglée sur l'IP validée par la garde
    d'egress. `baseUrl` du secret = `https://hôte:port` : désigne l'hôte AMQP auquel il est lié."""
    import ssl

    import pika

    from app.pipelines import egress

    scope = urlsplit(getattr(payload, "baseUrl", None) or "")
    if (scope.hostname or "").lower() != host.lower() or (scope.port or 5671) != port:
        raise PipelineRuntimeError(
            f"{op}: secret baseUrl must be 'https://{host}:{port}' (set it on the secret)"
        )
    try:
        ip = egress.assert_egress_allowed(f"http://[{host}]" if ":" in host else f"http://{host}")
    except egress.EgressBlockedError as exc:
        raise PipelineRuntimeError(f"{op}: egress blocked: {exc}") from exc
    params = pika.ConnectionParameters(
        host=str(ip) if ip else host,
        port=port,
        virtual_host=vhost,
        credentials=pika.PlainCredentials(payload.username, payload.password),
        ssl_options=pika.SSLOptions(ssl.create_default_context(), server_hostname=host),
        socket_timeout=10,
        blocked_connection_timeout=30,
        connection_attempts=1,
        heartbeat=30,
    )
    try:
        return pika.BlockingConnection(params)
    except Exception as exc:  # AMQPError, OSError, ssl.SSLError
        raise PipelineRuntimeError(f"{op}: AMQP connection failed: {type(exc).__name__}") from exc


class _AmqpBase(BaseModel):
    host: str = Field(..., pattern=r"^[A-Za-z0-9.-]{1,253}$")
    port: int = Field(5671, ge=1, le=65535)
    vhost: str = Field("/", min_length=1, max_length=200)


class WriterRabbitMqParams(_WriterParams, _AmqpBase):
    """Publie un message RabbitMQ (AMQP 0-9-1 sur TLS) par ligne (corps = ligne JSON, persistant,
    confirmation de l'éditeur, `mandatory` : un message non routé fait échouer le nœud) vers
    `exchange`/`routingKey`. Secret basic_auth dont le baseUrl est `https://<hôte>:<port>`.
    `messageIdColumn` renseigne la propriété AMQP message_id (dédoublonnage côté consommateur lors
    d'un rejeu). Aucun aperçu."""

    exchange: str = Field("", max_length=255)
    routingKey: str = Field(..., min_length=1, max_length=255)
    messageIdColumn: str | None = None
    ratePerSecond: float = Field(100, gt=0, le=1000)

    def extra_columns(self) -> list[str]:
        return [self.messageIdColumn] if self.messageIdColumn else []


def _open_rabbitmq_writer(p: WriterRabbitMqParams, payload):
    import pika

    op = "writer.rabbitmq"

    @contextmanager
    def cm() -> Iterator[Callable]:
        conn = _amqp_connection(op, payload, host=p.host, port=p.port, vhost=p.vhost)
        try:
            ch = conn.channel()
            ch.confirm_delivery()

            def send(row: dict, i: int) -> None:
                props = pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=_text(row, p.messageIdColumn)[:255] if p.messageIdColumn else None,
                )
                try:
                    ch.basic_publish(
                        p.exchange,
                        p.routingKey,
                        _row_json(row, p.payloadColumns).encode(),
                        props,
                        mandatory=True,
                    )
                except pika.exceptions.AMQPError as exc:
                    raise PipelineRuntimeError(f"publish refused: {type(exc).__name__}") from exc

            yield send
        finally:
            with contextlib.suppress(Exception):
                conn.close()

    return cm()


_register_writer(
    "writer.rabbitmq",
    WriterRabbitMqParams,
    ("basic_auth",),
    _open_rabbitmq_writer,
    engine="python",
    license_="BSD-3-Clause (pika, client AMQP)",
)


# --------------------------------------------------------------------------- MCPCaller

_MCP_PROTOCOL = "2025-03-26"
_ARG_NAME_RE = r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$"


class TransformMcpCallParams(BaseModel):
    """Appelle l'outil `tool` d'un serveur MCP externe (`url`, transport HTTP streamable) une fois
    par ligne et ajoute `mcp_result` (texte de la réponse), `mcp_status` (ok, tool_error, error,
    skipped_preview) et `mcp_error`. Les arguments viennent de `argumentColumns` (nom d'argument →
    colonne) et `staticArguments`. Seul l'outil nommé ici peut être appelé (liste d'autorisation
    d'un seul outil) ; `secretName` : secret bearer_token ou api_key dont le baseUrl couvre `url`,
    accédé avec les permissions de l'utilisateur du run. Un appel d'outil peut avoir un effet de
    bord : l'aperçu n'appelle rien (statut skipped_preview). Un appel déjà parti n'est pas annulé
    par un échec ultérieur (au moins une fois)."""

    secretName: str = Field(..., json_schema_extra={"format": "secret-name"})
    url: str = Field(..., min_length=8, max_length=2000)
    tool: str = Field(..., pattern=r"^[A-Za-z0-9_.-]{1,128}$")
    argumentColumns: dict[str, str] = Field(default_factory=dict, max_length=50)
    staticArguments: dict[str, str | int | float | bool] = Field(default_factory=dict)
    maxCalls: int = Field(100, ge=1, le=500, description="Plafond d'appels par run")
    ratePerSecond: float = Field(5, gt=0, le=50)

    @model_validator(mode="after")
    def _check(self):
        parts = urlsplit(self.url)
        if parts.scheme not in ("http", "https") or not parts.hostname or parts.username:
            raise ValueError("url: http(s) sans identifiants attendu")
        for name in (*self.argumentColumns, *self.staticArguments):
            if not re.match(_ARG_NAME_RE, name):
                raise ValueError(f"nom d'argument invalide : {name!r}")
        if set(self.argumentColumns) & set(self.staticArguments):
            raise ValueError("argument défini à la fois en colonne et en valeur fixe")
        return self


def _mcp_output_srid(
    params: dict, *, op: str, input_srid: int, join_srid: int | None = None
) -> int:
    return input_srid


def _mcp_message(body: bytes, headers, want_id: int | None) -> dict | None:
    """Réponse JSON-RPC unique, ou flux SSE dont on retient le message portant `id`."""
    ctype = (headers.get("Content-Type") or "").lower()
    if "text/event-stream" in ctype:
        found = None
        for line in body.decode("utf-8", "replace").splitlines():
            if line.startswith("data:"):
                try:
                    msg = json.loads(line[5:].strip())
                except ValueError:
                    continue
                if isinstance(msg, dict) and msg.get("id") == want_id:
                    found = msg
        return found
    if not body.strip():
        return None
    try:
        msg = json.loads(body)
    except ValueError as exc:
        raise PipelineRuntimeError("transform.mcpCall: invalid JSON from MCP server") from exc
    return msg if isinstance(msg, dict) else None


def _mcp_rpc(
    payload, p: TransformMcpCallParams, sid: str | None, msg: dict, version: str = _MCP_PROTOCOL
):
    op = "transform.mcpCall"
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
        "MCP-Protocol-Version": version,
    }
    if sid:
        headers["Mcp-Session-Id"] = sid
    status, body, resp_headers = _http(
        op, payload, "POST", p.url, headers=headers, body=json.dumps(msg).encode()
    )
    if status not in (200, 202):
        raise PipelineRuntimeError(f"{op}: MCP server answered HTTP {status}")
    return _mcp_message(body, resp_headers, msg.get("id")), resp_headers.get("Mcp-Session-Id")


def execute_mcp_call(
    conn,
    *,
    input_view: str,
    view_name: str,
    params: dict,
    secret_resolver=None,
    preview: bool = False,
    input_srid: int | None = None,
) -> None:
    op = "transform.mcpCall"
    p = TransformMcpCallParams.model_validate(params)
    desc = conn.execute(f"SELECT * FROM {_qi(input_view)} LIMIT 0").description
    cols = [d[0] for d in desc]
    if missing := [c for c in p.argumentColumns.values() if c not in cols]:
        raise PipelineRuntimeError(f"{op}: column(s) not found in input: {missing}")
    if clash := [c for c in ("mcp_result", "mcp_status", "mcp_error") if c in cols]:
        raise PipelineRuntimeError(f"{op}: output column(s) already exist in input: {clash}")
    geom = {d[0] for d in desc if d[1].id == "geometry"}
    if geom & set(p.argumentColumns.values()):
        raise PipelineRuntimeError(f"{op}: geometry columns cannot be sent as arguments")
    arg_cols = list(dict.fromkeys(p.argumentColumns.values()))
    sel = "".join(f", {_qi(c)}" for c in arg_cols)
    rows = conn.execute(
        f"SELECT row_number() OVER () AS rn{sel} FROM {_qi(input_view)} LIMIT {p.maxCalls + 1}"
    ).fetchall()
    if len(rows) > p.maxCalls:
        raise PipelineRuntimeError(f"{op}: plafond de {p.maxCalls} appels dépassé")
    results: list[dict] = []
    if preview:  # effet de bord possible : jamais d'appel en aperçu
        results = [
            {"rn": r[0], "mcp_result": None, "mcp_status": "skipped_preview", "mcp_error": None}
            for r in rows
        ]
    elif rows:
        session = getattr(secret_resolver, "session", None)
        user = getattr(secret_resolver, "user", None)
        if session is None or user is None or secret_resolver is None:
            raise PipelineRuntimeError(f"{op}: secret resolver unavailable")
        try:
            payload = secret_resolver.get(p.secretName)
        except KeyError:
            raise PipelineRuntimeError(f"{op}: secret '{p.secretName}' not found") from None
        if payload.kind not in ("bearer_token", "api_key"):
            raise PipelineRuntimeError(
                f"{op}: secret has kind '{payload.kind}', expected bearer_token or api_key"
            )
        _audit(
            session,
            tenant_id=user.tenant_id,
            user=user,
            op=op,
            obj=p.secretName,
            payload={"url": p.url, "tool": p.tool, "calls": len(rows)},
        )
        init, sid = _mcp_rpc(
            payload,
            p,
            None,
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": _MCP_PROTOCOL,
                    "capabilities": {},
                    "clientInfo": {"name": "geostudio-pipeline", "version": "1"},
                },
            },
        )
        if init is None or "result" not in init:
            raise PipelineRuntimeError(f"{op}: MCP initialize failed")
        version = str((init["result"] or {}).get("protocolVersion") or _MCP_PROTOCOL)
        _mcp_rpc(
            payload, p, sid, {"jsonrpc": "2.0", "method": "notifications/initialized"}, version
        )
        for n, r in enumerate(rows):
            args = dict(p.staticArguments)
            for arg, col in p.argumentColumns.items():
                args[arg] = r[1 + arg_cols.index(col)]
            res = {"rn": r[0], "mcp_result": None, "mcp_status": "error", "mcp_error": None}
            try:
                out, _ = _mcp_rpc(
                    payload,
                    p,
                    sid,
                    {
                        "jsonrpc": "2.0",
                        "id": 100 + n,
                        "method": "tools/call",
                        "params": {"name": p.tool, "arguments": args},
                    },
                    version,
                )
                if out is None:
                    res["mcp_error"] = "no answer"
                elif "error" in out:
                    res["mcp_error"] = _redact(str(out["error"].get("message", "error")), payload)[
                        :500
                    ]
                else:
                    result = out.get("result") or {}
                    parts = [
                        c.get("text", "")
                        for c in result.get("content", [])
                        if isinstance(c, dict) and c.get("type") == "text"
                    ]
                    res["mcp_result"] = ("\n".join(parts) if parts else json.dumps(result))[:100000]
                    res["mcp_status"] = "tool_error" if result.get("isError") else "ok"
            except PipelineRuntimeError as exc:
                res["mcp_error"] = str(exc)[:500]
            results.append(res)
            time.sleep(1.0 / p.ratePerSecond)
    df = pd.DataFrame(results, columns=["rn", "mcp_result", "mcp_status", "mcp_error"])
    conn.register("_mcp_results", df)
    try:
        conn.execute(
            f"CREATE TEMP TABLE {_qi(view_name)} AS "
            f"SELECT s.* EXCLUDE (_rn), r.mcp_result, r.mcp_status, r.mcp_error "
            f"FROM (SELECT *, row_number() OVER () AS _rn FROM {_qi(input_view)}) s "
            f"LEFT JOIN _mcp_results r ON r.rn = s._rn"
        )
    finally:
        conn.unregister("_mcp_results")


CONTRACTS.append(
    OperationContract(
        op="transform.mcpCall",
        kind="transform",
        params_schema=TransformMcpCallParams,
        engine="python",
        engine_license="Apache-2.0 (requests) ; protocole MCP (JSON-RPC sur HTTP streamable)",
        execute=execute_mcp_call,
        needs_runtime_context=True,
        output_srid=_mcp_output_srid,
    )
)
