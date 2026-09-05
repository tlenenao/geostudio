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
from sqlalchemy.orm import Session as SASession

from app import db
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import get_session, init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
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
    raise AssertionError(f"unhandled kind in test helper: {kind}")


@pytest.mark.parametrize("kind", ["app", "map", "dataset", "pipeline", "bookmark"])
def test_reader_without_any_privilege_is_denied_on_create(env, kind):
    app, client, _creator, reader = env
    _as(app, reader)
    resp = client.post("/configs", json={"title": "x", "config": _body(kind)})
    assert resp.status_code == 403, resp.text


def test_creator_can_still_create_an_app_map_and_dataset_config(env, monkeypatch):
    app, client, creator, _reader = env
    _as(app, creator)
    for kind in ("app", "map", "dataset"):
        resp = client.post("/configs", json={"title": f"x-{kind}", "config": _body(kind)})
        assert resp.status_code == 201, resp.text

    # pipeline reste gardé par la capacité instance CORE_ETL_ENABLED en plus
    # du privilège automation.manage — l'activer ici prouve que le Créateur
    # (qui porte déjà automation.manage) n'est pas bloqué par la nouvelle
    # garde de privilège une fois la capacité ouverte.
    monkeypatch.setenv("CORE_ETL_ENABLED", "true")
    resp = client.post("/configs", json={"title": "x-pipeline", "config": _body("pipeline")})
    assert resp.status_code == 201, resp.text


def test_demoted_owner_can_no_longer_update_their_own_app_config(env):
    app, client, creator, reader = env
    _as(app, creator)
    created = client.post("/configs", json={"title": "x", "config": _body("app")}).json()
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
    resp = client.put(f"/configs/{config_id}", json=_body("app"))
    assert resp.status_code == 403, resp.text

    resp_by_item = client.put(f"/configs/by-item/{item_id}", json=_body("app"))
    assert resp_by_item.status_code == 403, resp_by_item.text
