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
        "/v1/configs", json={"title": "App", "config": _config_body_with_pages("incidents")}
    )
    assert response.status_code == 400
    assert "acme.gauge" in response.json()["detail"]


def test_create_config_rejects_extension_prop_outside_scope(client):
    response = client.post(
        "/v1/configs", json={"title": "App", "config": _config_body("incidents")}
    )
    assert response.status_code == 400
    assert "acme.gauge" in response.json()["detail"]


def test_create_config_accepts_extension_prop_inside_scope(client):
    response = client.post("/v1/configs", json={"title": "App", "config": _config_body("communes")})
    assert response.status_code == 201


def test_create_config_ignores_non_extension_widgets(client):
    body = {
        "kind": "app",
        "dataSources": [],
        "layout": {"type": "grid", "items": [{"widget": "map", "x": 0, "y": 0, "w": 2, "h": 2}]},
    }
    response = client.post("/v1/configs", json={"title": "App", "config": body})
    assert response.status_code == 201


def test_update_config_rejects_extension_prop_outside_scope(client):
    created = client.post(
        "/v1/configs", json={"title": "App", "config": _config_body("communes")}
    ).json()
    response = client.put(f"/v1/configs/{created['id']}", json=_config_body("incidents"))
    assert response.status_code == 400


def test_rejected_create_does_not_leave_an_orphan_item(client):
    client.post("/v1/configs", json={"title": "App", "config": _config_body("incidents")})
    listed = client.get("/v1/items").json()
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
        "/v1/configs", json={"title": "App", "config": _config_body("communes")}
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
    reject = client.put(f"/v1/configs/{created['id']}", json=_config_body("communes"))
    assert reject.status_code == 400

    # rollback vers v1 revalide désormais contre le scope courant, et refuse
    # pour la même raison (422, pas 400 : c'est le garde-fou de rollback qui
    # convertit l'HTTPException levée par le validateur).
    rollback = client.post(f"/v1/configs/{created['id']}/rollback", json={"version": 1})
    assert rollback.status_code == 422


def test_put_config_rejects_unknown_widget_type(client):
    ok = {"kind": "app", "layout": {"type": "grid", "items": []}}
    created = client.post("/v1/configs", json={"title": "App", "config": ok})
    assert created.status_code in (200, 201), created.text
    bad = {
        "kind": "app",
        "layout": {
            "type": "grid",
            "items": [{"widget": "hologram", "x": 0, "y": 0, "w": 2, "h": 2}],
        },
    }
    r = client.put(f"/v1/configs/by-item/{created.json()['itemId']}", json=bad)
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "hologram" in r.json()["detail"]


def _ext_app(items: list[dict], data_sources: list[dict]) -> dict:
    return {
        "kind": "app",
        "dataSources": data_sources,
        "layout": {"type": "grid", "items": items},
    }


def _ds(id_: str, layer: str = "", type_: str = "features", **kw) -> dict:
    return {"id": id_, "type": type_, "service": "core", "layer": layer, "query": {}, **kw}


def _gauge(props: dict) -> dict:
    return {"widget": "acme.gauge", "x": 0, "y": 0, "w": 2, "h": 2, "props": props}


def test_extension_data_source_id_is_checked_without_a_declared_prop(client):
    # AUD-108 (a) : WidgetHost lit dataSourceId quel que soit le manifeste.
    body = _ext_app([_gauge({"dataSourceId": "ds_b"})], [_ds("ds_b", "incidents")])
    r = client.post("/v1/configs", json={"title": "App", "config": body})
    assert r.status_code == 400 and "dataSourceId" in r.json()["detail"]


def test_nested_extension_widget_is_checked(client):
    # AUD-108 (b) : widget d'extension imbriqué dans une modale.
    modal = {
        "widget": "modal",
        "x": 0,
        "y": 0,
        "w": 2,
        "h": 2,
        "props": {"items": [_gauge({"source": "ds_b"})]},
    }
    body = _ext_app([modal], [_ds("ds_b", "incidents")])
    r = client.post("/v1/configs", json={"title": "App", "config": body})
    assert r.status_code == 400 and "acme.gauge" in r.json()["detail"]


def test_dataset_source_resolves_to_its_collection(client):
    # AUD-108 (c) : une source datasetId se juge sur la collection du dataset.
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig
    from app.items import repository as items_repo

    with client.session_factory() as s:
        owner = get_or_create_user(
            s,
            tenant_id=client.tenant_id,
            oidc_sub="sub-1",
            username="alice",
            email="alice@example.com",
            first_name="Alice",
            last_name="Doe",
        )
        item = items_repo.create_item(
            s, tenant_id=client.tenant_id, owner_id=owner.id, resource_type="dataset", title="D"
        )
        configs_repo.create_config(
            s,
            BuilderConfig.model_validate(
                {
                    "kind": "dataset",
                    "dataset": {"source": "collection", "collectionId": "incidents"},
                }
            ),
            item.id,
            tenant_id=client.tenant_id,
        )
        s.commit()
        dataset_id = item.id
    body = _ext_app([_gauge({"source": "ds_d"})], [_ds("ds_d", datasetId=dataset_id)])
    r = client.post("/v1/configs", json={"title": "App", "config": body})
    assert r.status_code == 400 and "incidents" in r.json()["detail"]


def test_bound_expression_on_a_data_source_prop_is_refused(client):
    # AUD-108 (d) : une expression n'est pas jugeable à l'écriture.
    body = _ext_app([_gauge({"source": {"$expr": "vars.ds"}})], [_ds("ds1", "communes")])
    r = client.post("/v1/configs", json={"title": "App", "config": body})
    assert r.status_code == 400 and "<expression>" in r.json()["detail"]


def test_static_source_is_accepted(client):
    # AUD-108 (e) : une source statique ne lit aucune collection.
    body = _ext_app([_gauge({"source": "s"})], [_ds("s", type_="static")])
    r = client.post("/v1/configs", json={"title": "App", "config": body})
    assert r.status_code == 201, r.text
