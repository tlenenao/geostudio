# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as repo
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound, UnsupportedTable
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INCIDENTS = TableInfo(
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
    return INCIDENTS


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
    ddl_calls: list[str] = []
    app.dependency_overrides[collections_routes.get_ddl_applier] = lambda: (
        lambda session, table: ddl_calls.append(table)
    )
    client = TestClient(app)
    return app, client, Session, admin, regular, ddl_calls


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_register_requires_admin(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, regular)
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 403


def test_register_and_get(env):
    app, client, _, admin, _regular, ddl_calls = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "incidents", "title": "Incidents"})
    assert r.status_code == 201
    body = r.json()
    assert body["id"] == "incidents" and body["geometryType"] == "Point"
    assert body["featureCount"] is None  # hors PostgreSQL (SQLite) : pas de vrai COUNT(*)
    assert ddl_calls == ["incidents"]  # la RLS est appliquée à l'enregistrement
    assert client.get("/collections/incidents").status_code == 200


def test_register_unknown_table_400_and_duplicate_409(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "nope"})
    assert r.status_code == 400
    assert r.json()["detail"] == "table not found in schema public"
    client.post("/collections", json={"tableName": "incidents"})
    assert client.post("/collections", json={"tableName": "incidents"}).status_code == 409


def test_table_name_bounded_to_50_chars(env):
    # 50 = 63 (limite Postgres) − len("ix_" + "_tenant_id") : garantit que le
    # nom d'index tenant_id généré par le DDL n'est jamais tronqué (deux tables
    # au long préfixe commun donneraient sinon le MÊME nom d'index, et le
    # second CREATE INDEX IF NOT EXISTS serait silencieusement sauté).
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "t" * 51})
    assert r.status_code == 422  # rejeté par la validation pydantic
    # 50 caractères : passe la couche schéma — le 400 "table not found" du
    # fake introspector prouve qu'on a atteint la logique métier.
    r = client.post("/collections", json={"tableName": "t" * 50})
    assert r.status_code == 400
    assert r.json()["detail"] == "table not found in schema public"


def test_register_core_table_refused(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    # Le detail exact distingue le refus denylist du fallback TableNotFound
    # ("table not found in schema public") du fake introspector.
    for table in ("items", "configs", "alembic_version"):
        r = client.post("/collections", json={"tableName": table})
        assert r.status_code == 400
        assert r.json()["detail"] == "core table cannot be registered"


def test_denylist_short_circuits_before_introspection(env):
    # Non-régression du timing d'import : la denylist doit couvrir items/configs
    # même si collections.routes est importé avant leurs modèles (main.py les
    # importe alphabétiquement APRÈS app.collections), et refuser AVANT tout
    # appel à l'introspecteur.
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    calls: list[str] = []

    def spying_introspector(session, table_name):
        calls.append(table_name)
        raise TableNotFound(table_name)

    app.dependency_overrides[collections_routes.get_introspector] = lambda: spying_introspector
    r = client.post("/collections", json={"tableName": "items"})
    assert r.status_code == 400
    assert r.json()["detail"] == "core table cannot be registered"
    assert calls == []  # l'introspecteur n'a jamais été appelé


def test_register_postgis_system_table_refused(env):
    # spatial_ref_sys est une table PostGIS ordinaire (PK simple) qui passerait
    # toutes les autres gardes : la denylist doit la couvrir explicitement,
    # sinon l'enregistrer ALTERerait une table système PostGIS (tenant_id,
    # RLS, grants).
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    r = client.post("/collections", json={"tableName": "spatial_ref_sys"})
    assert r.status_code == 400
    assert r.json()["detail"] == "core table cannot be registered"


def test_denylist_postgis_system_tables_short_circuits_before_introspection(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    calls: list[str] = []

    def spying_introspector(session, table_name):
        calls.append(table_name)
        raise TableNotFound(table_name)

    app.dependency_overrides[collections_routes.get_introspector] = lambda: spying_introspector
    for table in ("spatial_ref_sys", "geometry_columns", "geography_columns"):
        r = client.post("/collections", json={"tableName": table})
        assert r.status_code == 400
        assert r.json()["detail"] == "core table cannot be registered"
    assert calls == []  # l'introspecteur n'a jamais été appelé


def test_private_collection_hidden_from_stranger_and_anonymous(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    _as(app, regular)
    assert client.get("/collections/incidents").status_code == 404
    assert client.get("/collections").json()["collections"] == []
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)  # anonyme
    assert client.get("/collections").json()["collections"] == []
    assert client.get("/collections/incidents").status_code == 404


def test_public_collection_visible_to_anonymous(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    body = client.get("/collections").json()
    assert [c["id"] for c in body["collections"]] == ["incidents"]


def test_custom_role_with_collections_manage_sees_a_private_collection(env):
    from app.roles.privileges import Privilege
    from app.roles.repository import create_role
    from app.users.repository import set_user_role

    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # privée, admin owner

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
        listed = client.get("/collections").json()["collections"]
        assert [c["id"] for c in listed] == ["incidents"]


def test_schema_endpoint_uses_introspector(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    schema = client.get("/collections/incidents/schema").json()
    assert schema["pk"] == "id"
    assert schema["fields"] == [{"name": "titre", "type": "string", "required": True}]


def test_schema_endpoint_404_when_backing_table_gone(env):
    # Une collection enregistrée dont la table a été droppée depuis (hors du
    # cœur, ex. migration manuelle) ne doit pas faire 500 : /schema retourne
    # 404, pas une exception d'introspection non mappée.
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    def gone_introspector(session, table_name):
        raise TableNotFound(table_name)

    app.dependency_overrides[collections_routes.get_introspector] = lambda: gone_introspector
    r = client.get("/collections/incidents/schema")
    assert r.status_code == 404
    assert r.json()["detail"] == "backing table not found"


def test_schema_endpoint_409_when_backing_table_unsupported(env):
    # Idem si la table backing existe encore mais a été altérée en une forme
    # que l'introspecteur ne sait plus lire (ex. colonne géométrie retirée).
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    from app.collections.introspection import UnsupportedTable

    def unsupported_introspector(session, table_name):
        raise UnsupportedTable("no geometry column")

    app.dependency_overrides[collections_routes.get_introspector] = lambda: unsupported_introspector
    r = client.get("/collections/incidents/schema")
    assert r.status_code == 409
    assert r.json()["detail"] == "no geometry column"


def test_patch_and_delete(env):
    app, client, Session, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    r = client.patch("/collections/incidents", json={"title": "Renommé", "isPublic": True})
    assert r.status_code == 200 and r.json()["title"] == "Renommé"
    _as(app, regular)
    assert client.delete("/collections/incidents").status_code == 403
    _as(app, admin)
    assert client.delete("/collections/incidents").status_code == 204
    assert client.get("/collections/incidents").status_code == 404


def test_patch_by_non_owner_without_editor_role_returns_403(env):
    # patch_collection's own "write access required" 403 branch
    # (app/collections/routes.py) had no test at all before this review —
    # test_patch_and_delete only exercises the DELETE guard
    # (require_privilege(admin.collections.manage), a different check). A
    # user who can read the (public) collection but
    # has no editor share and isn't admin must be refused the PATCH.
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": True})
    _as(app, regular)
    r = client.patch("/collections/incidents", json={"title": "Hijacked"})
    assert r.status_code == 403
    assert r.json()["detail"] == "write access required"


def test_mutations_are_audited(env):
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch("/collections/incidents", json={"title": "X"})
    client.delete("/collections/incidents")
    from sqlalchemy import select

    from app.audit.models import AuditLog

    with Session() as s:
        actions = list(s.scalars(select(AuditLog.action)))
    for expected in ("collection.create", "collection.update", "collection.delete"):
        assert expected in actions


def test_canWrite_reflects_the_requesting_users_write_access(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post(
        "/collections", json={"tableName": "incidents", "title": "Incidents", "isPublic": True}
    )

    # admin (propriétaire de la collection qu'il vient de créer) : write=True
    assert client.get("/collections/incidents").json()["permissions"]["write"] is True
    assert client.get("/collections").json()["collections"][0]["permissions"]["write"] is True

    # regular : lisible car isPublic=True (comme un viewer), mais aucun rôle
    # editor sur le groupe de partage de la collection → write=False
    _as(app, regular)
    assert client.get("/collections/incidents").json()["permissions"]["write"] is False
    assert client.get("/collections").json()["collections"][0]["permissions"]["write"] is False


def test_patch_collection_enqueues_embedding_only_when_title_or_description_change(
    env, monkeypatch
):
    # Évite un recalcul inutile d'embedding sur un simple toggle isPublic/
    # editable (brief SP-7 Task 7, patch_collection) : l'enqueue ne doit se
    # déclencher que si le titre ou la description ont effectivement changé.
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "title": "Incidents"})

    deferred = []
    monkeypatch.setattr(
        repo,
        "enqueue_embedding",
        lambda collection_id, tenant_id: deferred.append((collection_id, tenant_id)),
    )

    # Ni titre ni description : pas d'enqueue.
    r = client.patch("/collections/incidents", json={"isPublic": True})
    assert r.status_code == 200
    assert deferred == []

    # Titre inchangé (même valeur) : pas d'enqueue.
    r = client.patch("/collections/incidents", json={"title": "Incidents"})
    assert r.status_code == 200
    assert deferred == []

    # Titre réellement modifié : enqueue.
    r = client.patch("/collections/incidents", json={"title": "Incidents voirie"})
    assert r.status_code == 200
    assert deferred == [("incidents", admin.tenant_id)]


def test_list_collections_accepts_q_param_without_error(env):
    app, client, Session, admin, regular, _ddl = env
    _as(app, regular)
    with Session() as s:
        repo.create_collection(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            table_name="c1",
            title="Communes",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column=None,
            geometry_type=None,
            srid=None,
        )
        s.commit()
    resp = client.get("/collections?q=commun")
    assert resp.status_code == 200
    # SQLite (route de test) : repli ILIKE, "commun" est une sous-chaîne de "Communes".
    assert [c["title"] for c in resp.json()["collections"]] == ["Communes"]

    # Preuve que `q` est bien câblé jusqu'à list_visible_collections (et pas
    # seulement accepté puis ignoré par FastAPI comme paramètre inconnu) :
    # une requête qui ne matche ni le titre ni la description doit filtrer
    # la collection, pas la laisser passer.
    resp = client.get("/collections?q=xyzzy-no-match")
    assert resp.status_code == 200
    assert resp.json()["collections"] == []


def test_candidates_requires_admin(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, regular)
    assert client.get("/collections/candidates").status_code == 403


def test_candidates_lists_registrable_and_unsupported_excludes_core_and_registered(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # already registered

    def fake_lister(session):
        return ["incidents", "widgets", "items"]  # "items" is a core table

    def fake_introspector_2(session, table_name):
        if table_name == "incidents":
            return INCIDENTS
        if table_name == "widgets":
            raise UnsupportedTable("table has no primary key")
        raise TableNotFound(table_name)

    app.dependency_overrides[collections_routes.get_table_lister] = lambda: fake_lister
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector_2

    r = client.get("/collections/candidates")
    assert r.status_code == 200
    assert r.json()["candidates"] == [
        {"tableName": "widgets", "registrable": False, "reason": "table has no primary key"},
    ]


def test_list_collections_includes_owner_username(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    body = client.get("/collections").json()
    assert body["collections"][0]["owner"] == "admin"
