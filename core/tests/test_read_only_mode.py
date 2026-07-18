# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

READ_ONLY_MESSAGE = "Mode démo : lecture seule, écritures désactivées."


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_defaults_to_read_write(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": False}


def test_instance_reports_read_only_without_needing_auth(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json() == {"readOnly": True}


@pytest.mark.parametrize(
    "method,path",
    [
        ("POST", "/configs"),
        ("PATCH", "/collections/does-not-exist"),
        ("DELETE", "/configs/does-not-exist"),
        ("PUT", "/collections/does-not-exist/items/1"),
        ("POST", "/extensions"),
    ],
)
def test_read_only_mode_blocks_every_mutation_even_for_admin(env, monkeypatch, method, path):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.request(method, path, json={})
    assert response.status_code == 403
    assert response.json() == {"detail": READ_ONLY_MESSAGE}


def test_read_only_mode_does_not_affect_reads(env, monkeypatch):
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    assert env.get("/items").status_code == 200
    assert env.get("/me").status_code == 200


def test_read_only_mode_off_by_default_leaves_mutations_working(env):
    response = env.post(
        "/configs",
        json={"title": "T", "config": {"kind": "app", "layout": {"type": "grid", "items": []}}},
    )
    assert response.status_code == 201


def test_read_only_mode_does_not_block_the_aggregate_endpoint(env, monkeypatch):
    """POST /collections/{id}/aggregate est une lecture malgré son verbe HTTP
    (le corps est structuré, pas une liste de query params — cf. spec SP-11b) ;
    le exempter du garde read-only évite de casser tout widget Graphique/
    Indicateur dans une démo publique."""
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.post("/collections/does-not-exist/aggregate", json={"groupBy": "x"})
    assert response.status_code == 404  # jamais 403 : passé le garde, arrêté par get_readable_collection


def test_analytics_sql_is_exempt_from_read_only(env, monkeypatch):
    """POST /analytics/sql est une lecture (SP-11c) malgré son verbe HTTP ;
    en mode démo lecture seule, le middleware ne doit pas le 403-er avant même
    que la route ne s'exécute. La fixture `env` authentifie un admin qui n'est
    pas analyste, donc la route elle-même renvoie 403 (analyst role required)
    — mais ce n'est PAS le message du middleware read-only, ce qui prouve que
    la requête a bien traversé le garde."""
    monkeypatch.setenv("CORE_READ_ONLY_MODE", "true")
    response = env.post("/analytics/sql", json={"sql": "SELECT 1"})
    assert response.status_code == 403
    assert response.json() != {"detail": READ_ONLY_MESSAGE}
