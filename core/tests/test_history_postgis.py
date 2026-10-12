# SPDX-License-Identifier: Apache-2.0
"""ARC-15 : journal d'entité sur PostGIS réel (critères d'acceptation du comparatif)."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.compliance.service import anonymize_user
from app.db import Base, make_session_factory, request_scoped_session
from app.history import service as history
from app.history.models import EntityHistory
from app.main import create_app
from app.roles.privileges import Privilege
from app.roles.repository import create_role
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


class _S3:
    def delete_object(self, *, Bucket, Key):
        pass


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_hist"))
        conn.execute(
            text(
                "CREATE TABLE demo_hist (id serial PRIMARY KEY, "
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
        role = create_role(
            s, tenant_id=tenant.id, name="limited", privileges=[Privilege.DATA_VIEW.value]
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
        limited.role_id = role.id
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    client = TestClient(app)
    yield client, app, admin, limited, Session
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_hist"))
        conn.execute(
            text(
                "TRUNCATE entity_history, roles, collection_shares, collections, audit_log, "
                "users, tenants CASCADE"
            )
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _feature(nom, salary, x=1.0):
    return {
        "type": "Feature",
        "properties": {"nom": nom, "salary": salary},
        "geometry": {"type": "Point", "coordinates": [x, 45.0]},
    }


@pytest.fixture()
def seeded(pg_app):
    client, app, admin, limited, Session = pg_app
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "demo_hist"}).status_code == 201
    client.patch(
        "/v1/collections/demo_hist", json={"sensitiveFields": ["salary"], "isPublic": True}
    )
    fid = client.post("/v1/collections/demo_hist/items", json=_feature("A", 100)).json()["id"]
    assert (
        client.put(
            f"/v1/collections/demo_hist/items/{fid}", json=_feature("B", 200, 2.0)
        ).status_code
        == 204
    )
    return client, app, admin, limited, Session, fid


def test_put_then_history_has_two_versions_with_author(seeded):
    client, app, admin, _l, _S, fid = seeded
    r = client.get(f"/v1/collections/demo_hist/items/{fid}/history")
    assert r.status_code == 200
    versions = r.json()["versions"]
    assert [v["op"] for v in versions] == ["update", "create"]  # plus récent d'abord
    assert versions[0]["actor"]["username"] == "admin"
    assert versions[0]["before"]["properties"]["nom"] == "A"
    assert versions[0]["after"]["properties"]["nom"] == "B"
    assert versions[1]["before"] is None and versions[1]["after"]["properties"]["nom"] == "A"


def test_changes_since_returns_only_the_delta(seeded):
    client, app, admin, _l, Session, fid = seeded
    with Session() as s:
        last = s.scalars(select(EntityHistory).order_by(EntityHistory.id.desc())).first()
        since = last.created_at.isoformat() + "Z"
    client.put(f"/v1/collections/demo_hist/items/{fid}", json=_feature("C", 300))
    r = client.get("/v1/collections/demo_hist/changes", params={"since": since})
    assert r.status_code == 200
    changes = r.json()["changes"]
    assert len(changes) == 1 and changes[0]["after"]["properties"]["nom"] == "C"
    everything = client.get(
        "/v1/collections/demo_hist/changes", params={"since": "2000-01-01T00:00:00Z"}
    ).json()["changes"]
    assert len(everything) == 3


def test_masked_field_stays_masked_in_history(seeded):
    client, app, admin, limited, _S, fid = seeded
    admin_view = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()
    assert admin_view["versions"][0]["after"]["properties"]["salary"] == 200
    _as(app, limited)
    body = client.get(f"/v1/collections/demo_hist/items/{fid}/history")
    assert body.status_code == 200
    for v in body.json()["versions"]:
        for snap in (v["before"], v["after"]):
            if snap:
                assert "salary" not in snap["properties"]
    changes = client.get(
        "/v1/collections/demo_hist/changes", params={"since": "2000-01-01T00:00:00Z"}
    ).json()["changes"]
    assert all("salary" not in (c["after"] or {"properties": {}})["properties"] for c in changes)


def test_anonymization_erases_author_from_journal(seeded):
    client, app, admin, limited, Session, fid = seeded
    # un second auteur : l'utilisateur « limited » devient propriétaire d'une écriture
    with Session() as s:
        s.add(
            EntityHistory(
                tenant_id=admin.tenant_id,
                collection_id="demo_hist",
                fid=fid,
                op="update",
                before=None,
                after=None,
                actor_id=limited.id,
            )
        )
        s.commit()
        anonymize_user(s, tenant_id=limited.tenant_id, user_id=limited.id, actor_id=admin.id)
        s.commit()
        rows = s.scalars(select(EntityHistory).where(EntityHistory.fid == str(fid))).all()
    assert all(r.actor_id != limited.id for r in rows)
    assert any(r.actor_id is None for r in rows)
    versions = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()["versions"]
    assert versions[0]["actor"] is None


def test_restore_a_version_rewrites_and_is_journaled(seeded):
    client, app, admin, _l, _S, fid = seeded
    versions = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()["versions"]
    create_id = versions[-1]["id"]
    r = client.post(f"/v1/collections/demo_hist/items/{fid}/history/{create_id}/restore")
    assert r.status_code == 204
    cur = client.get(f"/v1/collections/demo_hist/items/{fid}").json()
    assert cur["properties"]["nom"] == "A" and cur["properties"]["salary"] == 100
    latest = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()["versions"][0]
    assert latest["op"] == "restore"


def test_delete_is_journaled_and_not_restorable(seeded):
    client, app, admin, _l, _S, fid = seeded
    assert client.delete(f"/v1/collections/demo_hist/items/{fid}").status_code == 204
    versions = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()["versions"]
    assert versions[0]["op"] == "delete" and versions[0]["after"] is None
    assert versions[0]["before"]["properties"]["nom"] == "B"
    r = client.post(f"/v1/collections/demo_hist/items/{fid}/history/{versions[0]['id']}/restore")
    assert r.status_code == 409


def test_failed_write_leaves_no_journal_row(seeded):
    client, app, admin, _l, Session, fid = seeded
    bad = {"type": "Feature", "properties": {"salary": 1}, "geometry": None}  # `nom` manquant
    assert client.put(f"/v1/collections/demo_hist/items/{fid}", json=bad).status_code == 400
    with Session() as s:
        assert len(s.scalars(select(EntityHistory)).all()) == 2


def test_quota_keeps_only_the_latest_versions(seeded, monkeypatch):
    client, app, admin, _l, Session, fid = seeded
    monkeypatch.setattr(history, "MAX_VERSIONS_PER_ENTITY", 3)
    for i in range(5):
        client.put(f"/v1/collections/demo_hist/items/{fid}", json=_feature(f"n{i}", i))
    versions = client.get(f"/v1/collections/demo_hist/items/{fid}/history").json()["versions"]
    assert len(versions) == 3
    assert versions[0]["after"]["properties"]["nom"] == "n4"


def test_retention_purges_old_rows(seeded):
    client, app, admin, _l, Session, fid = seeded
    from datetime import UTC, datetime, timedelta

    with Session() as s:
        s.execute(text("UPDATE entity_history SET created_at = now() - interval '400 days'"))
        s.commit()
        n = history.purge_expired(s, now=datetime.now(UTC) + timedelta(seconds=1))
        s.commit()
    assert n == 2
