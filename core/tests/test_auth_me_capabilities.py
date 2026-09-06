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
    "adminToolsEnabled",
    "quotasEnabled",
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
    response = client.get("/v1/me")
    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body["capabilities"]) == CAPABILITY_KEYS
    for key, value in body["capabilities"].items():
        assert isinstance(value, bool), f"{key} doit être un booléen, pas {type(value)}"


def test_me_capabilities_match_the_instance_route(client):
    """Les deux routes doivent dire la même chose : `GET /instance` reste servi
    avant authentification (page de connexion, mode démo) et ne disparaît pas.
    Si elles divergent, un écran affichera une capacité que l'autre refuse."""
    me = client.get("/v1/me").json()["capabilities"]
    instance = client.get("/v1/instance").json()
    assert me == instance


def test_me_keeps_its_existing_fields(client):
    body = client.get("/v1/me").json()
    for key in (
        "id",
        "tenantId",
        "username",
        "email",
        "firstName",
        "lastName",
        "role",
        "privileges",
    ):
        assert key in body, f"champ disparu de MeResponse : {key}"
    assert set(body["role"]) == {"id", "name", "slug"}


@pytest.mark.parametrize("env_value,expected", [("true", True), ("false", False)])
def test_capability_reflects_the_environment(client, monkeypatch, env_value, expected):
    monkeypatch.setenv("CORE_ETL_ENABLED", env_value)
    assert client.get("/v1/me").json()["capabilities"]["etlEnabled"] is expected


def test_me_exposes_tenant_slug_and_version(client):
    body = client.get("/v1/me").json()
    assert isinstance(body["tenantSlug"], str) and body["tenantSlug"] != ""
    assert isinstance(body["version"], str) and body["version"] != ""


# Finding I2 (revue finale SP-29a) : `test_me_capabilities_match_the_instance_route`
# ci-dessus prouve l'égalité des deux réponses avec l'environnement par
# défaut, mais `test_capability_reflects_the_environment` ne fait bouger
# qu'UNE seule variable (CORE_ETL_ENABLED) et ne vérifie que `/me`. Comme
# `/me` (app/auth/routes.py::get_me) et `/instance`
# (app/instance/routes.py::get_instance_info) sont deux dict littéraux
# indépendants qui appellent chacun les sept mêmes sondes de
# app/auth/dependency.py, une régression où l'une des deux routes
# mapperait une sonde sur le mauvais champ resterait invisible tant que
# seule la valeur par défaut (identique pour toutes les sondes non
# modifiées) est exercée. Ce test fait bouger CHAQUE variable d'env, une à
# la fois, et vérifie que /me ET /instance suivent ensemble.
_CAPABILITY_PROBES = [
    ("CORE_READ_ONLY_MODE", "readOnly", "true", "false"),
    ("CORE_ETL_ENABLED", "etlEnabled", "true", "false"),
    ("CORE_EXPORT_ENABLED", "exportEnabled", "true", "false"),
    ("CORE_APPEXPORT_ENABLED", "appExportEnabled", "true", "false"),
    ("CORE_TILESET3D_ENABLED", "tileset3dEnabled", "true", "false"),
    ("CORE_TERRAIN3D_ENABLED", "terrain3dEnabled", "true", "false"),
    # is_copilot_enabled() n'est pas un booléen dédié : la capacité est
    # active dès que CORE_LLM_PROVIDER est une chaîne non vide (cf. sa
    # docstring dans app/auth/dependency.py) — pas "true"/"false".
    ("CORE_LLM_PROVIDER", "copilotEnabled", "openai", ""),
    ("CORE_ADMIN_TOOLS_ENABLED", "adminToolsEnabled", "true", "false"),
    ("CORE_QUOTAS_ENABLED", "quotasEnabled", "true", "false"),
]


@pytest.mark.parametrize(
    "env_var,field,true_value,false_value",
    _CAPABILITY_PROBES,
    ids=[field for _, field, _, _ in _CAPABILITY_PROBES],
)
def test_me_and_instance_move_together_for_every_capability(
    client, monkeypatch, env_var, field, true_value, false_value
):
    monkeypatch.setenv(env_var, true_value)
    me = client.get("/v1/me").json()["capabilities"][field]
    instance = client.get("/v1/instance").json()[field]
    assert me is True, f"{field} devrait être vrai avec {env_var}={true_value!r} (/me)"
    assert instance is True, f"{field} devrait être vrai avec {env_var}={true_value!r} (/instance)"

    monkeypatch.setenv(env_var, false_value)
    me = client.get("/v1/me").json()["capabilities"][field]
    instance = client.get("/v1/instance").json()[field]
    assert me is False, f"{field} devrait être faux avec {env_var}={false_value!r} (/me)"
    assert instance is False, (
        f"{field} devrait être faux avec {env_var}={false_value!r} (/instance)"
    )
