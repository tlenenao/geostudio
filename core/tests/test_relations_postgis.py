# SPDX-License-Identifier: Apache-2.0
"""ARC-21 : relations entre collections sur PostGIS réel (ADR 0021)."""

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.collections import routes as collections_routes
from app.db import Base, make_session_factory, request_scoped_session
from app.history.models import EntityHistory
from app.main import create_app
from app.sharing.models import Group, GroupMember
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]]]}


class _S3:
    def delete_object(self, *, Bucket, Key):
        pass

    def list_objects_v2(self, **_kw):
        return {"Contents": [], "IsTruncated": False}

    def delete_objects(self, **_kw):
        return {}


def _f(props, x=5.0, y=5.0):
    return {
        "type": "Feature",
        "properties": props,
        "geometry": {"type": "Point", "coordinates": [x, y]},
    }


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE collection_relations, entity_history, collection_shares, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )
    tables = ("rel_liens", "rel_proprios", "rel_parcelles")
    with pg_engine.begin() as conn:
        for t in (*tables, "rel_proprios__rejected", "rel_parcelles__rejected"):
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        conn.execute(
            text(
                "CREATE TABLE rel_parcelles (id serial PRIMARY KEY, ref text, code text, "
                "geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE rel_proprios (id serial PRIMARY KEY, parcelle_id integer, "
                "nom text, tel text, geom geometry(Point, 4326))"
            )
        )
        conn.execute(
            text(
                "CREATE TABLE rel_liens (id serial PRIMARY KEY, parcelle_id integer, "
                "proprio_id integer, geom geometry(Point, 4326))"
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
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="reader",
            email=None,
            first_name="",
            last_name="",
        )
        group = Group(id=uuid.uuid4().hex, tenant_id=tenant.id, name="eq", created_by=admin.id)
        s.add(group)
        s.flush()
        s.add(GroupMember(group_id=group.id, user_id=reader.id, tenant_id=tenant.id))
        group_id = group.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    app.dependency_overrides[collections_routes.get_s3_client] = lambda: _S3()
    client = TestClient(app)

    def as_user(user):
        app.dependency_overrides[get_current_user] = lambda: user
        app.dependency_overrides[get_current_user_optional] = lambda: user

    as_user(admin)
    for t in tables:
        assert client.post("/v1/collections", json={"tableName": t}).status_code == 201
    for t in ("rel_parcelles", "rel_proprios"):
        r = client.put(f"/v1/collections/{t}/sharing", json={"public": True, "groups": []})
        assert r.status_code == 200, r.text
    yield client, as_user, admin, reader, group_id, Session
    with pg_engine.begin() as conn:
        for t in (*tables, "rel_proprios__rejected", "rel_parcelles__rejected"):
            conn.execute(text(f"DROP TABLE IF EXISTS {t}"))
        conn.execute(
            text(
                "TRUNCATE collection_relations, entity_history, collection_shares, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def _relation(client, **over):
    body = {
        "name": "proprietaires",
        "cardinality": "one_to_many",
        "parentCollectionId": "rel_parcelles",
        "childCollectionId": "rel_proprios",
        "childKey": "parcelle_id",
    }
    body.update(over)
    return client.post("/v1/relations", json=body)


def _seed(client):
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A1"})).json()["id"]
    owners = [
        client.post(
            "/v1/collections/rel_proprios/items",
            json=_f({"parcelle_id": pid, "nom": n, "tel": "0102"}),
        ).json()["id"]
        for n in ("Dupont", "Martin")
    ]
    return pid, owners


def _related(client, pid, rid, **params):
    return client.get(f"/v1/collections/rel_parcelles/items/{pid}/related/{rid}", params=params)


def test_master_detail_parcel_to_owners_and_back(env):
    client, *_ = env
    rid = _relation(client).json()["id"]
    pid, owners = _seed(client)
    body = _related(client, pid, rid).json()
    assert body["direction"] == "children" and body["collectionId"] == "rel_proprios"
    assert sorted(f["properties"]["nom"] for f in body["features"]) == ["Dupont", "Martin"]
    assert body["numberMatched"] == 2
    back = client.get(f"/v1/collections/rel_proprios/items/{owners[0]}/related/{rid}").json()
    assert back["direction"] == "parents"
    assert [f["properties"]["ref"] for f in back["features"]] == ["A1"]
    listed = client.get("/v1/collections/rel_parcelles/relations").json()
    assert [r["name"] for r in listed] == ["proprietaires"]


def test_restrict_blocks_deletion_then_allows_when_children_gone(env):
    client, *_ = env
    _relation(client)
    pid, owners = _seed(client)
    r = client.delete(f"/v1/collections/rel_parcelles/items/{pid}")
    assert r.status_code == 409
    assert client.get(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 200
    for o in owners:
        assert client.delete(f"/v1/collections/rel_proprios/items/{o}").status_code == 204
    assert client.delete(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 204


def test_cascade_deletes_children_journaled_and_counted(env):
    client, _as, _a, _r, _g, Session = env
    _relation(client, onDelete="cascade")
    pid, owners = _seed(client)
    assert client.delete(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 204
    for o in owners:
        assert client.get(f"/v1/collections/rel_proprios/items/{o}").status_code == 404
    with Session() as s:
        ops = s.scalars(
            select(EntityHistory.op).where(EntityHistory.collection_id == "rel_proprios")
        ).all()
        assert ops.count("delete") == 2  # journal ARC-15 des enfants supprimés en cascade
        n = s.execute(
            text("SELECT feature_count FROM collections WHERE id = 'rel_proprios'")
        ).scalar()
        assert n == 0


def test_cascade_refused_without_write_right_on_child(env):
    client, as_user, admin, reader, group_id, _S = env
    _relation(client, onDelete="cascade")
    pid, owners = _seed(client)
    # le groupe du lecteur édite le parent, mais ne fait que LIRE les propriétaires
    r = client.put(
        "/v1/collections/rel_parcelles/sharing",
        json={"public": True, "groups": [{"groupId": group_id, "role": "editor"}]},
    )
    assert r.status_code == 200, r.text
    as_user(reader)
    resp = client.delete(f"/v1/collections/rel_parcelles/items/{pid}")
    assert resp.status_code == 403
    as_user(admin)
    assert client.get(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 200
    assert client.get(f"/v1/collections/rel_proprios/items/{owners[0]}").status_code == 200


def test_unknown_parent_is_rejected_on_child_write(env):
    client, *_ = env
    _relation(client)
    r = client.post(
        "/v1/collections/rel_proprios/items", json=_f({"parcelle_id": 9999, "nom": "X"})
    )
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "relation_target_missing"
    pid, _ = _seed(client)
    ok = client.post("/v1/collections/rel_proprios/items", json=_f({"parcelle_id": pid}))
    assert ok.status_code == 201


def test_one_to_one_allows_a_single_child(env):
    client, *_ = env
    _relation(client, cardinality="one_to_one")
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A"})).json()["id"]
    first = client.post("/v1/collections/rel_proprios/items", json=_f({"parcelle_id": pid}))
    assert first.status_code == 201
    second = client.post("/v1/collections/rel_proprios/items", json=_f({"parcelle_id": pid}))
    assert second.status_code == 409
    # le même enfant peut être réécrit (PUT) sans se heurter à lui-même
    put = client.put(
        f"/v1/collections/rel_proprios/items/{first.json()['id']}",
        json=_f({"parcelle_id": pid, "nom": "ok"}),
    )
    assert put.status_code == 204


def test_sensitive_field_stays_masked_in_related_records(env):
    client, as_user, admin, reader, *_ = env
    client.patch("/v1/collections/rel_proprios", json={"sensitiveFields": ["tel"]})
    rid = _relation(client).json()["id"]
    pid, _ = _seed(client)
    as_user(reader)
    feats = _related(client, pid, rid).json()["features"]
    assert len(feats) == 2 and all("tel" not in f["properties"] for f in feats)
    as_user(admin)
    feats = _related(client, pid, rid).json()["features"]
    assert all(f["properties"]["tel"] == "0102" for f in feats)


def test_sensitive_key_refused_at_declaration(env):
    client, *_ = env
    client.patch("/v1/collections/rel_proprios", json={"sensitiveFields": ["parcelle_id"]})
    assert _relation(client).status_code == 422


def test_unreadable_child_collection_is_invisible_to_reader(env):
    client, as_user, admin, reader, *_ = env
    rid = _relation(client).json()["id"]
    pid, _ = _seed(client)
    client.put("/v1/collections/rel_proprios/sharing", json={"public": False, "groups": []})
    as_user(reader)
    assert _related(client, pid, rid).status_code == 404
    assert client.get("/v1/collections/rel_parcelles/relations").json() == []


def test_geo_limit_of_child_collection_applies_to_related_records(env):
    client, as_user, admin, reader, group_id, _S = env
    rid = _relation(client).json()["id"]
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A"})).json()["id"]
    for nom, x in (("in", 5.0), ("out", 50.0)):
        client.post(
            "/v1/collections/rel_proprios/items",
            json=_f({"parcelle_id": pid, "nom": nom}, x=x, y=x),
        )
    r = client.put(
        f"/v1/collections/rel_proprios/geo-limits/group/{group_id}", json={"geometry": SQUARE}
    )
    assert r.status_code == 200, r.text
    as_user(reader)
    feats = _related(client, pid, rid).json()["features"]
    assert [f["properties"]["nom"] for f in feats] == ["in"]


def test_many_to_many_through_link_collection(env):
    client, *_ = env
    rid = _relation(
        client,
        name="coproprietaires",
        cardinality="many_to_many",
        childKey=None,
        linkCollectionId="rel_liens",
        linkParentKey="parcelle_id",
        linkChildKey="proprio_id",
    )
    assert rid.status_code == 201, rid.text
    rid = rid.json()["id"]
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A"})).json()["id"]
    a = client.post("/v1/collections/rel_proprios/items", json=_f({"nom": "A"})).json()["id"]
    b = client.post("/v1/collections/rel_proprios/items", json=_f({"nom": "B"})).json()["id"]
    for o in (a, b):
        client.post(
            "/v1/collections/rel_liens/items", json=_f({"parcelle_id": pid, "proprio_id": o})
        )
    body = _related(client, pid, rid).json()
    assert sorted(f["properties"]["nom"] for f in body["features"]) == ["A", "B"]
    back = client.get(f"/v1/collections/rel_proprios/items/{a}/related/{rid}").json()
    assert back["direction"] == "parents" and len(back["features"]) == 1
    # restrict : des liens existent -> 409
    assert client.delete(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 409


def test_declaration_requires_write_on_both_collections_and_same_tenant(env):
    client, as_user, admin, reader, *_ = env
    as_user(reader)
    assert _relation(client).status_code in (403, 404)
    as_user(admin)
    assert _relation(client, childCollectionId="nope").status_code == 404
    assert _relation(client, childKey=None).status_code == 422
    assert _relation(client).status_code == 201
    assert _relation(client).status_code == 409  # nom déjà pris


def test_delete_relation_then_parent_deletion_is_free(env):
    client, *_ = env
    rid = _relation(client).json()["id"]
    pid, _ = _seed(client)
    assert client.delete(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 409
    assert client.delete(f"/v1/relations/{rid}").status_code == 204
    assert client.delete(f"/v1/collections/rel_parcelles/items/{pid}").status_code == 204


def test_bulk_replace_guard_reports_blocking_relation(env):
    from app.collections import repository as collections_repo
    from app.relations.service import restricting_relation

    client, _as, admin, _r, _g, Session = env
    _relation(client)
    with Session() as s:
        col = collections_repo.get_collection(
            s, tenant_id=admin.tenant_id, collection_id="rel_parcelles"
        )
        assert restricting_relation(s, col) is None  # aucun enfant
    _seed(client)
    with Session() as s:
        col = collections_repo.get_collection(
            s, tenant_id=admin.tenant_id, collection_id="rel_parcelles"
        )
        assert restricting_relation(s, col) == "proprietaires"
