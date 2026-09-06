# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.dcat import routes as dcat_routes
from app.features import routes as features_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="incidents",
    pk_column="id",
    geometry_column="geom",
    geometry_type="Point",
    srid=4326,
    columns=[ColumnInfo(name="titre", type="string", required=True)],
)


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
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
        regular = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="regular",
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
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table, tenant_id=None: None
    )
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    # ST_EstimatedExtent n'existe pas sur SQLite : stub d'emprise.
    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: (
        lambda session, info: [1.0, 44.0, 2.0, 45.0]
    )
    return app, TestClient(app), admin, regular, Session


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, *, public=False, description=""):
    _as(app, admin)
    client.post(
        "/v1/collections",
        json={"tableName": "incidents", "isPublic": public, "description": description},
    )


def test_catalog_content_type_and_shape(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True, description="Réseau routier")
    resp = client.get("/v1/dcat/catalog")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@type"] == "dcat:Catalog"
    assert len(body["dcat:dataset"]) == 1
    ds = body["dcat:dataset"][0]
    assert ds["dct:identifier"] == "incidents"
    assert ds["dct:description"] == "Réseau routier"
    assert ds["dct:accessRights"]["@id"].endswith("/PUBLIC")
    assert len(ds["dcat:distribution"]) == 2


def test_dcat_catalog_is_paginated(env):
    app, client, admin, _regular, _Session = env

    def introspector_for_many(session, table_name):
        return TableInfo(
            table_name=table_name,
            pk_column="id",
            geometry_column="geom",
            geometry_type="Point",
            srid=4326,
            columns=[],
        )

    app.dependency_overrides[collections_routes.get_introspector] = lambda: introspector_for_many
    _as(app, admin)
    for i in range(3):
        resp = client.post("/v1/collections", json={"tableName": f"t{i}", "isPublic": True})
        assert resp.status_code == 201

    body = client.get("/v1/dcat/catalog?limit=2&offset=0").json()
    assert len(body["dcat:dataset"]) == 2
    rels = {link["rel"]: link["href"] for link in body.get("links", [])}
    assert "offset=2" in rels["next"]

    body2 = client.get("/v1/dcat/catalog?limit=2&offset=2").json()
    assert len(body2["dcat:dataset"]) == 1
    assert "next" not in {link["rel"] for link in body2.get("links", [])}


def test_broken_collection_degrades_instead_of_failing_whole_catalog(env, caplog):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)

    info2 = TableInfo(
        table_name="incidents2",
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[],
    )

    def introspector_with_incidents2(session, table_name):
        if table_name == "incidents2":
            return info2
        return fake_introspector(session, table_name)

    app.dependency_overrides[collections_routes.get_introspector] = lambda: (
        introspector_with_incidents2
    )
    _as(app, admin)
    resp = client.post("/v1/collections", json={"tableName": "incidents2", "isPublic": True})
    assert resp.status_code == 201

    def flaky_bbox_provider(session, info):
        if info.table_name == "incidents2":
            raise TableNotFound("gone")
        return [1.0, 44.0, 2.0, 45.0]

    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: flaky_bbox_provider
    with caplog.at_level("WARNING"):
        catalog_resp = client.get("/v1/dcat/catalog")
    assert catalog_resp.status_code == 200
    ids = [d["dct:identifier"] for d in catalog_resp.json()["dcat:dataset"]]
    assert set(ids) == {"incidents", "incidents2"}
    assert "extent lookup failed" in caplog.text


def test_broken_collection_code_bug_is_not_swallowed(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)

    def buggy_provider(session, info):
        raise TypeError("bug")

    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: buggy_provider
    with pytest.raises(TypeError):
        client.get("/v1/dcat/catalog")


def test_catalog_reflects_restricted_access_rights(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=False)
    resp = client.get("/v1/dcat/catalog")  # vue admin : voit sa propre collection non publique
    ds = resp.json()["dcat:dataset"][0]
    assert ds["dct:accessRights"]["@id"].endswith("/RESTRICTED")


def test_dataset_detail_is_self_contained_with_context(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)
    resp = client.get("/v1/dcat/datasets/incidents")
    assert resp.headers["content-type"] == "application/ld+json"
    body = resp.json()
    assert body["@context"] == {
        "dcat": "http://www.w3.org/ns/dcat#",
        "dct": "http://purl.org/dc/terms/",
        "foaf": "http://xmlns.com/foaf/0.1/",
        "locn": "http://www.w3.org/ns/locn#",
        "xsd": "http://www.w3.org/2001/XMLSchema#",
        "vcard": "http://www.w3.org/2006/vcard/ns#",
        "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    }
    assert body["dct:identifier"] == "incidents"


def test_dataset_detail_404_non_leaking(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=False)
    _as(app, admin)
    assert client.get("/v1/dcat/datasets/nope").status_code == 404
    # Anonyme sur collection non publique → 404 non-fuyant.
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/v1/dcat/datasets/incidents").status_code == 404


def test_anonymous_catalog_shows_public_only_no_leak(env):
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)
    assert client.get("/v1/dcat/catalog").json()["dcat:dataset"] == []


def test_custom_role_with_collections_manage_sees_a_private_collection_in_catalog(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, admin, regular, Session = env
    _register(app, client, admin, public=False)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)

        resp = client.get("/v1/dcat/catalog")
        assert [d["dct:identifier"] for d in resp.json()["dcat:dataset"]] == ["incidents"]


def test_custom_role_with_collections_manage_reaches_dataset_detail(env):
    # Round 2 : GET /dcat/catalog montrait déjà la collection privée (fix
    # précédent) mais son détail (/dcat/datasets/{id}) appelait encore
    # get_readable_collection() sans can_manage_collections → 404 en cliquant
    # dessus, même défaut que celui déjà fermé sur /collections/{id}/schema.
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, admin, regular, Session = env
    _register(app, client, admin, public=False)

    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        custom = create_role(
            s,
            tenant_id=tenant.id,
            name="Gestionnaire de collections",
            privileges=[Privilege.ADMIN_COLLECTIONS_MANAGE.value],
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=regular.id,
            role_id=custom.id,
            role_slug=custom.slug,
        )
        s.commit()
        regular_id = regular.id

    with Session() as s:
        from app.users.models import User

        custom_user = s.get(User, regular_id)
        assert custom_user is not None and custom_user.is_admin is False
        _as(app, custom_user)

        resp = client.get("/v1/dcat/datasets/incidents")
        assert resp.status_code == 200
        assert resp.json()["dct:identifier"] == "incidents"


def test_dcat_dataset_reflects_declared_license(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/v1/collections/incidents", json={"license": "etalab-2.0"})
    res = client.get("/v1/dcat/datasets/incidents")
    assert res.json()["dct:license"] == {"@id": "https://spdx.org/licenses/etalab-2.0.html"}


def test_dcat_dataset_publisher_uses_producer_when_declared(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    _as(app, admin)
    client.patch("/v1/collections/incidents", json={"producer": "Ma Régie"})
    res = client.get("/v1/dcat/datasets/incidents")
    assert res.json()["dct:publisher"]["foaf:name"] == "Ma Régie"
    # SP-41, correctif de revue finale : un producteur déclaré obtient une IRI
    # de publisher distincte (par collection), pas l'IRI partagée à l'échelle
    # du tenant.
    assert res.json()["dct:publisher"]["@id"] == "http://testserver/v1/dcat/publisher/incidents"


def test_dataset_detail_degrades_to_none_on_broken_collection(env, caplog):
    # GAP-62 (reste) : une collection présente mais dont la table est cassée
    # (introspection/emprise en échec) ne doit pas faire échouer le détail
    # DCAT en 500 — même dégradation que get_catalog/get_collection.
    from app.collections.introspection import TableNotFound as _TableNotFound

    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)

    def broken_bbox_provider(session, info):
        raise _TableNotFound("gone")

    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: broken_bbox_provider
    resp = client.get("/dcat/datasets/incidents")
    assert resp.status_code == 200
    body = resp.json()
    assert body["dct:identifier"] == "incidents"
    assert "extent lookup failed" in caplog.text


def test_dataset_detail_code_bug_is_not_swallowed(env):
    # Le tuple d'exceptions capturé doit rester étroit : un bug de code
    # (TypeError) ne doit jamais être avalé en bbox=None (piège CLAUDE.md n°10).
    app, client, admin, _regular, _Session = env
    _register(app, client, admin, public=True)

    def buggy_bbox_provider(session, info):
        raise TypeError("bug")

    app.dependency_overrides[dcat_routes.get_bbox_provider] = lambda: buggy_bbox_provider
    with pytest.raises(TypeError):
        client.get("/dcat/datasets/incidents")


def test_dcat_dataset_without_declared_metadata_omits_optional_fields(env):
    app, client, admin, _regular, Session = env
    _register(app, client, admin)
    res = client.get("/v1/dcat/datasets/incidents")
    body = res.json()
    assert body["dct:license"] == {
        "@id": "http://publications.europa.eu/resource/authority/licence/OTHER"
    }
    assert "dct:accrualPeriodicity" not in body
    assert "dct:provenance" not in body
    assert "dcat:contactPoint" not in body
    assert "dct:hasVersion" not in body
    # Exception assumée (spec §3/§7.2) : dct:language, lui, apparaît
    # désormais inconditionnellement (défaut "fr" jamais vide) — ce n'est
    # PAS un défaut de non-régression.
    assert body["dct:language"] == {
        "@id": "http://publications.europa.eu/resource/authority/language/FRA"
    }
