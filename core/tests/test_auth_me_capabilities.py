# SPDX-License-Identifier: Apache-2.0
"""`GET /me` porte les capacités de l'instance.

Le shell dérive l'état de ses neuf domaines d'un profil unique (spec §6.6) :
rôle du compte + capacités du déploiement. Sans ce champ, il faudrait croiser
deux requêtes dans chaque écran — c'est ce que fait le code d'aujourd'hui, et
c'est ce que la refonte supprime.
"""

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

CAPABILITY_KEYS = {
    "readOnly",
    "etlEnabled",
    "exportEnabled",
    "appExportEnabled",
    "tileset3dEnabled",
    "terrain3dEnabled",
    "copilotEnabled",
}


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="sub-1",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    yield TestClient(app)
    engine.dispose()


def test_me_exposes_every_capability(client):
    response = client.get("/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["capabilities"]) == CAPABILITY_KEYS
    for key, value in body["capabilities"].items():
        assert isinstance(value, bool), f"{key} doit être un booléen, pas {type(value)}"


def test_me_capabilities_match_the_instance_route(client):
    """Les deux routes doivent dire la même chose : `GET /instance` reste servi
    avant authentification (page de connexion, mode démo) et ne disparaît pas.
    Si elles divergent, un écran affichera une capacité que l'autre refuse."""
    me = client.get("/me").json()["capabilities"]
    instance = client.get("/instance").json()
    assert me == instance


def test_me_keeps_its_existing_fields(client):
    """Non-régression : le champ ajouté ne doit rien retirer — le shell lit
    encore `username`, `isAdmin` et `isAnalyst` à quinze endroits."""
    body = client.get("/me").json()
    for key in (
        "id",
        "tenantId",
        "username",
        "email",
        "firstName",
        "lastName",
        "isAdmin",
        "isAnalyst",
    ):
        assert key in body, f"champ disparu de MeResponse : {key}"


@pytest.mark.parametrize("env_value,expected", [("true", True), ("false", False)])
def test_capability_reflects_the_environment(client, monkeypatch, env_value, expected):
    monkeypatch.setenv("CORE_ETL_ENABLED", env_value)
    assert client.get("/me").json()["capabilities"]["etlEnabled"] is expected
