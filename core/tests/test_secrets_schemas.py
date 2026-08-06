# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretCreate


def test_api_key_header_placement_round_trips():
    body = SecretCreate.model_validate({
        "name": "geoserver-key",
        "payload": {"kind": "api_key", "location": "header", "key": "X-API-Key", "value": "abc"},
    })
    assert body.payload.location == "header"
    assert body.payload.key == "X-API-Key"


def test_api_key_query_placement_round_trips():
    # ArcGIS Feature Service / WFS-style token-in-query-param auth (spec §4).
    body = SecretCreate.model_validate({
        "name": "arcgis-fs-token",
        "payload": {"kind": "api_key", "location": "query", "key": "token", "value": "abc123"},
    })
    assert body.payload.location == "query"


def test_bearer_token_round_trips():
    body = SecretCreate.model_validate({
        "name": "weather-api", "payload": {"kind": "bearer_token", "token": "tok"},
    })
    assert body.payload.token == "tok"


def test_basic_auth_round_trips():
    body = SecretCreate.model_validate({
        "name": "wfs-basic",
        "payload": {"kind": "basic_auth", "username": "u", "password": "p"},
    })
    assert body.payload.username == "u"


def test_oauth2_client_credentials_round_trips():
    # ArcGIS Online app-login shape (spec §4).
    body = SecretCreate.model_validate({
        "name": "arcgis-online-app",
        "payload": {
            "kind": "oauth2_client_credentials",
            "tokenUrl": "https://www.arcgis.com/sharing/rest/oauth2/token",
            "clientId": "cid", "clientSecret": "csecret",
        },
    })
    assert body.payload.clientId == "cid"


def test_postgres_dsn_round_trips():
    body = SecretCreate.model_validate({
        "name": "warehouse-pg", "payload": {"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"},
    })
    assert body.payload.dsn == "postgresql://u:p@host/db"


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({"name": "x", "payload": {"kind": "ssh_key", "value": "y"}})


def test_api_key_requires_location():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({
            "name": "x", "payload": {"kind": "api_key", "key": "k", "value": "v"},
        })


def test_secret_payload_adapter_decodes_decrypted_dict():
    # This is exactly what repository.get_secret_payload does after
    # crypto.decrypt() returns a plain dict (Task 4).
    payload = SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "bearer_token", "token": "tok"})
    assert payload.token == "tok"
