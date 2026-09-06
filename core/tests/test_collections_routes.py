# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.attachments import repository as attachments_repo
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as repo
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound, UnsupportedTable
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
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


class _FakeS3Client:
    """Stub minimal pour collections_routes.get_s3_client (SP-42/
    F-securite-tenant-rls-03) : unregister_collection dépend désormais de
    get_s3_client pour purger les pièces jointes avant suppression, donc TOUT
    test de ce fichier qui appelle DELETE /collections/{id} a besoin de cet
    override — sinon RuntimeError("S3 client dependency not configured")."""

    def __init__(self):
        self.deleted: list[str] = []

    def delete_object(self, *, Bucket, Key):
        self.deleted.append(Key)


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
        lambda session, table, tenant_id=None: ddl_calls.append(table)
    )
    app.dependency_overrides[collections_routes.get_s3_client] = lambda: _FakeS3Client()
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


def test_list_collections_is_paginated(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)

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

    for i in range(150):
        resp = client.post("/collections", json={"tableName": f"t{i}"})
        assert resp.status_code == 201

    body = client.get("/collections").json()
    assert len(body["collections"]) == 100  # DEFAULT_LIMIT, pas 150
    assert body["numberMatched"] == 150
    assert body["numberReturned"] == 100

    body2 = client.get("/collections?limit=100&offset=100").json()
    assert len(body2["collections"]) == 50


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


def test_custom_role_with_collections_manage_sees_and_can_delete_a_private_collection(env):
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
        assert listed[0]["permissions"]["delete"] is True

        # La route DELETE laisse effectivement passer — le verdict n'est pas
        # un mensonge d'affichage (piège n°5/n°4 : chemin de lecture ET
        # d'écriture doivent être d'accord).
        assert client.delete("/collections/incidents").status_code == 204


def test_custom_role_with_collections_manage_reaches_schema_of_a_private_collection(env):
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

        # 200, pas 404 : can_manage_collections lève le voile de visibilité
        # exactement comme sur GET/PATCH/DELETE /collections/{id}.
        resp = client.get("/collections/incidents/schema")
        assert resp.status_code == 200
        assert resp.json()["pk"] == "id"


def test_custom_role_with_collections_manage_gets_honest_403_not_404_on_sharing(env):
    # can_manage_collections lève le voile de visibilité (get_readable_collection),
    # mais _require_share() (can(action="share", ...)) reste inchangé : un
    # porteur non-propriétaire du privilège reçoit un 403 honnête, pas un 404
    # confus — même patron que le garde d'écriture de patch_collection.
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

        assert client.get("/collections/incidents/sharing").status_code == 403
        assert (
            client.put(
                "/collections/incidents/sharing", json={"public": False, "groups": []}
            ).status_code
            == 403
        )


def test_private_collection_schema_and_sharing_404_without_privilege(env):
    # Contrepartie négative des deux tests ci-dessus (Gestionnaire de
    # collections → 200/403) : un utilisateur SANS ce privilège doit rester
    # 404 sur les trois mêmes routes, comme il l'est déjà sur la ressource de
    # base /collections/{id} (test_private_collection_hidden_from_stranger_
    # and_anonymous) — jamais vérifié explicitement pour /schema et /sharing.
    app, client, _, admin, regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # privée, admin owner

    _as(app, regular)
    assert client.get("/collections/incidents/schema").status_code == 404
    assert client.get("/collections/incidents/sharing").status_code == 404
    assert (
        client.put(
            "/collections/incidents/sharing", json={"public": False, "groups": []}
        ).status_code
        == 404
    )


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


def test_delete_collection_with_existing_attachment_returns_204_and_purges_it(env):
    # SP-42/F-securite-tenant-rls-03 : avant correctif, la FK
    # attachments.collection_id (sans ondelete) faisait échouer ce DELETE en
    # 500 dès qu'une pièce jointe existait — la collection restait
    # indésenregistrable, et l'objet S3 n'était de toute façon jamais purgé.
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    s3_key = f"{admin.tenant_id}/incidents/f1/a.jpg"
    with Session() as s:
        attachments_repo.create_attachment(
            s,
            tenant_id=admin.tenant_id,
            collection_id="incidents",
            fid="f1",
            field_key="photos",
            filename="a.jpg",
            content_type="image/jpeg",
            byte_size=10,
            s3_key=s3_key,
            created_by=admin.id,
        )
        s.commit()

    s3 = _FakeS3Client()
    app.dependency_overrides[collections_routes.get_s3_client] = lambda: s3

    response = client.delete("/collections/incidents")
    assert response.status_code == 204
    assert s3.deleted == [s3_key]

    with Session() as s:
        remaining = attachments_repo.list_attachments(
            s, tenant_id=admin.tenant_id, collection_id="incidents", fid="f1"
        )
        assert remaining == []


def test_delete_collection_refuses_when_a_dataset_still_references_it(env):
    # SP-42/F-coeur-contenu-04 : sans cette garde, supprimer une collection
    # encore référencée par un Dataset (dataset.collectionId) orphelinait ce
    # Dataset silencieusement (204, aucun signal).
    app, client, Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    with Session() as s:
        dataset_item = repo.get_collection(s, tenant_id=admin.tenant_id, collection_id="incidents")
        assert dataset_item is not None  # sanity : la collection existe bien
        from app.items import repository as items_repo

        item = items_repo.create_item(
            s,
            tenant_id=admin.tenant_id,
            owner_id=admin.id,
            resource_type="dataset",
            title="Dataset sur incidents",
        )
        dataset_config = BuilderConfig.model_validate(
            {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "incidents"}}
        )
        configs_repo.create_config(s, dataset_config, item_id=item.id, tenant_id=admin.tenant_id)
        s.commit()

    response = client.delete("/collections/incidents")
    assert response.status_code == 409
    assert "dataset" in response.json()["detail"]
    # la collection n'a pas été supprimée (refus, pas suppression partielle) :
    assert client.get("/collections/incidents").status_code == 200


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


def test_patch_collection_declares_attachment_fields(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents", json={"attachmentFields": [{"key": "photos", "label": "Photos"}]}
    )
    assert res.status_code == 200
    assert res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]

    get_res = client.get("/collections/incidents")
    assert get_res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]


def test_patch_collection_rejects_attachment_field_key_colliding_with_real_column(env):
    # SP-42/F-coeur-contenu-03 : "titre" est déjà une colonne SQL réelle de
    # INCIDENTS (fake_introspector) — sans cette garde, GET
    # /collections/incidents/schema exposerait deux champs "titre" (un
    # "string", un "attachment").
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents", json={"attachmentFields": [{"key": "titre", "label": "Photo"}]}
    )
    assert res.status_code == 422
    assert "titre" in res.json()["detail"]

    schema = client.get("/collections/incidents/schema").json()
    names = [f["name"] for f in schema["fields"]]
    assert names.count("titre") == 1


def test_patch_collection_rejects_duplicate_attachment_field_keys(env):
    # Collision entre deux entrées attachmentFields elles-mêmes (pas besoin
    # de DB, couvert par CollectionPatch._reject_duplicate_attachment_field_keys).
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents",
        json={
            "attachmentFields": [
                {"key": "photos", "label": "Photos"},
                {"key": "photos", "label": "Autres photos"},
            ]
        },
    )
    assert res.status_code == 422


def test_patch_collection_without_attachment_fields_leaves_them_unchanged(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch(
        "/collections/incidents", json={"attachmentFields": [{"key": "photos", "label": "Photos"}]}
    )

    res = client.patch("/collections/incidents", json={"title": "Nouveau titre"})
    assert res.status_code == 200
    assert res.json()["attachmentFields"] == [{"key": "photos", "label": "Photos"}]


def test_register_collection_defaults_attachment_fields_to_empty(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    res = client.post("/collections", json={"tableName": "incidents"})
    assert res.json()["attachmentFields"] == []


def test_register_collection_defaults_open_metadata_to_empty(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    res = client.post("/collections", json={"tableName": "incidents"})
    body = res.json()
    assert body["license"] == ""
    assert body["licenseUri"] == ""
    assert body["producer"] == ""
    assert body["contact"] == ""
    assert body["updateFrequency"] == ""
    assert body["lineage"] == ""
    assert body["language"] == "fr"
    assert body["version"] == ""
    assert body["temporalStart"] is None
    assert body["temporalEnd"] is None


def test_patch_collection_declares_open_metadata(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents",
        json={
            "license": "etalab-2.0",
            "producer": "Ma Régie",
            "contact": "contact@example.org",
            "updateFrequency": "monthly",
            "lineage": "Relevé terrain 2026",
            "language": "en",
            "version": "1.0",
            "temporalStart": "2020-01-01",
            "temporalEnd": "2026-12-31",
        },
    )
    assert res.status_code == 200
    body = res.json()
    assert body["license"] == "etalab-2.0"
    assert body["producer"] == "Ma Régie"
    assert body["contact"] == "contact@example.org"
    assert body["updateFrequency"] == "monthly"
    assert body["lineage"] == "Relevé terrain 2026"
    assert body["language"] == "en"
    assert body["version"] == "1.0"
    assert body["temporalStart"] == "2020-01-01"
    assert body["temporalEnd"] == "2026-12-31"

    get_res = client.get("/collections/incidents")
    assert get_res.json()["license"] == "etalab-2.0"


def test_patch_collection_with_other_license_requires_uri(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})

    res = client.patch(
        "/collections/incidents",
        json={"license": "other", "licenseUri": "https://example.org/my-license"},
    )
    assert res.status_code == 200
    assert res.json()["licenseUri"] == "https://example.org/my-license"


def test_patch_collection_rejects_unknown_license(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    res = client.patch("/collections/incidents", json={"license": "bogus"})
    assert res.status_code == 422


def test_patch_collection_rejects_unknown_language(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    res = client.patch("/collections/incidents", json={"language": "bogus"})
    assert res.status_code == 422


def test_patch_collection_without_open_metadata_leaves_it_unchanged(env):
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch("/collections/incidents", json={"license": "etalab-2.0"})

    res = client.patch("/collections/incidents", json={"title": "Nouveau titre"})
    assert res.status_code == 200
    assert res.json()["license"] == "etalab-2.0"


def test_patch_collection_can_clear_a_declared_temporal_extent(env):
    # Défaut de revue finale (SP-41) : temporalStart/temporalEnd sont typés
    # date | None sans représentation "vide" non-None distincte, donc "champ
    # omis" et "champ explicitement mis à null" valaient tous deux None côté
    # Python — un PATCH {"temporalStart": null} ne pouvait jamais effacer une
    # emprise déjà déclarée. C'est pourtant exactement le payload envoyé par
    # EditCollectionPanel du shell (`temporalStart: temporalStart || null`).
    app, client, _Session, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    client.patch(
        "/collections/incidents",
        json={"temporalStart": "2020-01-01", "temporalEnd": "2026-12-31"},
    )

    get_res = client.get("/collections/incidents")
    assert get_res.json()["temporalStart"] == "2020-01-01"
    assert get_res.json()["temporalEnd"] == "2026-12-31"

    clear_res = client.patch(
        "/collections/incidents",
        json={"temporalStart": None, "temporalEnd": None},
    )
    assert clear_res.status_code == 200

    final_res = client.get("/collections/incidents")
    assert final_res.json()["temporalStart"] is None
    assert final_res.json()["temporalEnd"] is None
