# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.extensions import repository as ext_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


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
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        ext_repo.create_extension(
            s,
            tenant_id=tenant.id,
            owner_id=user.id,
            id="acme.gauge",
            tag="gauge-extension-widget",
            label="Jauge",
            module_url="https://x/gauge.js",
            props=[{"name": "source", "type": "dataSource", "label": "Source", "default": None}],
            events=None,
            actions=None,
            default_size={"w": 2, "h": 2},
            permissions={"collections": ["communes"]},
        )
        s.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    test_client = TestClient(app)
    test_client.session_factory = Session  # type: ignore[attr-defined]
    test_client.tenant_id = tenant.id  # type: ignore[attr-defined]
    return test_client


def _config_body(data_source_layer: str) -> dict:
    return {
        "kind": "app",
        "dataSources": [
            {
                "id": "ds1",
                "type": "features",
                "service": "core",
                "layer": data_source_layer,
                "query": {},
            }
        ],
        "layout": {
            "type": "grid",
            "items": [
                {
                    "widget": "acme.gauge",
                    "x": 0,
                    "y": 0,
                    "w": 2,
                    "h": 2,
                    "props": {"source": "ds1"},
                },
            ],
        },
    }


def _config_body_with_pages(data_source_layer: str) -> dict:
    return {
        "kind": "app",
        "dataSources": [
            {
                "id": "ds1",
                "type": "features",
                "service": "core",
                "layer": data_source_layer,
                "query": {},
            }
        ],
        "layout": {"type": "grid", "items": []},
        "pages": [
            {
                "id": "page1",
                "name": "Page 1",
                "layout": {
                    "type": "grid",
                    "items": [
                        {
                            "widget": "acme.gauge",
                            "x": 0,
                            "y": 0,
                            "w": 2,
                            "h": 2,
                            "props": {"source": "ds1"},
                        },
                    ],
                },
            },
        ],
    }


def test_create_config_rejects_extension_prop_outside_scope_in_pages(client):
    # Le widget d'extension est uniquement dans pages[0].layout.items (le
    # layout racine a une liste d'items vide) : ce test ne peut passer que
    # si _all_layout_items parcourt bien config.pages, pas seulement
    # config.layout.
    response = client.post(
        "/configs", json={"title": "App", "config": _config_body_with_pages("incidents")}
    )
    assert response.status_code == 400
    assert "acme.gauge" in response.json()["detail"]


def test_create_config_rejects_extension_prop_outside_scope(client):
    response = client.post("/configs", json={"title": "App", "config": _config_body("incidents")})
    assert response.status_code == 400
    assert "acme.gauge" in response.json()["detail"]


def test_create_config_accepts_extension_prop_inside_scope(client):
    response = client.post("/configs", json={"title": "App", "config": _config_body("communes")})
    assert response.status_code == 201


def test_create_config_ignores_non_extension_widgets(client):
    body = {
        "kind": "app",
        "dataSources": [],
        "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 2, "h": 2}]},
    }
    response = client.post("/configs", json={"title": "App", "config": body})
    assert response.status_code == 201


def test_update_config_rejects_extension_prop_outside_scope(client):
    created = client.post(
        "/configs", json={"title": "App", "config": _config_body("communes")}
    ).json()
    response = client.put(f"/configs/{created['id']}", json=_config_body("incidents"))
    assert response.status_code == 400


def test_rejected_create_does_not_leave_an_orphan_item(client):
    client.post("/configs", json={"title": "App", "config": _config_body("incidents")})
    listed = client.get("/items").json()
    assert listed["total"] == 0


def test_rollback_is_rejected_if_it_would_now_violate_a_narrowed_scope(client):
    # SP-8c (spec §Hors périmètre) avait volontairement laissé le rollback
    # restaurer une révision sans revalidation, faute d'appelant réel. SP-23
    # (chantier 4.18) inverse cette décision une fois le panneau
    # « Historique » câblé sur de vrais éditeurs : rollback_config revalide
    # désormais la config restaurée avec exactement la même séquence que
    # update_config, dont _validate_extension_scope fait partie.
    from app.extensions import repository as ext_repo

    # v1 : "communes" est dans le scope déclaré de l'extension au moment de la création.
    created = client.post(
        "/configs", json={"title": "App", "config": _config_body("communes")}
    ).json()

    # Un admin resserre ensuite le scope de l'extension : "communes" n'est
    # plus autorisée. On le fait directement en base (pas via l'API
    # /extensions, hors périmètre de ce test) pour isoler le comportement du
    # rollback de celui de la route PATCH /extensions déjà testée ailleurs.
    with client.session_factory() as s:
        ext = ext_repo.get_extension(s, tenant_id=client.tenant_id, extension_id="acme.gauge")
        ext_repo.update_extension(s, ext, permissions={"collections": ["incidents"]})
        s.commit()

    # create_config/update_config revalident bien contre le scope courant :
    # "communes" est désormais refusée.
    reject = client.put(f"/configs/{created['id']}", json=_config_body("communes"))
    assert reject.status_code == 400

    # rollback vers v1 revalide désormais contre le scope courant, et refuse
    # pour la même raison (422, pas 400 : c'est le garde-fou de rollback qui
    # convertit l'HTTPException levée par le validateur).
    rollback = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 422
