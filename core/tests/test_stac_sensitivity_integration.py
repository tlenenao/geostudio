# SPDX-License-Identifier: Apache-2.0
"""Bout en bout PostGIS réel : preuve que les 3 routes STAC de lecture
(list_items, get_item, search) masquent un champ marqué sensible — Finding
C1 de la revue finale de branche GAP-22.

Avant correctif, ces 3 routes lisaient les données via le même
repo.select_features/repo.get_feature que les routes OGC Features déjà
masquées (app/features/routes.py), mais sans jamais appeler
`rls(session, ..., masked=...)` ni `hide_sensitive_columns` — un champ
marqué sensible (`salary`) revenait en clair, y compris pour un appelant
anonyme sur une collection publique. Ce test reproduit le PoC de la revue :
falsifié en retirant temporairement le correctif (voir le rapport de
clôture), confirmé en échec avec la colonne effectivement en clair, puis
restauré et confirmé au vert."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stac_employees"))
        conn.execute(
            text(
                "CREATE TABLE stac_employees (id serial PRIMARY KEY, "
                "nom text NOT NULL, salary integer, geom geometry(Point, 4326))"
            )
        )
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="admin",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        # rôle sur mesure SANS data.view_sensitive, avec de quoi lire/gérer
        # des collections — même patron que
        # test_features_sensitive_fields_integration.py (GAP-22, Task 10) :
        # ADMIN_COLLECTIONS_MANAGE seul ne suffit pas à lire via
        # get_readable_collection() côté OGC Features, mais les routes STAC
        # (SP-35/GAP-60) le prennent bien en compte pour can_manage_collections
        # — ici, la collection est de toute façon rendue publique.
        limited_role = create_role(
            s,
            tenant_id=tenant.id,
            name="limited",
            privileges=[Privilege.DATA_VIEW.value, Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        limited = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="l",
            username="limited",
            email=None,
            first_name="",
            last_name="",
        )
        limited.role_id = limited_role.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    yield client, app, admin, limited
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS stac_employees"))
        conn.execute(
            text(
                "TRUNCATE roles, collection_shares, collections, audit_log, users, tenants CASCADE"
            )
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _anonymous(app):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides[get_current_user_optional] = lambda: None


def _setup_collection_with_sensitive_field(client, app, admin):
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "stac_employees"}).status_code == 201
    # isPublic=True : la collection doit être lisible par un appelant
    # anonyme pour que le PoC (fuite vers un lecteur totalement anonyme,
    # cf. Finding C1) soit exercé — le masquage doit tenir MÊME quand la
    # lecture elle-même est autorisée.
    assert (
        client.patch(
            "/v1/collections/stac_employees",
            json={"sensitiveFields": ["salary"], "isPublic": True},
        ).status_code
        == 200
    )
    r = client.post(
        "/v1/collections/stac_employees/items",
        json={
            "type": "Feature",
            "properties": {"nom": "Dupont", "salary": 45000},
            "geometry": {"type": "Point", "coordinates": [1.85, 45.27]},
        },
    )
    assert r.status_code == 201
    return r.json()["id"]


def test_stac_list_items_masks_sensitive_field_for_anonymous(pg_app):
    client, app, admin, _limited = pg_app
    _setup_collection_with_sensitive_field(client, app, admin)

    _anonymous(app)
    items = client.get("/v1/stac/collections/stac_employees/items").json()
    assert len(items["features"]) == 1
    props = items["features"][0]["properties"]
    assert "salary" not in props
    assert props["nom"] == "Dupont"


def test_stac_get_item_masks_sensitive_field_for_anonymous(pg_app):
    client, app, admin, _limited = pg_app
    fid = _setup_collection_with_sensitive_field(client, app, admin)

    _anonymous(app)
    item = client.get(f"/v1/stac/collections/stac_employees/items/{fid}").json()
    assert "salary" not in item["properties"]
    assert item["properties"]["nom"] == "Dupont"


def test_stac_search_get_masks_sensitive_field_for_anonymous(pg_app):
    client, app, admin, _limited = pg_app
    _setup_collection_with_sensitive_field(client, app, admin)

    _anonymous(app)
    result = client.get("/v1/stac/search?collections=stac_employees").json()
    assert len(result["features"]) == 1
    assert "salary" not in result["features"][0]["properties"]


def test_stac_search_post_masks_sensitive_field_for_anonymous(pg_app):
    client, app, admin, _limited = pg_app
    _setup_collection_with_sensitive_field(client, app, admin)

    _anonymous(app)
    result = client.post("/v1/stac/search", json={"collections": ["stac_employees"]}).json()
    assert len(result["features"]) == 1
    assert "salary" not in result["features"][0]["properties"]


def test_stac_masks_sensitive_field_for_user_without_privilege(pg_app):
    client, app, admin, limited = pg_app
    fid = _setup_collection_with_sensitive_field(client, app, admin)

    _as(app, limited)
    items = client.get("/v1/stac/collections/stac_employees/items").json()
    assert "salary" not in items["features"][0]["properties"]
    item = client.get(f"/v1/stac/collections/stac_employees/items/{fid}").json()
    assert "salary" not in item["properties"]
    result = client.get("/v1/stac/search?collections=stac_employees").json()
    assert "salary" not in result["features"][0]["properties"]


def test_stac_shows_sensitive_field_for_user_with_privilege(pg_app):
    client, app, admin, _limited = pg_app
    fid = _setup_collection_with_sensitive_field(client, app, admin)

    # admin porte data.view_sensitive par défaut (BUILT_IN_ROLE_PRIVILEGES).
    _as(app, admin)
    items = client.get("/v1/stac/collections/stac_employees/items").json()
    assert items["features"][0]["properties"]["salary"] == 45000
    item = client.get(f"/v1/stac/collections/stac_employees/items/{fid}").json()
    assert item["properties"]["salary"] == 45000
    result = client.get("/v1/stac/search?collections=stac_employees").json()
    assert result["features"][0]["properties"]["salary"] == 45000
    result_post = client.post("/v1/stac/search", json={"collections": ["stac_employees"]}).json()
    assert result_post["features"][0]["properties"]["salary"] == 45000
