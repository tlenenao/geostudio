# SPDX-License-Identifier: Apache-2.0
"""ARC-27 sur PostGIS réel : import XLSForm -> collection + App mobile, saisie validée par les
règles/domaines importés, « mes saisies », soumission publique (ARC-10)."""

import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import db
from app.attachments import routes as attachments_routes
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.public_submit import service
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user
from tests.test_xlsform_parser import _thirty

pytestmark = pytest.mark.postgis


class _S3:
    def __getattr__(self, _name):
        return lambda *a, **k: {}


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
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
        other = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="b",
            username="bob",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="r",
            username="lect",
            email=None,
            first_name="",
            last_name="",
        )
        from app.roles.repository import ensure_built_in_roles
        from app.users.models import User

        roles = ensure_built_in_roles(s, tenant_id=tenant.id)
        ru = s.get(User, reader.id)
        ru.role_id = roles["reader"].id
        ru.is_admin = False
        s.commit()
        users = {"admin": admin, "bob": other, "reader": reader}
        for u in users.values():
            s.refresh(u)
            s.expunge(u)
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: _S3()
    service.ip_limiter.reset()
    client = TestClient(app)

    def as_(name):
        if name is None:
            app.dependency_overrides.pop(get_current_user, None)
            app.dependency_overrides.pop(get_current_user_optional, None)
        else:
            app.dependency_overrides[get_current_user] = lambda: users[name]
            app.dependency_overrides[get_current_user_optional] = lambda: users[name]

    as_("admin")
    yield client, Session, as_
    service.ip_limiter.reset()
    with pg_engine.begin() as conn:
        tables = conn.execute(
            text("SELECT table_name FROM collections WHERE table_name LIKE 'query_%'")
        ).scalars()
        for t in list(tables):
            conn.execute(text(f'DROP TABLE IF EXISTS "{t}"'))
        conn.execute(
            text(
                "TRUNCATE submissions, submission_tokens, entity_history, notifications, "
                "collection_shares, collections, items, configs, audit_log, users, tenants CASCADE"
            )
        )


def _import(client, content=None, name="form.xlsx"):
    return client.post(
        "/v1/xlsform/import",
        files={
            "file": (
                name,
                content or _thirty(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            )
        },
    )


def _feature(**props):
    base = {"nom": "Banc", "age": 30, "etat": "bon"}
    return {
        "type": "Feature",
        "properties": {**base, **props},
        "geometry": {"type": "Point", "coordinates": [2.35, 48.85]},
    }


def test_import_creates_collection_and_mobile_form_app(env):
    client, Session, _as = env
    r = _import(client)
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["title"] == "Inspection des bancs"
    assert not [x for x in body["report"] if x["code"] == "not_ported"]
    col = client.get(f"/v1/collections/{body['collectionId']}").json()
    assert col["geometryType"] in ("Point", "ST_Point") or "Point" in str(col["geometryType"])
    assert col["fieldDomains"]["etat"] == {"type": "list", "values": ["bon", "degrade", "hs"]}
    assert {r["field"] for r in col["attributeRules"]} == {"age", "surface"}
    assert col["attachmentFields"] == [{"key": "photo", "label": "Photo"}]
    cfg = client.get(f"/v1/configs/by-item/{body['itemId']}").json()
    form = cfg["config"]["layout"]["items"][0]
    assert form["widget"] == "form" and form["props"]["mobile"] is True
    assert form["props"]["showMyEntries"] is True
    motif = next(f for f in form["props"]["fields"] if f["name"] == "motif")
    assert motif["visibleWhen"] == "etat == 'degrade'"


def test_imported_rules_and_domains_are_enforced_on_write(env):
    client, _S, _as = env
    cid = _import(client).json()["collectionId"]
    ok = client.post(f"/v1/collections/{cid}/items", json=_feature())
    assert ok.status_code == 201, ok.text
    bad_age = client.post(f"/v1/collections/{cid}/items", json=_feature(age=200))
    assert bad_age.status_code == 400 and "Âge entre 0 et 120" in bad_age.text
    bad_dom = client.post(f"/v1/collections/{cid}/items", json=_feature(etat="inconnu"))
    assert bad_dom.status_code == 400


def test_my_entries_lists_only_my_own_creations(env):
    client, _S, as_ = env
    cid = _import(client).json()["collectionId"]
    client.post(f"/v1/collections/{cid}/items", json=_feature(nom="de admin"))
    as_("bob")
    client.post(f"/v1/collections/{cid}/items", json=_feature(nom="de bob"))
    mine = client.get(f"/v1/collections/{cid}/my-entries").json()["entries"]
    assert [e["properties"]["nom"] for e in mine] == ["de bob"]
    as_("admin")
    mine = client.get(f"/v1/collections/{cid}/my-entries").json()["entries"]
    assert [e["properties"]["nom"] for e in mine] == ["de admin"]
    as_("reader")
    assert client.get(f"/v1/collections/{cid}/my-entries").status_code in (403, 404)


def test_import_requires_data_manage_and_rejects_bad_files(env):
    client, _S, as_ = env
    assert _import(client, b"not a workbook").status_code == 422
    assert _import(client, b"x" * (2 * 1024 * 1024 + 10)).status_code == 422
    as_("reader")
    assert _import(client).status_code == 403


def test_public_submission_via_arc10_on_imported_collection(env):
    client, Session, as_ = env
    cid = _import(client).json()["collectionId"]
    assert client.patch(f"/v1/collections/{cid}", json={"isPublic": True}).status_code == 200
    tok = client.post(
        f"/v1/collections/{cid}/submission-tokens",
        json={"name": "terrain", "expiresInDays": 7, "maxSubmissions": 5},
    )
    assert tok.status_code == 201, tok.text
    as_(None)
    r = client.post(
        f"/v1/public/submit/{tok.json()['token']}",
        data={"payload": json.dumps(_feature())},
    )
    assert r.status_code == 202, r.text
    with Session() as s:
        from app.public_submit.models import Submission

        assert s.scalars(select(Submission.status)).all() == ["pending"]
