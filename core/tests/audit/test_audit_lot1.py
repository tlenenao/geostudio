# SPDX-License-Identifier: Apache-2.0
"""Tests reproducteurs de l'audit (lot 1). Chacun échoue tant que le bug existe (xfail strict)."""

import gzip
import http.server
import threading
from unittest.mock import MagicMock

import duckdb
import httpx
import pytest
from pydantic import ValidationError

from app.alerts import notify
from app.configs.schemas import AlertChannelEmail
from app.harvest import egress as harvest_egress
from app.pipelines import connector_runtime
from app.pipelines.ops.schemas import ReaderConnectorRestParams
from app.secrets.schemas import AzureBlobCredentialsPayload, SmtpCredentialsPayload


@pytest.mark.xfail(
    strict=True, reason="REV-audit: send_email sans assert_egress_allowed (notify.py:142)"
)
def test_smtp_secret_to_internal_host_is_blocked_before_connecting(monkeypatch):
    payload = SmtpCredentialsPayload(
        host="10.0.0.5", port=25, username="u", password="p", useTls=True, fromAddress="a@b.c"
    )
    monkeypatch.setattr(notify, "_owner_user", lambda *a, **k: MagicMock())
    monkeypatch.setattr(notify.secrets_repo, "get_secret_payload", lambda *a, **k: payload)
    connected = []

    class Boom(Exception):
        pass

    def fake_smtp(host, port, **kw):
        connected.append((host, port))
        raise OSError("connected")

    monkeypatch.setattr(notify.smtplib, "SMTP", fake_smtp)
    channel = AlertChannelEmail(to="x@y.z", smtpSecretName="s")
    with pytest.raises(notify.NotifyError, match="egress"):
        notify.send_email(
            MagicMock(), tenant_id="t", item_id="i", channel=channel, subject="s", body="b"
        )
    assert connected == []


class _H(http.server.BaseHTTPRequestHandler):
    seen: list = []
    target = ""

    def do_GET(self):
        if self.server.role == "a":
            self.send_response(302)
            self.send_header("Location", self.server.other_url + "/items")
            self.end_headers()
        else:
            _H.seen.append(self.headers.get("X-Api-Key"))
            body = b'[{"id": 1}]'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    def log_message(self, *a):
        pass


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: reader REST suit les redirections avec l'en-tête secret (connector_runtime.py:569)",  # noqa: E501
)
def test_rest_reader_does_not_forward_api_key_header_on_redirect(monkeypatch):
    import requests

    monkeypatch.setattr(connector_runtime, "build_guarded_session", requests.Session)
    _H.seen = []
    a = http.server.HTTPServer(("127.0.0.1", 0), _H)
    b = http.server.HTTPServer(("127.0.0.1", 0), _H)
    a.role, b.role = "a", "b"
    a.other_url = f"http://127.0.0.1:{b.server_port}"
    for s in (a, b):
        threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        conn = duckdb.connect(":memory:")
        params = ReaderConnectorRestParams(
            baseUrl=f"http://127.0.0.1:{a.server_port}/",
            path="items",
            headers={"X-Api-Key": "SUPERSECRET"},
        )
        try:
            connector_runtime.materialize_rest_connector(
                conn, secret_resolver=None, node_id="r", params=params, view_name="n_r"
            )
        except Exception:
            pass
    finally:
        a.shutdown()
        b.shutdown()
    assert "SUPERSECRET" not in _H.seen


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: plafond moissonnage sur octets compressés (harvest/egress.py:97)",
)
def test_harvest_cap_applies_to_decoded_gzip_bytes(monkeypatch):
    monkeypatch.setenv("CORE_HARVEST_MAX_RESPONSE_BYTES", "10000")
    monkeypatch.setattr(harvest_egress, "assert_egress_allowed", lambda url: [])
    monkeypatch.setattr(harvest_egress, "send_pinned", lambda fn, req, ips: fn(req))
    bomb = gzip.compress(b"\0" * 5_000_000)
    assert len(bomb) < 10_000
    inner = httpx.MockTransport(
        lambda req: httpx.Response(200, headers={"content-encoding": "gzip"}, content=bomb)
    )
    client = httpx.Client(transport=harvest_egress._GuardedTransport(inner))
    with pytest.raises(harvest_egress.ResponseTooLargeError):
        client.get("https://example.test/x").content  # noqa: B018


@pytest.mark.xfail(
    strict=True, reason="REV-audit: accountName Azure non validé, hôte piloté (schemas.py:354)"
)
def test_azure_account_name_rejects_host_injection():
    with pytest.raises(ValidationError):
        AzureBlobCredentialsPayload(
            accountName="10.0.0.5:8080/x?",
            accountKey="a2V5",
            bucketUrl="az://c/",
        )


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: token_uri du compte de service GCS non validé (connector_runtime.py:918)",
)
def test_gcs_service_account_token_uri_is_validated():
    from app.secrets.schemas import GcsCredentialsPayload

    with pytest.raises(ValidationError):
        GcsCredentialsPayload(
            serviceAccountInfo={
                "type": "service_account",
                "client_email": "a@b.iam.gserviceaccount.com",
                "private_key": "x",
                "token_uri": "http://169.254.169.254/token",
            },
            bucketUrl="gs://b/",
        )


@pytest.mark.xfail(
    strict=True,
    reason="REV-audit: confused deputy, secret d'un autre non contrôlé à l'écriture (alerts/notify.py:44)",  # noqa: E501
)
def test_alert_config_write_checks_secret_usage_by_editor():
    pytest.xfail("non testable unitairement sans scénario HTTP complet")


def test_gpkg_import_rejects_vrt_disguised_file(tmp_path):
    from app.ingestion.parsers import IngestionParseError, parse_gpkg

    src = tmp_path / "s.geojson"
    src.write_text(
        '{"type":"FeatureCollection","features":[{"type":"Feature","properties":{"secret":"LEAK"},"geometry":{"type":"Point","coordinates":[1,2]}}]}'
    )
    vrt = (
        f'<OGRVRTDataSource><OGRVRTLayer name="x"><SrcDataSource>{src}</SrcDataSource>'
        "<SrcLayer>s</SrcLayer></OGRVRTLayer></OGRVRTDataSource>"
    ).encode()
    with pytest.raises(IngestionParseError):
        list(parse_gpkg(vrt))
