# SPDX-License-Identifier: Apache-2.0
"""ARC-10 : soumission publique modérée sur PostGIS réel (critères d'acceptation)."""

import io
import json
import pathlib

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import db
from app.attachments import routes as attachments_routes
from app.audit.models import AuditLog
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.notifications.models import Notification
from app.public_submit import service
from app.public_submit.models import Submission, SubmissionToken
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis

MARK = "ZZ-PENDING-MARK"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64


class _S3:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self.puts = 0

    def put_object(self, *, Bucket, Key, Body, ContentType=None):
        self.puts += 1
        self.objects[Key] = Body

    def get_object(self, *, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[Key])}

    def delete_object(self, *, Bucket, Key):
        self.objects.pop(Key, None)

    def list_objects_v2(self, **_kw):
        return {"Contents": [], "IsTruncated": False}

    def __getattr__(self, _name):  # create_bucket, put_bucket_lifecycle... : sans effet
        return lambda *a, **k: {}


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_sub"))
        conn.execute(
            text(
                "CREATE TABLE demo_sub (id serial PRIMARY KEY, "
                "nom text NOT NULL, categorie text, gravite integer, surface double precision, "
                "geom geometry(Point, 4326))"
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
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    s3 = _S3()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[attachments_routes.get_s3_client] = lambda: s3
    service.ip_limiter.reset()
    service.token_limiter.reset()
    client = TestClient(app)
    yield client, app, admin, Session, s3
    service.ip_limiter.reset()
    service.token_limiter.reset()
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS demo_sub"))
        conn.execute(
            text(
                "TRUNCATE submissions, submission_tokens, notifications, collection_shares, "
                "collections, audit_log, users, tenants CASCADE"
            )
        )


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def _anon(app):
    app.dependency_overrides.pop(get_current_user, None)
    app.dependency_overrides.pop(get_current_user_optional, None)


@pytest.fixture()
def ready(pg_app):
    client, app, admin, Session, s3 = pg_app
    _as(app, admin)
    assert client.post("/v1/collections", json={"tableName": "demo_sub"}).status_code == 201
    r = client.patch(
        "/v1/collections/demo_sub",
        json={"isPublic": True, "attachmentFields": [{"key": "photo", "label": "Photo"}]},
    )
    assert r.status_code == 200, r.text
    tok = client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "formulaire mairie", "expiresInDays": 30, "maxSubmissions": 5},
    )
    assert tok.status_code == 201, tok.text
    return client, app, admin, Session, s3, tok.json()


def _payload(nom=MARK):
    return json.dumps(
        {
            "type": "Feature",
            "properties": {"nom": nom},
            "geometry": {"type": "Point", "coordinates": [1, 45]},
        }
    )


def _submit(client, token, nom=MARK, **extra):
    return client.post(
        f"/v1/public/submit/{token}",
        data={"payload": _payload(nom), **extra.pop("data", {})},
        **extra,
    )


def test_token_is_shown_once_and_stored_hashed(ready):
    client, _app, _a, Session, _s3, tok = ready
    assert tok["token"].startswith("gss_")
    with Session() as s:
        row = s.scalars(select(SubmissionToken)).one()
        assert row.token_hash != tok["token"] and tok["token"] not in row.token_hash
    listed = client.get("/v1/collections/demo_sub/submission-tokens").json()["tokens"]
    assert "token" not in listed[0] and listed[0]["prefix"] == tok["prefix"]


def test_anonymous_submit_is_pending_and_invisible_on_every_read_twin(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    r = _submit(client, tok["token"])
    assert r.status_code == 202 and r.json() == {"status": "pending"}
    # Jumelles de lecture, en anonyme sur une collection publique : la soumission
    # en attente n'apparaît nulle part (REST, tuiles MVT, STAC, DCAT).
    items = client.get("/v1/collections/demo_sub/items")
    assert items.status_code == 200 and MARK not in items.text
    assert items.json().get("numberMatched", 0) == 0
    tile = client.get("/v1/collections/demo_sub/tiles/0/0/0.mvt")
    assert MARK.encode() not in tile.content
    stac = client.get("/v1/stac/collections/demo_sub/items")
    assert MARK not in stac.text
    search = client.get("/v1/stac/search")
    assert MARK not in search.text
    dcat = client.get("/v1/dcat/catalog")
    assert MARK not in dcat.text
    # Table de la collection : aucune ligne (donc rien pour export/MCP/DuckDB/CDC/moissonnage).
    with Session() as s:
        assert s.scalar(text("SELECT count(*) FROM demo_sub")) == 0
        assert s.scalars(select(Submission.status)).all() == ["pending"]
        assert s.scalar(text("SELECT feature_count FROM collections")) == 0


def test_rls_invariant_no_core_table_granted_to_rls_roles(pg_app):
    _c, _app, _a, Session, _s3 = pg_app
    with Session() as s:
        for role in ("gis_rls", "gis_rls_masked"):
            for table in ("submissions", "submission_tokens"):
                granted = s.scalar(
                    text("SELECT has_table_privilege(:r, :t, 'SELECT')"), {"r": role, "t": table}
                )
                assert granted is False, f"{role} ne doit pas lire {table}"


def test_only_whitelisted_modules_touch_the_staging_table():
    """Garde structurelle des jumelles (MCP, DuckDB/lac, moissonnage, exports, STAC,
    DCAT, tuiles) : aucun chemin de lecture des features ne référence la file."""
    allowed = {"public_submit", "compliance", "db.py", "main.py"}
    root = pathlib.Path(__file__).resolve().parent.parent / "app"
    offenders = []
    for path in root.rglob("*.py"):
        rel = path.relative_to(root)
        if rel.parts[0] in allowed or rel.name in allowed:
            continue
        if "public_submit" in path.read_text():
            offenders.append(str(rel))
    assert offenders == []


def test_honeypot_returns_success_and_stores_nothing(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    r = _submit(client, tok["token"], data={"website": "http://spam.example"})
    assert r.status_code == 202
    with Session() as s:
        assert s.scalars(select(Submission)).all() == []
        assert s.scalar(select(SubmissionToken.submission_count)) == 0


def test_unknown_token_404_expired_410_revoked_410(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    assert _submit(client, "gss_" + "0" * 12 + "_nope").status_code == 404
    with Session() as s:
        row = s.scalars(select(SubmissionToken)).one()
        row.expires_at = row.created_at.replace(year=2000)
        s.commit()
    assert _submit(client, tok["token"]).status_code == 410
    _as(app, ready[2])
    fresh = client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "b", "expiresInDays": 1, "maxSubmissions": 1},
    ).json()
    assert (
        client.delete(f"/v1/collections/demo_sub/submission-tokens/{fresh['id']}").status_code
        == 204
    )
    _anon(app)
    assert _submit(client, fresh["token"]).status_code == 410


def test_token_quota_is_enforced(ready):
    client, app, admin, _S, _s3, _tok = ready
    one = client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "q", "expiresInDays": 1, "maxSubmissions": 2},
    ).json()
    _anon(app)
    assert [_submit(client, one["token"]).status_code for _ in range(3)] == [202, 202, 429]


def test_21st_request_per_minute_per_ip_is_429(ready):
    # AUD-154 : budget par minute partagé (middleware), avant tout parsing multipart.
    client, app, _a, _S, _s3, tok = ready
    _anon(app)
    codes = [_submit(client, "gss_" + "1" * 12 + "_bad").status_code for _ in range(20)]
    assert set(codes) == {404}
    assert _submit(client, tok["token"]).status_code == 429


def test_101st_request_per_hour_per_ip_is_429(ready):
    # Compteur horaire par IP (ADR 0017) ; le client de test se présente "testclient".
    client, app, _a, _S, _s3, tok = ready
    _anon(app)
    for _ in range(100):
        assert service.ip_limiter.allow("testclient")
    r = _submit(client, tok["token"])
    assert r.status_code == 429 and r.json()["detail"] == "too many submissions, retry later"


def test_request_over_the_hourly_token_budget_is_429_whatever_the_ip(ready):
    # AUD-154 : budget horaire par jeton, même réparti sur plusieurs IP (simulées ici en
    # consommant le compteur du jeton, l'IP du client de test étant fixe).
    client, app, _a, _S, _s3, tok = ready
    _anon(app)
    assert service.token_limiter.limit == 1000  # revue SP-L2 I4 : défaut relevé
    for _ in range(service.token_limiter.limit):
        assert service.token_limiter.allow(tok["token"])
    r = _submit(client, tok["token"])
    assert r.status_code == 429 and "this form" in r.json()["detail"]


def test_invalid_payload_is_rejected_without_consuming_quota(ready):
    client, app, _a, Session, _s3, tok = ready
    _anon(app)
    r = client.post(f"/v1/public/submit/{tok['token']}", data={"payload": "{pas du json"})
    assert r.status_code == 400
    r = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": '{"type":"Feature","properties":{"inconnu":1},"geometry":null}'},
    )
    assert r.status_code == 400
    with Session() as s:
        assert s.scalar(select(SubmissionToken.submission_count)) == 0
    # revue SP-L2 I4 : le compteur horaire du jeton n'est pas consommé non plus
    assert not service.token_limiter._hits.get(tok["token"])
    assert _submit(client, tok["token"]).status_code == 202
    assert len(service.token_limiter._hits[tok["token"]]) == 1


def test_attachment_type_is_controlled_by_content_and_size_capped(ready):
    client, app, _a, Session, s3, tok = ready
    _anon(app)
    bad = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("photo.png", b"<html>pas une image</html>", "image/png")},
    )
    assert bad.status_code == 415  # l'en-tête déclaré ne compte pas, le contenu oui
    exe = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("x.exe", PNG, "image/png")},
    )
    assert exe.status_code == 400
    big = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("big.png", PNG + b"\x00" * (25 * 1024 * 1024), "image/png")},
    )
    assert big.status_code == 413
    ok = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert ok.status_code == 202
    assert len(s3.objects) == 1
    with Session() as s:
        assert s.scalar(select(SubmissionToken.submission_count)) == 1


def test_moderators_are_notified_and_approve_inserts_with_audit(ready):
    client, app, admin, Session, s3, tok = ready
    _anon(app)
    ok = client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert ok.status_code == 202
    with Session() as s:
        notes = s.scalars(select(Notification)).all()
        assert [(n.kind, n.recipient_user_id) for n in notes] == [("submission", admin.id)]
    _as(app, admin)
    queue = client.get("/v1/collections/demo_sub/submissions").json()["submissions"]
    assert len(queue) == 1 and queue[0]["properties"] == {"nom": MARK}
    sid = queue[0]["id"]
    att = client.get(f"/v1/collections/demo_sub/submissions/{sid}/attachment")
    assert att.status_code == 200 and att.content == PNG
    done = client.post(f"/v1/collections/demo_sub/submissions/{sid}/approve")
    assert done.status_code == 200, done.text
    fid = done.json()["fid"]
    # Une fois approuvée, la donnée est une feature ordinaire ET sa pièce jointe est rattachée.
    got = client.get(f"/v1/collections/demo_sub/items/{fid}")
    assert got.status_code == 200 and got.json()["properties"]["nom"] == MARK
    atts = client.get(f"/v1/collections/demo_sub/items/{fid}/attachments").json()["attachments"]
    assert len(atts) == 1
    hist = client.get(f"/v1/collections/demo_sub/items/{fid}/history").json()["versions"]
    assert [v["op"] for v in hist] == ["create"]
    with Session() as s:
        actions = [a.action for a in s.scalars(select(AuditLog).order_by(AuditLog.id))]
        assert "submission.create" in actions and "submission.approve" in actions
        sub = s.scalars(select(Submission)).one()
        assert sub.status == "approved" and sub.payload == {} and sub.moderated_by == admin.id
    assert client.post(f"/v1/collections/demo_sub/submissions/{sid}/approve").status_code == 409
    assert client.get("/v1/collections/demo_sub/submissions").json()["submissions"] == []


def test_reject_erases_the_citizen_data_and_the_file(ready):
    client, app, admin, Session, s3, tok = ready
    _anon(app)
    client.post(
        f"/v1/public/submit/{tok['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("photo.png", PNG, "image/png")},
    )
    _as(app, admin)
    sid = client.get("/v1/collections/demo_sub/submissions").json()["submissions"][0]["id"]
    r = client.post(
        f"/v1/collections/demo_sub/submissions/{sid}/reject", json={"reason": "hors sujet"}
    )
    assert r.status_code == 204
    assert s3.objects == {}
    with Session() as s:
        sub = s.scalars(select(Submission)).one()
        assert sub.status == "rejected" and sub.payload == {} and sub.attachment_key is None
        assert s.scalar(text("SELECT count(*) FROM demo_sub")) == 0
        actions = [a.action for a in s.scalars(select(AuditLog))]
        assert "submission.reject" in actions


def test_moderation_requires_write_permission(ready):
    client, app, admin, Session, _s3, tok = ready
    _anon(app)
    assert client.get("/v1/collections/demo_sub/submissions").status_code in (401, 403)
    assert client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "x", "expiresInDays": 1, "maxSubmissions": 1},
    ).status_code in (401, 403)


RULES = {
    "fieldDomains": {"gravite": {"type": "range", "min": 1, "max": 5}},
    "subtypes": {
        "field": "categorie",
        "items": [{"value": "voirie", "label": "Voirie", "defaults": {"gravite": 3}}],
    },
    "attributeRules": [
        {
            "id": "surface",
            "kind": "calculation",
            "field": "surface",
            "mode": "derived",
            "expression": "double(gravite) * 2.0",
        },
        {
            "id": "pas-interdit",
            "kind": "constraint",
            "field": "nom",
            "expression": "nom != 'interdit'",
            "message": "nom interdit",
        },
    ],
}


def _submit_props(client, token, props):
    feat = {"type": "Feature", "properties": props, "geometry": None}
    return client.post(f"/v1/public/submit/{token}", data={"payload": json.dumps(feat)})


def test_attribute_rules_apply_at_deposit_and_approval(ready):
    """I1 : domaines/sous-types/règles ARC-13/14 au dépôt ET à l'approbation."""
    client, app, admin, Session, _s3, tok = ready
    _anon(app)
    # Déposées avant que les règles existent : à revalider à l'approbation.
    assert _submit_props(client, tok["token"], {"nom": "a", "gravite": 9}).status_code == 202
    assert _submit_props(client, tok["token"], {"nom": "interdit"}).status_code == 202
    ok = _submit_props(client, tok["token"], {"nom": "ok", "categorie": "voirie"})
    assert ok.status_code == 202
    _as(app, admin)
    assert client.patch("/v1/collections/demo_sub", json=RULES).status_code == 200
    _anon(app)
    # Au dépôt : hors domaine et contrainte CEL refusés.
    assert _submit_props(client, tok["token"], {"nom": "b", "gravite": 9}).status_code == 400
    assert _submit_props(client, tok["token"], {"nom": "interdit"}).status_code == 400
    _as(app, admin)
    queue = client.get("/v1/collections/demo_sub/submissions").json()["submissions"]
    by_nom = {s["properties"]["nom"]: s["id"] for s in queue}
    base = "/v1/collections/demo_sub/submissions"
    r = client.post(f"{base}/{by_nom['a']}/approve")
    assert r.status_code == 400 and r.json()["errors"][0]["code"] == "out_of_domain"
    r = client.post(f"{base}/{by_nom['interdit']}/approve")
    assert r.status_code == 400 and r.json()["errors"][0]["code"] == "constraint_violation"
    r = client.post(f"{base}/{by_nom['ok']}/approve")
    assert r.status_code == 200, r.text
    got = client.get(f"/v1/collections/demo_sub/items/{r.json()['fid']}").json()["properties"]
    assert got["gravite"] == 3 and got["surface"] == 6.0  # défaut de sous-type puis calcul


def test_exhausted_token_never_uploads_the_attachment(ready):
    """M4a : quota réservé avant l'envoi S3."""
    client, app, _admin, _S, s3, _tok = ready
    one = client.post(
        "/v1/collections/demo_sub/submission-tokens",
        json={"name": "q", "expiresInDays": 1, "maxSubmissions": 1},
    ).json()
    _anon(app)
    assert _submit(client, one["token"]).status_code == 202
    r = client.post(
        f"/v1/public/submit/{one['token']}",
        data={"payload": _payload(), "fieldKey": "photo"},
        files={"file": ("photo.png", PNG, "image/png")},
    )
    assert r.status_code == 429
    assert s3.puts == 0
