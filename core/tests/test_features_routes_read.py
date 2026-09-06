# SPDX-License-Identifier: Apache-2.0
import json
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.features import routes as features_routes
from app.features.repository import FeaturePage, FilterError
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

FEAT = {"type": "Feature", "id": 1, "geometry": None, "properties": {"titre": "a"}}


def fake_introspector(session, table_name):
    if table_name != "incidents":
        raise TableNotFound(table_name)
    return INFO


def make_fake_repo(matched=3):
    calls = {}

    def select_features(
        session, info, *, limit, offset, bbox=None, geom_intersects=None, filters=None
    ):
        calls.update(
            limit=limit, offset=offset, bbox=bbox, geom_intersects=geom_intersects, filters=filters
        )
        if filters and "inconnu" in filters:
            raise FilterError("inconnu", "unknown filter property 'inconnu'")
        return FeaturePage(features=[FEAT], number_matched=matched, number_returned=1)

    def get_feature(session, info, *, fid):
        return FEAT if fid == "1" else None

    return SimpleNamespace(select_features=select_features, get_feature=get_feature, calls=calls)


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
    fake_repo = make_fake_repo()
    app.dependency_overrides[features_routes.get_features_repo] = lambda: fake_repo
    # SQLite ne connaît ni SET LOCAL ROLE ni set_config : neutraliser le scope.
    app.dependency_overrides[features_routes.get_rls_scope] = lambda: features_routes.null_rls_scope
    client = TestClient(app)
    return app, client, admin, regular, fake_repo


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _register(app, client, admin, public=False):
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents", "isPublic": public})


def test_items_returns_feature_collection_with_links(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    r = client.get("/collections/incidents/items?limit=1&offset=1")
    assert r.status_code == 200
    body = r.json()
    assert body["type"] == "FeatureCollection"
    assert body["numberMatched"] == 3 and body["numberReturned"] == 1
    rels = {link["rel"]: link["href"] for link in body["links"]}
    assert "offset=2" in rels["next"] and "offset=0" in rels["prev"]
    assert repo.calls["limit"] == 1 and repo.calls["offset"] == 1


def test_limit_is_capped_not_rejected(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    assert client.get("/collections/incidents/items?limit=99999").status_code == 200
    assert repo.calls["limit"] == 1000


def test_filters_forwarded_and_unknown_is_400(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    client.get("/collections/incidents/items?titre=a&f=json")
    assert repo.calls["filters"] == {"titre": "a"}  # f/limit/offset/bbox réservés, exclus
    r = client.get("/collections/incidents/items?inconnu=x")
    assert r.status_code == 400
    assert r.json()["errors"][0]["code"] == "unknown_filter"


def test_bbox_parsing(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    client.get("/collections/incidents/items?bbox=0.5,44.5,1.5,45.5")
    assert repo.calls["bbox"] == (0.5, 44.5, 1.5, 45.5)
    assert client.get("/collections/incidents/items?bbox=zzz").status_code == 400


def test_geom_intersects_parsing(env):
    app, client, admin, _r, repo = env
    _register(app, client, admin)
    geom = {"type": "Point", "coordinates": [1.0, 2.0]}
    r = client.get("/collections/incidents/items", params={"geom_intersects": json.dumps(geom)})
    assert r.status_code == 200
    assert repo.calls["geom_intersects"] == geom
    r2 = client.get("/collections/incidents/items", params={"geom_intersects": "not-json"})
    assert r2.status_code == 400
    assert r2.json()["errors"][0]["code"] == "invalid_geom_intersects"


def test_single_feature_and_404(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin)
    assert client.get("/collections/incidents/items/1").json()["id"] == 1
    assert client.get("/collections/incidents/items/999").status_code == 404


def test_anonymous_reads_public_only(env):
    app, client, admin, _r, _repo = env
    _register(app, client, admin, public=False)
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    assert client.get("/collections/incidents/items").status_code == 404
    _register(app, client, admin, public=True)  # re-register échoue (409) mais PATCH ok :
    _as(app, admin)
    client.patch("/collections/incidents", json={"isPublic": True})
    app.dependency_overrides.pop(get_current_user)
    app.dependency_overrides.pop(get_current_user_optional)
    res = client.get("/collections/incidents/items")
    assert res.status_code == 200
    # Renforcement REV-077 (même défaut, second site trouvé par cette
    # spec) : sans cette ligne, une réponse à liste vide passait aussi.
    assert res.json()["numberReturned"] == 1
    assert res.json()["features"][0]["id"] == 1
