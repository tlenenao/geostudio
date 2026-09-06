# SPDX-License-Identifier: Apache-2.0
"""SP-42 / F-securite-autorisation-01 (critical) : POST/PUT /configs et
POST/PUT /configs/by-item/{id} ne consultaient jusqu'ici aucun privilège —
un rôle prédéfini « Lecteur » (0 privilège) obtenait 201 sur POST /configs
pour n'importe quel kind. Ce fichier prouve que chaque kind exige désormais
le privilège de domaine correspondant (app.configs.routes::_KIND_PRIVILEGE),
et que le rôle « Créateur » (qui porte déjà ces privilèges) n'est pas
régressé.
"""

import pytest
from fastapi import Depends
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session as SASession

from app import db
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig
from app.db import get_session, init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        creator = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="creator-sub",
            username="creator",
            email=None,
            first_name="",
            last_name="",
        )
        assert creator.role_id == roles["creator"].id  # défaut de get_or_create_user
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="reader-sub",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=tenant.id,
            user_id=reader.id,
            role_id=roles["reader"].id,
            role_slug="reader",
        )
        assert roles["reader"].privileges == []
        collection = Collection(
            id="parcs",
            tenant_id=tenant.id,
            owner_id=creator.id,
            table_name="parcs",
            title="Parcs",
            pk_column="id",
            is_public=True,
            editable=True,
        )
        s.add(collection)
        s.commit()
        s.refresh(reader)

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    client.session_factory = Session  # type: ignore[attr-defined]
    return app, client, creator, reader


def _as(app, user):
    # Re-résout l'utilisateur depuis la session de LA requête à chaque appel
    # (comme le fait réellement app.auth.dependency.get_current_user) plutôt
    # que de fermer sur l'objet Python déjà chargé : un test qui modifie le
    # rôle de `user` en base entre deux appels doit voir cette modification
    # prise en compte, exactement comme un utilisateur réel dont le jeton
    # est revalidé à chaque requête.
    user_id = user.id

    def _get_current_user(session: SASession = Depends(get_session)) -> User:
        fresh = session.get(User, user_id)
        assert fresh is not None
        return fresh

    app.dependency_overrides[get_current_user] = _get_current_user


def _body(kind: str) -> dict:
    if kind == "app":
        return {"kind": "app", "layout": {"type": "grid", "items": []}}
    if kind == "map":
        return {
            "kind": "map",
            "map": {"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
        }
    if kind == "dataset":
        return {"kind": "dataset", "dataset": {"source": "collection", "collectionId": "parcs"}}
    if kind == "pipeline":
        return {
            "kind": "pipeline",
            "pipeline": {
                "nodes": [
                    {
                        "id": "r1",
                        "kind": "reader",
                        "op": "reader.collection",
                        "params": {"collectionId": "parcs"},
                    },
                    {
                        "id": "w1",
                        "kind": "writer",
                        "op": "writer.dataset",
                        "params": {"collectionId": "parcs", "title": "sortie"},
                    },
                ]
            },
        }
    if kind == "bookmark":
        return {"kind": "bookmark", "bookmark": {"appId": "does-not-matter", "pageId": "p1"}}
    if kind == "site":
        return {"kind": "site", "layout": {"type": "grid", "items": []}}
    if kind == "dashboard":
        return {"kind": "dashboard", "layout": {"type": "grid", "items": []}}
    if kind == "alert":
        return {
            "kind": "alert",
            "alert": {
                "datasetItemId": "does-not-matter",
                "query": {"agg": "count"},
                "condition": {"expr": "value > 100"},
                "refreshPolicy": {"enabled": True, "cron": "*/5 * * * *"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        }
    if kind == "report":
        return {
            "kind": "report",
            "report": {
                "bookmarkItemId": "does-not-matter",
                "refreshPolicy": {"enabled": True, "cron": "0 8 * * MON"},
                "channels": [{"kind": "webhook", "url": "https://example.test/hook"}],
            },
        }
    if kind == "tileset3d":
        return {
            "kind": "tileset3d",
            "tileset3d": {
                "sourceKey": "does-not-matter/city.zip",
                "tilesetJsonPath": "tileset.json",
                "totalBytes": 1234,
                "entryCount": 2,
            },
        }
    if kind == "terrain3d":
        return {
            "kind": "terrain3d",
            "terrain3d": {
                "sourceKey": "does-not-matter/dem.tif",
                "originalFilename": "dem.tif",
            },
        }
    raise AssertionError(f"unhandled kind in test helper: {kind}")


# SP-42, revue du lot de correctifs 1 (Important) : la version d'origine de
# ce test ne couvrait que 5 des 11 kinds du catalogue, et son cas
# "pipeline" passait pour la MAUVAISE raison — confirmé par le réviseur en
# neutralisant _require_privilege_for_kind : le 403 provenait en réalité de
# _require_etl_enabled_for_pipeline (CORE_ETL_ENABLED désactivé par défaut
# dans cet environnement de test), pas du nouveau garde de privilège. Même
# piège pour "report" (_require_export_enabled_for_report/
# CORE_EXPORT_ENABLED). Les deux capacités sont donc explicitement
# ACTIVÉES ici pour que seul le privilège manquant puisse produire le 403 —
# et les 6 kinds jusqu'ici non testés (alert/report/site/dashboard/
# tileset3d/terrain3d) sont ajoutés au paramétrage, couvrant les 11 kinds et
# les 5 privilèges de _KIND_PRIVILEGE.
@pytest.mark.parametrize(
    "kind",
    [
        "app",
        "map",
        "dataset",
        "pipeline",
        "bookmark",
        "site",
        "dashboard",
        "alert",
        "report",
        "tileset3d",
        "terrain3d",
    ],
)
def test_reader_without_any_privilege_is_denied_on_create(env, kind, monkeypatch):
    app, client, _creator, reader = env
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    monkeypatch.setenv("CORE_EXPORT_ENABLED", "true")
    _as(app, reader)
    resp = client.post("/v1/configs", json={"title": "x", "config": _body(kind)})
    assert resp.status_code == 403, resp.text


def test_creator_can_still_create_an_app_map_and_dataset_config(env, monkeypatch):
    app, client, creator, _reader = env
    _as(app, creator)
    for kind in ("app", "map", "dataset"):
        resp = client.post("/v1/configs", json={"title": f"x-{kind}", "config": _body(kind)})
        assert resp.status_code == 201, resp.text

    # pipeline reste gardé par la capacité instance CORE_ETL_ENABLED en plus
    # du privilège automation.manage — l'activer ici prouve que le Créateur
    # (qui porte déjà automation.manage) n'est pas bloqué par la nouvelle
    # garde de privilège une fois la capacité ouverte.
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    resp = client.post("/v1/configs", json={"title": "x-pipeline", "config": _body("pipeline")})
    assert resp.status_code == 201, resp.text


def test_demoted_owner_can_no_longer_update_their_own_app_config(env):
    app, client, creator, reader = env
    _as(app, creator)
    created = client.post("/v1/configs", json={"title": "x", "config": _body("app")}).json()
    config_id = created["id"]
    item_id = created["itemId"]

    # Rétrograde le propriétaire (creator) vers le rôle Lecteur directement
    # en base — l'objectif de ce test est le comportement de PUT /configs,
    # pas celui de PATCH /users (couvert par ailleurs, cf.
    # F-securite-autorisation-07/lot A-lockout).
    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        set_user_role(
            s,
            tenant_id=creator.tenant_id,
            user_id=creator.id,
            role_id=reader.role_id,
            role_slug="reader",
        )
        s.commit()

    _as(app, creator)
    resp = client.put(f"/v1/configs/{config_id}", json=_body("app"))
    assert resp.status_code == 403, resp.text

    resp_by_item = client.put(f"/v1/configs/by-item/{item_id}", json=_body("app"))
    assert resp_by_item.status_code == 403, resp_by_item.text


def test_analyst_can_create_and_reader_still_cannot_create_a_bookmark(env):
    # Revue du lot de correctifs 1 (Important), décision Tanguy : un
    # bookmark est une « vue analytique enregistrée » (spec SP-14m), portée
    # par analytics.view — pas catalog.manage (l'ancien mapping bloquait à
    # tort l'Analyste, seul rôle prédéfini dont le domaine est justement
    # l'Analytique). Preuve des deux côtés dans le même test : l'Analyste
    # obtient de nouveau 201, le Lecteur reste à 403.
    app, client, _creator, reader = env
    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=reader.tenant_id)
        assert Privilege.ANALYTICS_VIEW.value in roles["analyst"].privileges
        assert Privilege.ANALYTICS_VIEW.value not in roles["reader"].privileges
        analyst = get_or_create_user(
            s,
            tenant_id=reader.tenant_id,
            oidc_sub="analyst-sub",
            username="analyst",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=reader.tenant_id,
            user_id=analyst.id,
            role_id=roles["analyst"].id,
            role_slug="analyst",
        )
        # L'app ciblée par le bookmark appartient à l'Analyste lui-même, pour
        # que sa lisibilité ne dépende d'aucun partage/publication distinct
        # du seul point testé ici (le privilège sur kind="bookmark").
        item = items_repo.create_item(
            s,
            tenant_id=reader.tenant_id,
            owner_id=analyst.id,
            resource_type="app",
            title="Cible analyste",
        )
        s.commit()
        app_item_id = item.id

    bookmark_body = {
        "kind": "bookmark",
        "bookmark": {"appId": app_item_id, "pageId": "p1"},
    }

    with Session() as s:
        analyst = s.scalar(select(User).where(User.username == "analyst"))
    _as(app, analyst)
    resp = client.post("/v1/configs", json={"title": "vue analyste", "config": bookmark_body})
    assert resp.status_code == 201, resp.text

    _as(app, reader)
    resp = client.post("/v1/configs", json={"title": "vue reader", "config": bookmark_body})
    assert resp.status_code == 403, resp.text


def test_demoted_owner_can_no_longer_rollback_their_own_app_config(env):
    # Revue du lot de correctifs 1 (Important) : POST /configs/{id}/rollback
    # rejoue "exactement la même séquence que update_config" (son propre
    # commentaire) mais sautait _require_privilege_for_kind — un
    # utilisateur rétrogradé pouvait donc encore muter le contenu d'un item
    # en restaurant une ancienne version. Même montage que
    # test_demoted_owner_can_no_longer_update_their_own_app_config
    # ci-dessus, sur /rollback plutôt que PUT.
    app, client, creator, reader = env
    _as(app, creator)
    created = client.post("/v1/configs", json={"title": "x", "config": _body("app")}).json()
    config_id = created["id"]

    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        set_user_role(
            s,
            tenant_id=creator.tenant_id,
            user_id=creator.id,
            role_id=reader.role_id,
            role_slug="reader",
        )
        s.commit()

    _as(app, creator)
    resp = client.post(f"/v1/configs/{config_id}/rollback", json={"version": 1})
    assert resp.status_code == 403, resp.text


def test_analyst_cannot_escalate_privilege_by_submitting_a_different_kind_on_put(env):
    # SP-42, revue des lots de correctifs 2/3bis (point 3, Important) :
    # _require_privilege_for_kind se cale sur le kind SOUMIS dans la
    # requête, jamais sur celui déjà enregistré pour l'item — repo
    # .update_config ne compare (et ne mute) jamais Config.kind. Un Analyste
    # (qui ne porte que analytics.view/analytics.sql_lab.access/data.view/
    # tasks.view, pas maps.manage) propriétaire d'une map — donc `write`
    # dessus — pouvait écraser sa config en soumettant kind="bookmark" : la
    # garde consultait alors analytics.view (qu'il porte) au lieu de
    # maps.manage (qu'il ne porte pas). Créée directement via le repository,
    # pas via POST /configs (qui refuserait la création elle-même — ce test
    # cible la MISE À JOUR d'une config déjà existante).
    app, client, _creator, reader = env
    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=reader.tenant_id)
        assert Privilege.MAPS_MANAGE.value not in roles["analyst"].privileges
        assert Privilege.ANALYTICS_VIEW.value in roles["analyst"].privileges
        analyst = get_or_create_user(
            s,
            tenant_id=reader.tenant_id,
            oidc_sub="analyst-escalation-sub",
            username="analyst-escalation",
            email=None,
            first_name="",
            last_name="",
        )
        set_user_role(
            s,
            tenant_id=reader.tenant_id,
            user_id=analyst.id,
            role_id=roles["analyst"].id,
            role_slug="analyst",
        )
        item = items_repo.create_item(
            s,
            tenant_id=reader.tenant_id,
            owner_id=analyst.id,
            resource_type="map",
            title="Carte de l'analyste",
        )
        created = configs_repo.create_config(
            s,
            BuilderConfig(
                version=1,
                kind="map",
                map={"basemap": {"style": "streets"}, "view": {"center": [0, 0], "zoom": 1}},
            ),
            item_id=item.id,
            tenant_id=reader.tenant_id,
        )
        # Cible du bookmark : un app item que l'analyste possède lui-même
        # (lisible sans dépendre d'un partage distinct) — sans lui,
        # _validate_bookmark_payload rejetterait le payload en 422 "app not
        # found" AVANT même d'atteindre la mise à jour, masquant la vraie
        # question testée ici (le kind soumis peut-il diverger de celui de
        # l'item ?) derrière un 422 accidentel plutôt qu'un succès réel.
        bookmark_target = items_repo.create_item(
            s,
            tenant_id=reader.tenant_id,
            owner_id=analyst.id,
            resource_type="app",
            title="Cible du bookmark",
        )
        s.commit()
        config_id = created.id
        item_id = item.id
        analyst_id = analyst.id
        bookmark_target_id = bookmark_target.id

    with Session() as s:
        analyst = s.get(User, analyst_id)
        assert analyst is not None
    _as(app, analyst)

    bookmark_body = {
        "kind": "bookmark",
        "bookmark": {"appId": bookmark_target_id, "pageId": "p1"},
    }
    resp = client.put(f"/v1/configs/{config_id}", json=bookmark_body)
    assert resp.status_code == 400, resp.text

    resp_by_item = client.put(f"/v1/configs/by-item/{item_id}", json=bookmark_body)
    assert resp_by_item.status_code == 400, resp_by_item.text

    # Non-régression : la config de la map n'a pas bougé — toujours "map",
    # jamais écrasée par le "bookmark" refusé ci-dessus.
    with Session() as s:
        untouched = configs_repo.get_config(s, config_id)
        assert untouched is not None
        assert untouched.kind == "map"


def test_rollback_refuses_a_stored_revision_whose_kind_diverges_from_the_item(env):
    # Défense en profondeur, même point : Config.kind n'est jamais muté par
    # repo.update_config (vérifié par lecture directe du repository) — une
    # révision stockée dont le kind diverge de celui de l'item ne peut donc
    # apparaître qu'à travers un accès direct au repository (simulé ici) ou
    # une exploitation historique du même défaut, avant ce correctif.
    # /rollback ne doit pas la restaurer.
    app, client, creator, _reader = env
    _as(app, creator)
    created = client.post("/v1/configs", json={"title": "x", "config": _body("map")}).json()
    config_id = created["id"]

    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        configs_repo.update_config(
            s,
            config_id,
            BuilderConfig(version=1, kind="bookmark", bookmark={"appId": "x", "pageId": "p1"}),
            tenant_id=creator.tenant_id,
        )
        s.commit()

    _as(app, creator)
    resp = client.post(f"/v1/configs/{config_id}/rollback", json={"version": 2})
    assert resp.status_code == 400, resp.text


def test_editor_share_without_domain_privilege_cannot_delete_a_map(env):
    # SP-42, revue de la dernière passe de correctifs (point 6, Important) :
    # les trois routes DELETE (/configs/{id}, /configs/by-item/{id},
    # /items/{id}) ne consultaient que can()/_require_access(action="delete")
    # — un Lecteur (0 privilège) à qui une map est partagée en "editor"
    # obtient "editor" in roles => decide() autorise delete, sans jamais
    # consulter maps.manage. _require_privilege_for_kind consulte déjà le
    # kind ENREGISTRÉ (result.config) sur PUT — même garde requise ici.
    from app.sharing.models import Group, GroupMember, ItemShare

    app, client, creator, reader = env
    _as(app, creator)
    created = client.post("/v1/configs", json={"title": "x", "config": _body("map")}).json()
    config_id = created["id"]
    item_id = created["itemId"]

    Session = client.session_factory  # type: ignore[attr-defined]
    with Session() as s:
        group = Group(id="g1", tenant_id=creator.tenant_id, name="Editors", created_by=creator.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=reader.id, tenant_id=creator.tenant_id))
        s.add(
            ItemShare(
                item_id=item_id, group_id=group.id, tenant_id=creator.tenant_id, role="editor"
            )
        )
        s.commit()

    _as(app, reader)
    resp = client.delete(f"/v1/configs/{config_id}")
    assert resp.status_code == 403, resp.text
    resp_by_item = client.delete(f"/v1/configs/by-item/{item_id}")
    assert resp_by_item.status_code == 403, resp_by_item.text
    resp_item = client.delete(f"/v1/items/{item_id}")
    assert resp_item.status_code == 403, resp_item.text

    # Le créateur (maps.manage) peut toujours supprimer — non régressé.
    _as(app, creator)
    resp_owner = client.delete(f"/v1/items/{item_id}")
    assert resp_owner.status_code == 204, resp_owner.text
