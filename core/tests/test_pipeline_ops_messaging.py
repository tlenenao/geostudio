# SPDX-License-Identifier: Apache-2.0
"""Voie E FME : messagerie & notification (writer.email/slack/trello/servicebus/azurequeue/
sns/kinesis/rabbitmq, reader.azurequeue/kinesis/rabbitmq, transform.mcpCall). Aucun réseau :
la session HTTP gardée, SMTP et pika sont remplacés ; les gardes (portée du secret, egress,
plafonds, annulation, aperçu, audit) sont, elles, réelles."""

import base64
import json
from types import SimpleNamespace
from urllib.parse import parse_qs

import duckdb
import pika
import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.audit.models import AuditLog
from app.configs.schemas import PipelineNode
from app.db import init_db, make_engine, make_session_factory
from app.pipelines import egress as pipelines_egress
from app.pipelines.connector_runtime import PostgresSecretResolver
from app.pipelines.errors import PipelineRuntimeError
from app.pipelines.ops import messaging
from app.pipelines.ops.contracts import OPERATIONS, ops_catalog
from app.secrets import repository as secrets_repo
from app.secrets.crypto import encrypt
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

TEST_MASTER_KEY = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
_REAL_EGRESS_GUARD = pipelines_egress.assert_egress_allowed
_REAL_BUILD_SESSION = pipelines_egress.build_guarded_session

WRITERS = {
    "writer.email",
    "writer.slack",
    "writer.trello",
    "writer.servicebus",
    "writer.azurequeue",
    "writer.sns",
    "writer.kinesis",
    "writer.rabbitmq",
}
READERS = {"reader.azurequeue", "reader.kinesis", "reader.rabbitmq"}
LANE_OPS = WRITERS | READERS | {"transform.mcpCall"}


@pytest.fixture()
def session(monkeypatch):
    monkeypatch.setenv("CORE_SECRETS_MASTER_KEY", TEST_MASTER_KEY)
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    with make_session_factory(engine)() as s:
        yield s
    engine.dispose()


@pytest.fixture()
def tenant(session):
    return get_or_create_default_tenant(session)


@pytest.fixture()
def user(session, tenant):
    return get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="u1",
        username="u1",
        email=None,
        first_name="",
        last_name="",
    )


@pytest.fixture()
def conn():
    c = duckdb.connect(":memory:")
    c.execute("INSTALL spatial; LOAD spatial;")
    yield c
    c.close()


@pytest.fixture(autouse=True)
def _no_sleep_no_guard(monkeypatch):
    monkeypatch.setattr(messaging.time, "sleep", lambda s: None)
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", lambda url: None)


def _secret(session, tenant, user, name, payload):
    ct, nonce = encrypt(payload)
    secrets_repo.create_secret(
        session,
        tenant_id=tenant.id,
        created_by=user.id,
        name=name,
        kind=payload["kind"],
        ciphertext=ct,
        nonce=nonce,
    )


def _bearer(session, tenant, user, base, name="s"):
    _secret(session, tenant, user, name, {"kind": "bearer_token", "token": "T0K", "baseUrl": base})


class _Resp:
    def __init__(self, status=200, body=b"", headers=None):
        self.status_code, self.body, self.headers = status, body, headers or {}

    def iter_content(self, n):
        for i in range(0, len(self.body), n):
            yield self.body[i : i + n]

    def close(self):
        pass


@pytest.fixture()
def http(monkeypatch):
    """Remplace la session gardée ; `h.handler(method, url, kw) -> _Resp`, `h.calls` journalise."""
    h = SimpleNamespace(calls=[], handler=lambda m, u, kw: _Resp(200, b"{}"))

    class _Sess:
        def request(self, method, url, **kw):
            h.calls.append({"method": method, "url": url, **kw})
            return h.handler(method, url, kw)

        def close(self):
            pass

    monkeypatch.setattr(pipelines_egress, "build_guarded_session", lambda: _Sess())
    return h


def _write(op, conn, session, tenant, user, params, sql, *, cancel=None):
    conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS {sql}")
    node = PipelineNode(id="w", kind="writer", op=op, params={"secretName": "s", **params})
    return messaging.WRITERS[op](
        session,
        conn,
        node=node,
        view_by_node={"w": "inp"},
        tenant_id=tenant.id,
        user=user,
        should_cancel=cancel,
    )


def _read(op, conn, session, tenant, user, params):
    messaging.READERS[op](
        conn,
        session=session,
        tenant_id=tenant.id,
        node_id="r",
        params={"secretName": "s", **params},
        view_name="out",
        user=user,
        base_uri="",
    )
    return conn.execute("SELECT * FROM out").fetchall()


def _audits(session, op):
    return [
        a
        for a in session.scalars(
            select(AuditLog).where(AuditLog.action == "pipeline.external_write")
        )
        if a.payload["op"] == op
    ]


ROWS3 = "SELECT * FROM (VALUES (1,'a@x.org','hello <!channel> & co'),(2,'b@x.org','two'),(3,'c@x.org','three')) t(id,mail,txt)"  # noqa: E501


def test_lane_contracts_and_catalog():
    assert {c.op for c in messaging.CONTRACTS} == LANE_OPS
    assert set(messaging.WRITERS) == WRITERS
    assert set(messaging.READERS) == READERS
    assert LANE_OPS <= set(ops_catalog())
    assert all(OPERATIONS[o].engine_license for o in LANE_OPS)


# ------------------------------------------------------------------ garde commune (portée, egress)


def test_secret_scope_must_cover_url_and_no_call_is_made(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://evil.example/")
    with pytest.raises(PipelineRuntimeError, match="baseUrl must cover"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "txt"},
            ROWS3,
        )
    assert http.calls == []


def test_wrong_secret_kind_refused(http, conn, session, tenant, user):
    _secret(session, tenant, user, "s", {"kind": "basic_auth", "username": "u", "password": "p"})
    with pytest.raises(PipelineRuntimeError, match="expected bearer_token"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "txt"},
            ROWS3,
        )


def test_real_egress_guard_blocks_internal_target(monkeypatch, conn, session, tenant, user):
    """Falsification : sans la garde (autouse), la même requête partirait vers le loopback."""
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    monkeypatch.setattr(pipelines_egress, "build_guarded_session", _REAL_BUILD_SESSION)
    _bearer(session, tenant, user, "https://127.0.0.1/")
    node_params = {"namespaceUrl": "https://127.0.0.1", "entity": "q"}
    with pytest.raises(PipelineRuntimeError, match="(?i)egress|interne|blocked"):
        _write("writer.servicebus", conn, session, tenant, user, node_params, ROWS3)


def test_redirects_are_never_followed(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://slack.com/api/")
    http.handler = lambda m, u, kw: _Resp(200, b'{"ok":true}')
    _write(
        "writer.slack", conn, session, tenant, user, {"channel": "#c", "textColumn": "txt"}, ROWS3
    )
    assert http.calls and all(c["allow_redirects"] is False for c in http.calls)
    http.handler = lambda m, u, kw: _Resp(302, b"", {"Location": "https://evil.example"})
    with pytest.raises(PipelineRuntimeError, match="HTTP 302"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "txt"},
            ROWS3,
        )


def test_cap_cancel_and_audit_before_effect(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://slack.com/api/")
    http.handler = lambda m, u, kw: _Resp(200, b'{"ok":true}')
    p = {"channel": "#c", "textColumn": "txt"}
    with pytest.raises(PipelineRuntimeError, match="plafond de 2"):
        _write("writer.slack", conn, session, tenant, user, {**p, "maxMessages": 2}, ROWS3)
    assert http.calls == [] and _audits(session, "writer.slack") == []  # rien n'est parti
    n = {"c": 0}

    def cancel():
        n["c"] += 1
        return n["c"] > 1  # annule avant le 2e message

    with pytest.raises(PipelineRuntimeError, match="cancelled after 1"):
        _write("writer.slack", conn, session, tenant, user, p, ROWS3, cancel=cancel)
    assert len(http.calls) == 1
    audits = _audits(session, "writer.slack")
    assert len(audits) == 1 and audits[0].payload["messages"] == 3  # audit commité avant l'envoi


def test_empty_input_sends_nothing(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://slack.com/api/")
    stat = _write(
        "writer.slack",
        conn,
        session,
        tenant,
        user,
        {"channel": "#c", "textColumn": "txt"},
        ROWS3 + " WHERE false",
    )
    assert stat.rowCount == 0 and http.calls == []


def test_column_missing_and_null_are_clean_errors(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://slack.com/api/")
    with pytest.raises(PipelineRuntimeError, match="column\\(s\\) not found"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "nope"},
            ROWS3,
        )
    with pytest.raises(PipelineRuntimeError, match="is NULL"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "t"},
            "SELECT NULL::VARCHAR AS t",
        )


# ------------------------------------------------------------------ Emailer


def _smtp_secret(session, tenant, user, **kw):
    _secret(
        session,
        tenant,
        user,
        "s",
        {
            "kind": "smtp",
            "host": "smtp.x.org",
            "port": 587,
            "username": "u",
            "password": "p",
            "useTls": True,
            "fromAddress": "noreply@x.org",
            **kw,
        },
    )


def test_email_sends_one_message_per_row_on_one_connection(
    monkeypatch, conn, session, tenant, user
):
    from unittest.mock import MagicMock, patch

    _smtp_secret(session, tenant, user)
    with patch("app.secrets.smtp_send.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value.__enter__.return_value = MagicMock()
        stat = _write(
            "writer.email",
            conn,
            session,
            tenant,
            user,
            {"toColumn": "mail", "subject": "Alerte", "bodyColumn": "txt"},
            ROWS3,
        )
    assert stat.rowCount == 3 and smtp_cls.call_count == 1
    smtp.starttls.assert_called_once()
    msgs = [c.args[0] for c in smtp.send_message.call_args_list]
    assert [m["To"] for m in msgs] == ["a@x.org", "b@x.org", "c@x.org"]
    assert msgs[0]["From"] == "noreply@x.org" and msgs[0]["Subject"] == "Alerte"


def test_email_rejects_bad_recipient_domain_and_header_injection(conn, session, tenant, user):
    from unittest.mock import MagicMock, patch

    _smtp_secret(session, tenant, user)
    p = {"toColumn": "mail", "subject": "S"}
    with patch("app.secrets.smtp_send.smtplib.SMTP") as smtp_cls:
        smtp = smtp_cls.return_value.__enter__.return_value = MagicMock()
        with pytest.raises(PipelineRuntimeError, match="domain not allowed"):
            _write(
                "writer.email",
                conn,
                session,
                tenant,
                user,
                {**p, "allowedRecipientDomains": ["corp.fr"]},
                ROWS3,
            )
        with pytest.raises(PipelineRuntimeError, match="invalid recipient"):
            _write(
                "writer.email",
                conn,
                session,
                tenant,
                user,
                p,
                "SELECT E'a@x.org\\nBcc: evil@x.org' AS mail",
            )
    smtp.send_message.assert_not_called()
    with pytest.raises(ValidationError):
        messaging.WriterEmailParams(secretName="s", toColumn="m", subject="a\nBcc: x@y.z")


def test_email_refuses_plaintext_smtp_to_remote_host(conn, session, tenant, user):
    _smtp_secret(session, tenant, user, useTls=False) if False else _secret(
        session,
        tenant,
        user,
        "s",
        {
            "kind": "smtp",
            "host": "smtp.x.org",
            "port": 25,
            "username": "u",
            "password": "p",
            "useTls": False,
            "fromAddress": "a@x.org",
        },
    )
    from unittest.mock import patch

    with patch("app.secrets.smtp_send.smtplib.SMTP") as smtp_cls:
        with pytest.raises(PipelineRuntimeError, match="TLS"):
            _write(
                "writer.email",
                conn,
                session,
                tenant,
                user,
                {"toColumn": "mail", "subject": "S"},
                ROWS3,
            )
        smtp_cls.assert_not_called()


# ------------------------------------------------------------------ Slack / Trello


def test_slack_escapes_mentions_and_reports_api_errors(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://slack.com/api/")
    http.handler = lambda m, u, kw: _Resp(200, b'{"ok":true}')
    _write(
        "writer.slack", conn, session, tenant, user, {"channel": "#c", "textColumn": "txt"}, ROWS3
    )
    sent = [json.loads(c["data"]) for c in http.calls]
    assert sent[0]["text"] == "hello &lt;!channel&gt; &amp; co" and sent[0]["channel"] == "#c"
    assert http.calls[0]["headers"]["Authorization"] == "Bearer T0K"
    http.handler = lambda m, u, kw: _Resp(200, b'{"ok":false,"error":"channel_not_found"}')
    with pytest.raises(PipelineRuntimeError, match="channel_not_found"):
        _write(
            "writer.slack",
            conn,
            session,
            tenant,
            user,
            {"channel": "#c", "textColumn": "txt"},
            ROWS3,
        )


def test_trello_creates_cards(http, conn, session, tenant, user):
    _secret(
        session,
        tenant,
        user,
        "s",
        {
            "kind": "basic_auth",
            "username": "KEY",
            "password": "TOK",
            "baseUrl": "https://api.trello.com/",
        },
    )
    http.handler = lambda m, u, kw: _Resp(200, b"{}")
    stat = _write(
        "writer.trello",
        conn,
        session,
        tenant,
        user,
        {"listId": "abcd1234efgh", "nameColumn": "txt", "descColumn": "mail"},
        ROWS3,
    )
    assert stat.rowCount == 3
    c = http.calls[1]
    assert c["url"] == "https://api.trello.com/1/cards"
    assert 'oauth_consumer_key="KEY", oauth_token="TOK"' in c["headers"]["Authorization"]
    assert json.loads(c["data"]) == {"idList": "abcd1234efgh", "name": "two", "desc": "b@x.org"}


# ------------------------------------------------------------------ Azure


def test_servicebus_message_ids_are_stable_across_reruns(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://ns.servicebus.windows.net")
    http.handler = lambda m, u, kw: _Resp(201, b"")
    p = {
        "namespaceUrl": "https://ns.servicebus.windows.net",
        "entity": "q1",
        "messageIdColumn": "id",
        "payloadColumns": ["txt"],
    }
    _write("writer.servicebus", conn, session, tenant, user, p, ROWS3)
    first = [c["headers"]["BrokerProperties"] for c in http.calls]
    http.calls.clear()
    _write("writer.servicebus", conn, session, tenant, user, p, ROWS3)
    assert [c["headers"]["BrokerProperties"] for c in http.calls] == first  # rejeu = mêmes ids
    assert json.loads(first[0]) == {"MessageId": "1"}
    assert http.calls[0]["url"] == "https://ns.servicebus.windows.net/q1/messages"
    assert json.loads(http.calls[0]["data"]) == {
        "txt": "hello <!channel> & co"
    }  # corps = payloadColumns
    http.handler = lambda m, u, kw: _Resp(401, b"denied")
    with pytest.raises(PipelineRuntimeError, match="HTTP 401"):
        _write("writer.servicebus", conn, session, tenant, user, p, ROWS3)
    with pytest.raises(ValidationError):
        messaging.WriterServiceBusParams(
            secretName="s", namespaceUrl="https://ns.servicebus.windows.net/evil", entity="q"
        )


_QUEUE_XML = (
    b'<?xml version="1.0"?><QueueMessagesList>'
    b"<QueueMessage><MessageId>m1</MessageId><InsertionTime>t1</InsertionTime>"
    b"<ExpirationTime>t2</ExpirationTime><DequeueCount>2</DequeueCount>"
    + b"<MessageText>"
    + base64.b64encode(b'{"a":1}')
    + b"</MessageText></QueueMessage></QueueMessagesList>"
)


def test_azurequeue_write_and_peek(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://acct.queue.core.windows.net")
    http.handler = lambda m, u, kw: _Resp(201, b"")
    p = {"accountUrl": "https://acct.queue.core.windows.net", "queue": "jobs"}
    stat = _write("writer.azurequeue", conn, session, tenant, user, p, ROWS3)
    assert stat.rowCount == 3
    body = http.calls[0]["data"].decode()
    inner = body.split("<MessageText>")[1].split("</MessageText>")[0]
    assert json.loads(base64.b64decode(inner))["id"] == 1
    http.calls.clear()
    http.handler = lambda m, u, kw: _Resp(200, _QUEUE_XML)
    rows = _read("reader.azurequeue", conn, session, tenant, user, p)
    assert rows == [("m1", "t1", "t2", 2, '{"a":1}')]
    assert http.calls[0]["params"] == {"peekonly": "true", "numofmessages": "32"}  # non destructif


def test_azurequeue_reader_refuses_xml_entities(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://acct.queue.core.windows.net")
    evil = b'<?xml version="1.0"?><!DOCTYPE x [<!ENTITY a "aaaa">]><QueueMessagesList/>'
    http.handler = lambda m, u, kw: _Resp(200, evil)
    with pytest.raises(PipelineRuntimeError, match="DTD"):
        _read(
            "reader.azurequeue",
            conn,
            session,
            tenant,
            user,
            {"accountUrl": "https://acct.queue.core.windows.net", "queue": "jobs"},
        )
    http.handler = lambda m, u, kw: _Resp(200, b"")  # file vide
    assert (
        _read(
            "reader.azurequeue",
            conn,
            session,
            tenant,
            user,
            {"accountUrl": "https://acct.queue.core.windows.net", "queue": "jobs"},
        )
        == []
    )


# ------------------------------------------------------------------ AWS


def _aws_secret(session, tenant, user, base):
    _secret(
        session,
        tenant,
        user,
        "s",
        {
            "kind": "basic_auth",
            "username": "AKIDEXAMPLE",
            "password": "wJalrXUtnFEMI",
            "baseUrl": base,
        },
    )


def test_sns_publishes_signed_request_with_dedup_id(http, conn, session, tenant, user):
    _aws_secret(session, tenant, user, "https://sns.eu-west-1.amazonaws.com")
    http.handler = lambda m, u, kw: _Resp(200, b"<PublishResponse/>")
    arn = "arn:aws:sns:eu-west-1:123456789012:alerts.fifo"
    p = {
        "topicArn": arn,
        "region": "eu-west-1",
        "messageColumn": "txt",
        "messageGroupId": "g",
        "deduplicationIdColumn": "id",
    }
    stat = _write("writer.sns", conn, session, tenant, user, p, ROWS3)
    assert stat.rowCount == 3
    c = http.calls[1]
    assert c["url"] == "https://sns.eu-west-1.amazonaws.com/"
    assert c["headers"]["Authorization"].startswith("AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/")
    assert "wJalrXUtnFEMI" not in json.dumps(c["headers"])  # la clé secrète n'est jamais envoyée
    form = parse_qs(c["data"].decode())
    assert form["Action"] == ["Publish"] and form["TopicArn"] == [arn]
    assert form["MessageDeduplicationId"] == ["2"] and form["Message"] == ["two"]
    with pytest.raises(ValidationError):  # région ≠ région de l'ARN
        messaging.WriterSnsParams(secretName="s", topicArn=arn, region="us-east-1")
    # le secret ne couvre pas un endpoint personnalisé : refusé, rien ne part
    http.calls.clear()
    with pytest.raises(PipelineRuntimeError, match="baseUrl must cover"):
        _write(
            "writer.sns",
            conn,
            session,
            tenant,
            user,
            {**p, "endpointUrl": "https://evil.example"},
            ROWS3,
        )
    assert http.calls == []


def test_kinesis_write_and_bounded_read(http, conn, session, tenant, user):
    _aws_secret(session, tenant, user, "https://kinesis.eu-west-1.amazonaws.com")
    p = {"streamName": "st", "region": "eu-west-1"}
    http.handler = lambda m, u, kw: _Resp(200, b'{"SequenceNumber":"1"}')
    _write("writer.kinesis", conn, session, tenant, user, {**p, "partitionKeyColumn": "id"}, ROWS3)
    assert http.calls[0]["headers"]["X-Amz-Target"] == "Kinesis_20131202.PutRecord"
    doc = json.loads(http.calls[2]["data"])
    assert doc["PartitionKey"] == "3" and json.loads(base64.b64decode(doc["Data"]))["id"] == 3

    http.calls.clear()
    data = base64.b64encode(b"payload").decode()

    def handler(method, url, kw):
        target = kw["headers"]["X-Amz-Target"].split(".")[1]
        if target == "ListShards":
            return _Resp(
                200, json.dumps({"Shards": [{"ShardId": "s-0"}, {"ShardId": "s-1"}]}).encode()
            )
        if target == "GetShardIterator":
            return _Resp(200, b'{"ShardIterator":"IT"}')
        rec = {
            "SequenceNumber": "9",
            "PartitionKey": "k",
            "Data": data,
            "ApproximateArrivalTimestamp": 1.5,
        }
        return _Resp(
            200,
            json.dumps(
                {"Records": [rec, rec], "NextShardIterator": "IT", "MillisBehindLatest": 5}
            ).encode(),
        )

    http.handler = handler
    rows = _read("reader.kinesis", conn, session, tenant, user, {**p, "maxRecords": 3})
    assert len(rows) == 3 and rows[0][0] == "s-0" and rows[0][4] == "payload"  # plafond respecté
    with pytest.raises(ValidationError):
        messaging.ReaderKinesisParams(secretName="s", **p, iteratorType="AT_TIMESTAMP")


# ------------------------------------------------------------------ RabbitMQ


class _FakeChannel:
    def __init__(self, conn):
        self.c = conn

    def confirm_delivery(self):
        pass

    def basic_publish(self, exchange, key, body, props, mandatory=False):
        if self.c.unroutable:
            raise pika.exceptions.UnroutableError([])
        self.c.published.append((exchange, key, json.loads(body), props.message_id, mandatory))

    def basic_get(self, queue, auto_ack=False):
        if not self.c.inbox:
            return None, None, None
        body, mid = self.c.inbox.pop(0)
        return (
            SimpleNamespace(routing_key="rk", redelivered=False),
            SimpleNamespace(message_id=mid),
            body,
        )

    def basic_recover(self, requeue=False):
        self.c.recovered = requeue


class _FakeMq:
    def __init__(self):
        self.published, self.inbox, self.unroutable = [], [], False
        self.recovered = None
        self.closed = False
        self.params = None

    def channel(self):
        return _FakeChannel(self)

    def close(self):
        self.closed = True


@pytest.fixture()
def mq(monkeypatch):
    fake = _FakeMq()

    def factory(params):
        fake.params = params
        return fake

    monkeypatch.setattr(pika, "BlockingConnection", factory)
    return fake


def _amqp_secret(session, tenant, user, base="https://mq.example.org:5671"):
    _secret(
        session,
        tenant,
        user,
        "s",
        {"kind": "basic_auth", "username": "u", "password": "p", "baseUrl": base},
    )


def test_rabbitmq_publish_confirmed_mandatory_and_stable_ids(mq, conn, session, tenant, user):
    _amqp_secret(session, tenant, user)
    p = {"host": "mq.example.org", "exchange": "ex", "routingKey": "geo", "messageIdColumn": "id"}
    stat = _write("writer.rabbitmq", conn, session, tenant, user, p, ROWS3)
    assert stat.rowCount == 3 and mq.closed
    assert [(m[0], m[1], m[3], m[4]) for m in mq.published] == [
        ("ex", "geo", "1", True),
        ("ex", "geo", "2", True),
        ("ex", "geo", "3", True),
    ]  # noqa: E501
    assert mq.params.ssl_options is not None and mq.params.port == 5671  # TLS toujours
    mq.unroutable = True
    with pytest.raises(PipelineRuntimeError, match="UnroutableError"):
        _write("writer.rabbitmq", conn, session, tenant, user, p, ROWS3)


def test_rabbitmq_secret_must_be_bound_to_the_host(mq, conn, session, tenant, user):
    _amqp_secret(session, tenant, user, base="https://other.example.org:5671")
    with pytest.raises(PipelineRuntimeError, match="baseUrl must be"):
        _write(
            "writer.rabbitmq",
            conn,
            session,
            tenant,
            user,
            {"host": "mq.example.org", "routingKey": "k"},
            ROWS3,
        )
    assert mq.published == [] and mq.params is None  # aucune connexion ouverte


def test_rabbitmq_egress_blocked(monkeypatch, mq, conn, session, tenant, user):
    monkeypatch.setattr(pipelines_egress, "assert_egress_allowed", _REAL_EGRESS_GUARD)
    _amqp_secret(session, tenant, user, base="https://127.0.0.1:5671")
    with pytest.raises(PipelineRuntimeError, match="egress blocked"):
        _write(
            "writer.rabbitmq",
            conn,
            session,
            tenant,
            user,
            {"host": "127.0.0.1", "routingKey": "k"},
            ROWS3,
        )
    assert mq.params is None


def test_rabbitmq_read_is_bounded_and_requeues(mq, conn, session, tenant, user):
    _amqp_secret(session, tenant, user)
    mq.inbox = [(b"m%d" % i, f"id{i}") for i in range(5)]
    rows = _read(
        "reader.rabbitmq",
        conn,
        session,
        tenant,
        user,
        {"host": "mq.example.org", "queue": "q", "maxMessages": 3},
    )
    assert [r[3] for r in rows] == ["m0", "m1", "m2"] and len(mq.inbox) == 2
    assert mq.recovered is True and mq.closed  # rien d'acquitté : remis en file


# ------------------------------------------------------------------ MCPCaller


def _mcp_server(calls_out):
    def handler(method, url, kw):
        msg = json.loads(kw["data"])
        calls_out.append((msg, kw["headers"]))
        if msg["method"] == "initialize":
            return _Resp(
                200,
                json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": {}}).encode(),
                {"Content-Type": "application/json", "Mcp-Session-Id": "SID"},
            )
        if msg["method"] == "notifications/initialized":
            return _Resp(202, b"")
        args = msg["params"]["arguments"]
        if args.get("q") == "boom":
            res = {"content": [{"type": "text", "text": "bad"}], "isError": True}
        else:
            res = {"content": [{"type": "text", "text": f"echo:{args['q']}:{args.get('k')}"}]}
        sse = (
            b"event: message\ndata: "
            + json.dumps({"jsonrpc": "2.0", "id": msg["id"], "result": res}).encode()
            + b"\n\n"
        )  # noqa: E501
        return _Resp(200, sse, {"Content-Type": "text/event-stream"})

    return handler


def _mcp(conn, session, tenant, user, sql, *, preview=False, **over):
    conn.execute(f"CREATE OR REPLACE TEMP TABLE inp AS {sql}")
    params = {
        "secretName": "s",
        "url": "https://mcp.example.org/mcp",
        "tool": "search",
        "argumentColumns": {"q": "txt"},
        "staticArguments": {"k": "v"},
        **over,
    }
    messaging.execute_mcp_call(
        conn,
        input_view="inp",
        view_name="out",
        params=params,
        secret_resolver=PostgresSecretResolver(session, tenant.id, user),
        preview=preview,
    )
    return conn.execute(
        "SELECT id, mcp_result, mcp_status, mcp_error FROM out ORDER BY id"
    ).fetchall()


def test_mcp_call_per_row_with_session_and_only_the_named_tool(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://mcp.example.org/")
    seen: list = []
    http.handler = _mcp_server(seen)
    rows = _mcp(conn, session, tenant, user, "SELECT * FROM (VALUES (1,'x'),(2,'boom')) t(id,txt)")
    assert rows == [(1, "echo:x:v", "ok", None), (2, "bad", "tool_error", None)]
    methods = [m["method"] for m, _ in seen]
    assert methods == ["initialize", "notifications/initialized", "tools/call", "tools/call"]
    assert {m["params"]["name"] for m, _ in seen if m["method"] == "tools/call"} == {"search"}
    assert seen[2][1]["Mcp-Session-Id"] == "SID" and seen[2][1]["Authorization"] == "Bearer T0K"
    a = [x for x in session.scalars(select(AuditLog)) if x.action == "pipeline.external_write"]
    assert len(a) == 1 and a[0].payload["tool"] == "search" and a[0].payload["calls"] == 2
    assert "x" not in json.dumps(a[0].payload["calls"])  # jamais les arguments dans l'audit


def test_mcp_preview_calls_nothing(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://mcp.example.org/")
    http.handler = _mcp_server([])
    rows = _mcp(conn, session, tenant, user, "SELECT 1 AS id, 'x' AS txt", preview=True)
    assert rows == [(1, None, "skipped_preview", None)] and http.calls == []


def test_mcp_scope_cap_and_degenerate_inputs(http, conn, session, tenant, user):
    _bearer(session, tenant, user, "https://other.example.org/")
    http.handler = _mcp_server([])
    sql = "SELECT * FROM (VALUES (1,'x'),(2,'y')) t(id,txt)"
    with pytest.raises(PipelineRuntimeError, match="baseUrl must cover"):
        _mcp(conn, session, tenant, user, sql)
    assert http.calls == []
    _bearer(session, tenant, user, "https://mcp.example.org/", name="ok")
    with pytest.raises(PipelineRuntimeError, match="plafond de 1"):
        _mcp(conn, session, tenant, user, sql, secretName="ok", maxCalls=1)
    with pytest.raises(PipelineRuntimeError, match="column\\(s\\) not found"):
        _mcp(conn, session, tenant, user, sql, secretName="ok", argumentColumns={"q": "nope"})
    with pytest.raises(PipelineRuntimeError, match="not found"):
        _mcp(conn, session, tenant, user, sql, secretName="absent")
    assert _mcp(conn, session, tenant, user, sql + " WHERE false", secretName="ok") == []  # vide
    assert http.calls == []


def test_mcp_secret_not_usable_by_another_user(http, conn, session, tenant, user):
    """Permissions de l'utilisateur seulement : un secret qu'il ne peut pas utiliser = absent."""
    _bearer(session, tenant, user, "https://mcp.example.org/")
    other = get_or_create_user(
        session,
        tenant_id=tenant.id,
        oidc_sub="u2",
        username="u2",
        email=None,
        first_name="",
        last_name="",
    )
    http.handler = _mcp_server([])
    conn.execute("CREATE OR REPLACE TEMP TABLE inp AS SELECT 1 AS id, 'x' AS txt")
    with pytest.raises(PipelineRuntimeError, match="not found"):
        messaging.execute_mcp_call(
            conn,
            input_view="inp",
            view_name="out",
            params={
                "secretName": "s",
                "url": "https://mcp.example.org/mcp",
                "tool": "search",
                "argumentColumns": {"q": "txt"},
            },
            secret_resolver=PostgresSecretResolver(session, tenant.id, other),
            preview=False,
        )
    assert http.calls == []


def test_run_session_is_never_committed_by_a_writer(monkeypatch, http, conn, session, tenant, user):
    """Piège revues B/D : commiter la session du run casserait sa transaction (rollback F5)."""
    _bearer(session, tenant, user, "https://slack.com/api/")
    http.handler = lambda m, u, kw: _Resp(200, b'{"ok":true}')

    def boom(*a, **k):
        raise AssertionError("session du run commitée")

    monkeypatch.setattr(session, "commit", boom)
    stat = _write(
        "writer.slack", conn, session, tenant, user, {"channel": "#c", "textColumn": "txt"}, ROWS3
    )
    assert stat.rowCount == 3 and len(_audits(session, "writer.slack")) == 1
