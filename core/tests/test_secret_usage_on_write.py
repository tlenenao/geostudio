# SPDX-License-Identifier: Apache-2.0
"""REV-331/342 : l'usage d'un secret est vérifié pour l'utilisateur qui ÉCRIT la config
(pipeline ou alerte), pas seulement pour le propriétaire qui l'exécute (confused deputy)."""

import pytest

from app.items import repository as items_repo
from tests.test_secrets_routes import BEARER_BODY, _as, env  # noqa: F401


def _pipeline(secret: str) -> dict:
    return {
        "kind": "pipeline",
        "pipeline": {
            "nodes": [
                {
                    "id": "r1",
                    "kind": "reader",
                    "op": "reader.connector.rest",
                    "params": {
                        "baseUrl": "https://api.example.test",
                        "path": "x",
                        "secretName": secret,
                    },
                },
                {
                    "id": "w1",
                    "kind": "writer",
                    "op": "writer.email",
                    "params": {"secretName": secret, "toColumn": "to", "subject": "s"},
                },
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        },
    }


def _alert(dataset_id: str, channels: list[dict]) -> dict:
    return {
        "kind": "alert",
        "alert": {
            "datasetItemId": dataset_id,
            "query": {"agg": "count"},
            "condition": {"expr": "value > 1"},
            "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
            "channels": channels,
        },
    }


@pytest.fixture()
def secrets_env(env, monkeypatch):  # noqa: F811
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    app, client, Session, admin, regular = env
    with Session() as s:  # le Créateur peut écrire pipelines/alertes et ses propres secrets
        from app.roles.repository import ensure_built_in_roles

        regular = s.merge(regular)
        regular.role_id = ensure_built_in_roles(s, tenant_id=regular.tenant_id)["creator"].id
        s.commit()
    _as(app, admin)
    assert client.post("/v1/secrets", json=BEARER_BODY).status_code == 201  # "weather-api"
    _as(app, regular)
    mine = {"name": "mine", "payload": {"kind": "bearer_token", "token": "t"}}
    assert client.post("/v1/secrets", json=mine).status_code == 201
    return app, client, Session, admin, regular


def test_pipeline_create_refuses_a_secret_the_writer_cannot_use(secrets_env):
    _app, client, *_ = secrets_env
    r = client.post("/v1/configs", json={"title": "p", "config": _pipeline("weather-api")})
    assert r.status_code == 422 and "weather-api" in r.text
    assert (
        client.post("/v1/configs", json={"title": "p", "config": _pipeline("mine")}).status_code
        == 201
    )


def test_pipeline_update_refuses_a_secret_the_writer_cannot_use(secrets_env):
    _app, client, *_ = secrets_env
    created = client.post("/v1/configs", json={"title": "p", "config": _pipeline("mine")}).json()
    r = client.put(f"/v1/configs/by-item/{created['itemId']}", json=_pipeline("weather-api"))
    assert r.status_code == 422 and "weather-api" in r.text
    r = client.put(f"/v1/configs/{created['id']}", json=_pipeline("weather-api"))
    assert r.status_code == 422


def test_admin_with_secrets_privilege_can_use_any_secret(secrets_env):
    app, client, _Session, admin, _regular = secrets_env
    _as(app, admin)
    assert (
        client.post("/v1/configs", json={"title": "p", "config": _pipeline("mine")}).status_code
        == 201
    )


def test_alert_write_checks_smtp_and_signing_secrets(secrets_env):
    _app, client, Session, _admin, regular = secrets_env
    with Session() as s:
        ds = items_repo.create_item(
            s, tenant_id=regular.tenant_id, owner_id=regular.id, resource_type="dataset", title="d"
        )
        s.commit()
        ds_id = ds.id
    email = {"kind": "email", "to": "a@b.c", "smtpSecretName": "weather-api"}
    hook = {"kind": "webhook", "url": "https://example.test/h", "signingSecretName": "weather-api"}
    for channel in (email, hook):
        r = client.post("/v1/configs", json={"title": "a", "config": _alert(ds_id, [channel])})
        assert r.status_code == 422 and "weather-api" in r.text, r.text
    ok = {**hook, "signingSecretName": "mine"}
    r = client.post("/v1/configs", json={"title": "a", "config": _alert(ds_id, [ok])})
    assert r.status_code == 201, r.text
