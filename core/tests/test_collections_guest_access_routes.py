# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import repository as collections_repo
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.collections.models import Collection
from app.collections.routes import get_readable_collection
from app.configs.guest_access import GuestActor
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def session_factory():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    yield make_session_factory(engine)
    engine.dispose()


def _create_private_collection(session, *, tenant_id, owner_id, collection_id):
    col = Collection(
        id=collection_id,
        tenant_id=tenant_id,
        owner_id=owner_id,
        table_name=collection_id,
        title=collection_id,
        description="",
        pk_column="id",
        editable=True,
        is_public=False,
    )
    session.add(col)
    session.flush()
    return col


def _guest(tenant_id, *, allowed=("incidents",), created_by="owner-1") -> GuestActor:
    return GuestActor(
        tenant_id=tenant_id,
        item_id="app-1",
        share_link_id="link-1",
        created_by=created_by,
        allowed_item_ids=frozenset({"app-1"}),
        allowed_collection_ids=frozenset(allowed),
    )


def test_guest_with_allowed_collection_bypasses_can_when_its_creator_may_read_it(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        col = get_readable_collection(
            session, None, "incidents", guest=_guest(tenant.id, created_by=owner.id)
        )

        assert col.id == "incidents"


def test_guest_whose_creator_cannot_read_the_referenced_collection_gets_404(session_factory):
    """Trouvaille de la revue finale de branche GAP-19, démontrée par PoC :
    appartenir à `guest.allowed_collection_ids` (la config de l'App choisit
    librement ses `dataSources`) ne suffisait pas — un auteur de config
    pouvait faire figurer n'importe quelle collection privée du tenant,
    qu'il ait lui-même le droit de la lire ou non, et un jeton invité pour
    CETTE App donnait alors accès à la collection d'un tiers sans rapport.
    Ce test aurait dû être écrit à la Tâche 2 (le critère d'acceptation
    « portée == référencée » ne teste que l'inverse : une collection non
    référencée) ; corrigé ici plutôt que silencieusement, per CLAUDE.md
    piège n°3."""
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        stranger = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="s",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        # "incidents" appartient à `owner`, jamais partagée avec `stranger` —
        # mais `stranger` a créé le lien de partage d'une App dont la config
        # référence "incidents" quand même (auteur de config != propriétaire
        # de la collection référencée).
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session,
                None,
                "incidents",
                guest=_guest(tenant.id, created_by=stranger.id),
            )
        assert exc_info.value.status_code == 404


def test_guest_without_the_collection_in_scope_still_gets_404(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="secret"
        )
        session.commit()

        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session,
                None,
                "secret",
                guest=_guest(tenant.id, allowed=("incidents",), created_by=owner.id),
            )
        assert exc_info.value.status_code == 404


def test_guest_uses_its_own_tenant_not_the_default_tenant(session_factory):
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        # guest.tenant_id volontairement erroné : la collection n'existe pas
        # dans ce tenant-là, même si "incidents" existe ailleurs.
        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session,
                None,
                "incidents",
                guest=GuestActor(
                    tenant_id="wrong-tenant",
                    item_id="app-1",
                    share_link_id="link-1",
                    created_by=owner.id,
                    allowed_item_ids=frozenset({"app-1"}),
                    allowed_collection_ids=frozenset({"incidents"}),
                ),
            )
        assert exc_info.value.status_code == 404


def test_guest_present_alongside_a_real_authenticated_user_never_triggers_the_bypass(
    session_factory,
):
    """I1 (revue finale de branche) : la résolution de tenant est déjà
    exclusive user/guest, mais le contournement can() lui-même tournait
    même quand un VRAI utilisateur authentifié était présent en même temps
    qu'un jeton invité (d'un tenant/App sans rapport) — un utilisateur
    authentifié doit systématiquement passer par can(), jamais par la
    portée d'un jeton invité qui l'accompagnerait par accident."""
    with session_factory() as session:
        tenant = get_or_create_default_tenant(session)
        owner = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        stranger = get_or_create_user(
            session,
            tenant_id=tenant.id,
            oidc_sub="s",
            username="stranger",
            email=None,
            first_name="",
            last_name="",
        )
        _create_private_collection(
            session, tenant_id=tenant.id, owner_id=owner.id, collection_id="incidents"
        )
        session.commit()

        # `stranger` est authentifié (paramètre `user`) ET présente, en même
        # temps, un jeton invité qui référence "incidents" — le jeton ne doit
        # jamais lui donner accès à une collection qu'il ne peut pas lire
        # lui-même via can().
        with pytest.raises(HTTPException) as exc_info:
            get_readable_collection(
                session,
                stranger,
                "incidents",
                guest=_guest(tenant.id, created_by=owner.id),
            )
        assert exc_info.value.status_code == 404


# --- Tâche 6 : GET /collections/{id} et /schema, bout en bout HTTP ---------
#
# Écart au texte du brief (piège CLAUDE.md n°3) : le brief enregistrait les
# collections via `POST /v1/collections`, qui dépend du VRAI introspecteur
# Postgres (`get_introspector` non overridé) pour lire une table qui doit
# réellement exister dans le schéma `public` — impossible à satisfaire sur le
# moteur sqlite en mémoire utilisé ici (RED pour la mauvaise raison : une
# introspection PG contre sqlite, pas l'absence de câblage `guest`). Corrigé
# en suivant le patron déjà éprouvé de `test_features_guest_access_routes.py`
# et `test_configs_guest_access_routes.py` : `collections_repo.create_collection()`
# direct + `collections_routes.get_introspector` overridé par un faux
# introspecteur en mémoire (nécessaire ici : `get_collection`/
# `get_collection_schema` appellent tous deux `introspect(...)`).

_ROUTE_SECRET = "test-collections-guest-access-routes-secret0"


def _route_table_info(table_name: str) -> TableInfo:
    return TableInfo(
        table_name=table_name,
        pk_column="id",
        geometry_column="geom",
        geometry_type="Point",
        srid=4326,
        columns=[ColumnInfo(name="titre", type="string", required=True)],
    )


def _fake_route_introspector(session, table_name):
    if table_name not in ("incidents", "other"):
        raise TableNotFound(table_name)
    return _route_table_info(table_name)


@pytest.fixture(autouse=True)
def share_link_secret(monkeypatch):
    monkeypatch.setenv("CORE_SHARE_LINK_TOKEN_SECRET", _ROUTE_SECRET)


@pytest.fixture()
def route_env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="o",
            username="owner",
            email=None,
            first_name="",
            last_name="",
        )
        for table_name in ("incidents", "other"):
            collections_repo.create_collection(
                s,
                tenant_id=tenant.id,
                owner_id=owner.id,
                table_name=table_name,
                title=table_name,
                description="",
                is_public=False,
                pk_column="id",
                geometry_column="geom",
                geometry_type="Point",
                srid=4326,
            )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[collections_routes.get_introspector] = lambda: _fake_route_introspector
    app.dependency_overrides[get_current_user] = lambda: owner
    app.dependency_overrides[get_current_user_optional] = lambda: owner
    client = TestClient(app)
    body = {
        "kind": "app",
        "dataSources": [
            {"id": "ds1", "type": "features", "service": "core", "layer": "incidents", "query": {}}
        ],
        "layout": {"type": "grid", "items": []},
    }
    item_id = client.post("/v1/configs", json={"title": "App", "config": body}).json()["itemId"]
    created = client.post(f"/v1/items/{item_id}/share-links", json={"ttlDays": 7}).json()
    token = created["url"].rsplit("/", 1)[-1]
    return app, client, token


def test_guest_token_reads_collection_metadata_and_schema(route_env):
    app, client, token = route_env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/incidents", headers={"X-Share-Link-Token": token})
    assert r.status_code == 200

    r2 = client.get("/v1/collections/incidents/schema", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 200


def test_guest_token_does_not_read_an_unreferenced_collection(route_env):
    app, client, token = route_env
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)

    r = client.get("/v1/collections/other", headers={"X-Share-Link-Token": token})
    assert r.status_code == 404

    r2 = client.get("/v1/collections/other/schema", headers={"X-Share-Link-Token": token})
    assert r2.status_code == 404
