# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SecretCreate


def test_api_key_header_placement_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "geoserver-key",
            "payload": {
                "kind": "api_key",
                "location": "header",
                "key": "X-API-Key",
                "value": "abc",
            },
        }
    )
    assert body.payload.location == "header"
    assert body.payload.key == "X-API-Key"


def test_api_key_query_placement_round_trips():
    # ArcGIS Feature Service / WFS-style token-in-query-param auth (spec §4).
    body = SecretCreate.model_validate(
        {
            "name": "arcgis-fs-token",
            "payload": {"kind": "api_key", "location": "query", "key": "token", "value": "abc123"},
        }
    )
    assert body.payload.location == "query"


def test_bearer_token_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "weather-api",
            "payload": {"kind": "bearer_token", "token": "tok"},
        }
    )
    assert body.payload.token == "tok"


def test_basic_auth_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "wfs-basic",
            "payload": {"kind": "basic_auth", "username": "u", "password": "p"},
        }
    )
    assert body.payload.username == "u"


def test_oauth2_client_credentials_round_trips():
    # ArcGIS Online app-login shape (spec §4).
    body = SecretCreate.model_validate(
        {
            "name": "arcgis-online-app",
            "payload": {
                "kind": "oauth2_client_credentials",
                "tokenUrl": "https://www.arcgis.com/sharing/rest/oauth2/token",
                "clientId": "cid",
                "clientSecret": "csecret",
            },
        }
    )
    assert body.payload.clientId == "cid"


def test_postgres_dsn_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "warehouse-pg",
            "payload": {"kind": "postgres_dsn", "dsn": "postgresql://u:p@host/db"},
        }
    )
    assert body.payload.dsn == "postgresql://u:p@host/db"


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({"name": "x", "payload": {"kind": "ssh_key", "value": "y"}})


def test_api_key_requires_location():
    with pytest.raises(ValidationError):
        SecretCreate.model_validate(
            {
                "name": "x",
                "payload": {"kind": "api_key", "key": "k", "value": "v"},
            }
        )


def test_secret_payload_adapter_decodes_decrypted_dict():
    # This is exactly what repository.get_secret_payload does after
    # crypto.decrypt() returns a plain dict (Task 4).
    payload = SECRET_PAYLOAD_ADAPTER.validate_python({"kind": "bearer_token", "token": "tok"})
    assert payload.token == "tok"


def test_snowflake_dsn_round_trips():
    body = SecretCreate.model_validate(
        {
            "name": "warehouse-sf",
            "payload": {
                "kind": "snowflake_dsn",
                "dsn": "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1&role=role1",
            },
        }
    )
    assert body.payload.dsn == "snowflake://u:p@myaccount/mydb/myschema?warehouse=wh1&role=role1"


def test_smtp_credentials_payload_round_trips():
    from app.secrets.schemas import SECRET_PAYLOAD_ADAPTER, SmtpCredentialsPayload

    payload = SmtpCredentialsPayload(
        host="smtp.example.test",
        port=587,
        username="alerts@example.test",
        password="s3cret",
        useTls=True,
        fromAddress="alerts@example.test",
    )
    dumped = SECRET_PAYLOAD_ADAPTER.dump_python(payload)
    assert dumped["kind"] == "smtp"
    restored = SECRET_PAYLOAD_ADAPTER.validate_python(dumped)
    assert isinstance(restored, SmtpCredentialsPayload)
    assert restored.host == "smtp.example.test"
    assert restored.useTls is True


from app.secrets.schemas import SecretUpdate  # noqa: E402

_BLOB_BODIES = {
    "s3_credentials": {
        "awsAccessKeyId": "AKIA",
        "awsSecretAccessKey": "x",
        "bucketUrl": "s3://b/p",
    },
    "azure_blob_credentials": {"accountName": "a", "accountKey": "k", "bucketUrl": "az://c/p"},
    "gcs_credentials": {"serviceAccountInfo": {"type": "service_account"}, "bucketUrl": "gs://b"},
}


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_blob_secret_round_trips_with_bucket_url(kind):
    body = {"kind": kind, **_BLOB_BODIES[kind]}
    created = SecretCreate.model_validate({"name": "x", "payload": body})
    assert created.payload.bucketUrl == _BLOB_BODIES[kind]["bucketUrl"]


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_blob_secret_creation_requires_bucket_url(kind):
    body = {"kind": kind, **{k: v for k, v in _BLOB_BODIES[kind].items() if k != "bucketUrl"}}
    with pytest.raises(ValidationError, match="bucketUrl"):
        SecretCreate.model_validate({"name": "x", "payload": body})
    with pytest.raises(ValidationError, match="bucketUrl"):
        SecretUpdate.model_validate({"payload": body})


@pytest.mark.parametrize("kind", sorted(_BLOB_BODIES))
def test_legacy_blob_secret_without_bucket_url_still_decodes(kind):
    # Un secret chiffré avant REV-197 doit rester lisible (l'exécution, elle, échoue
    # avec un message explicite — cf. connector_runtime).
    body = {"kind": kind, **{k: v for k, v in _BLOB_BODIES[kind].items() if k != "bucketUrl"}}
    assert SECRET_PAYLOAD_ADAPTER.validate_python(body).bucketUrl is None


@pytest.mark.parametrize(
    "kind, bad",
    [
        ("s3_credentials", "az://b/p"),  # mauvais schéma pour le kind
        ("s3_credentials", "s3://"),  # pas de bucket
        ("s3_credentials", "s3://b/../other"),  # traversée
        ("s3_credentials", "s3://b/p?x=1"),  # query
        ("s3_credentials", "s3://*/p"),  # joker dans le bucket
        ("s3_credentials", "s3://b/p/*"),  # joker dans le préfixe
        ("s3_credentials", "s3://b/p[0-9]"),
        ("azure_blob_credentials", "s3://c"),
        ("gcs_credentials", "gs:///p"),
    ],
)
def test_blob_bucket_url_format_is_validated(kind, bad):
    body = {"kind": kind, **_BLOB_BODIES[kind], "bucketUrl": bad}
    with pytest.raises(ValidationError):
        SecretCreate.model_validate({"name": "x", "payload": body})


_SMTP = {
    "kind": "smtp",
    "host": "smtp.example.test",
    "port": 25,
    "username": "u",
    "password": "p",
    "useTls": False,
    "fromAddress": "a@example.test",
}


def test_secret_create_rejects_smtp_without_tls_on_a_remote_host():
    with pytest.raises(ValidationError, match="useTls"):
        SecretCreate(name="m", payload=_SMTP)


def test_secret_update_rejects_smtp_without_tls_on_a_remote_host():
    from app.secrets.schemas import SecretUpdate

    with pytest.raises(ValidationError, match="useTls"):
        SecretUpdate(payload=_SMTP)


@pytest.mark.parametrize("host", ["localhost", "127.0.0.1", "::1", "LocalHost"])
def test_secret_create_accepts_smtp_without_tls_on_localhost(host):
    SecretCreate(name="m", payload={**_SMTP, "host": host})


def test_stored_smtp_payload_without_tls_still_decodes():
    # Compat : un secret déjà chiffré avec useTls=false doit rester lisible.
    assert SECRET_PAYLOAD_ADAPTER.validate_python(_SMTP).useTls is False


def test_databricks_dsn_round_trips_and_requires_http_path():
    dsn = "databricks://token:dapi123@adb-1.azuredatabricks.net?http_path=/sql/1.0/warehouses/abc&catalog=main&schema=default"
    body = SecretCreate.model_validate(
        {"name": "dbx", "payload": {"kind": "databricks_dsn", "dsn": dsn}}
    )
    assert body.payload.dsn == dsn
    with pytest.raises(ValueError, match="http_path"):
        SecretCreate.model_validate(
            {
                "name": "dbx",
                "payload": {
                    "kind": "databricks_dsn",
                    "dsn": "databricks://token:t@adb-1.azuredatabricks.net?catalog=main",
                },
            }
        )
