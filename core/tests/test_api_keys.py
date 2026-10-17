# SPDX-License-Identifier: Apache-2.0
"""Clés d'API de service (ARC-06, ADR 0016) : critères d'acceptation du
comparatif §6.1.2 (expirée = 401, jamais au-delà du créateur, usage audité)
+ points sécurité (secret jamais relu, temps constant, révocation)."""

import hmac
from datetime import timedelta

import pytest
from fastapi import APIRouter, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select

from app import db
from app.apikeys import service
from app.apikeys.models import ApiKey
from app.apikeys.routes import router as apikeys_router
from app.audit.models import AuditLog
from app.auth.routes import router as auth_router
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.roles.repository import ensure_built_in_roles
from app.tenants.repository import get_or_create_default_tenant
from app.users.models import User
from app.users.repository import get_or_create_user, set_user_role


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")  # jeton non-clé -> mockuser
    monkeypatch.setenv("CORE_ENV", "development")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="adm",
            username="adm",
            email=None,
            first_name="",
            last_name="",
            bootstrap_admin=True,
        )
        reader = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="rd",
            username="rd",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
        ids = (tenant.id, admin.id, reader.id)
    # main.py est hors périmètre de la voie : routeurs montés ici, comme il le fera.
    app = FastAPI()
    v1 = APIRouter(prefix="/v1")
    v1.include_router(apikeys_router)
    v1.include_router(auth_router)
    app.include_router(v1)

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    return TestClient(app), Session, ids


def _mint(Session, user_id, days=30, **kw):
    with Session() as s:
        user = s.get(User, user_id)
        key, token = service.create_api_key(s, user=user, name="ci", expires_in_days=days, **kw)
        s.commit()
        return key.id, token


def _get(client, token, path="/v1/users"):
    return client.get(path, headers={"Authorization": f"Bearer {token}"})


def test_valid_key_acts_as_its_creator(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id)
    assert _get(client, token).status_code == 200


def test_unknown_malformed_and_tampered_keys_are_401(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id)
    for bad in (
        "gsk_",
        "gsk_nope",
        "gsk_" + "0" * 12 + "_x",
        token[:-1] + ("A" if token[-1] != "A" else "B"),
    ):
        r = _get(client, bad)
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid api key"


def test_expired_key_is_401(env):
    client, Session, (_, admin_id, _) = env
    key_id, token = _mint(Session, admin_id)
    with Session() as s:
        s.get(ApiKey, key_id).expires_at = service._utcnow() - timedelta(seconds=1)
        s.commit()
    assert _get(client, token).status_code == 401


def test_revoked_key_is_401_immediately(env):
    client, Session, (_, admin_id, _) = env
    key_id, token = _mint(Session, admin_id)
    assert _get(client, token).status_code == 200
    with Session() as s:
        service.revoke_api_key(s, user=s.get(User, admin_id), key_id=key_id)
        s.commit()
    assert _get(client, token).status_code == 401


def test_key_never_exceeds_creator_privileges(env):
    """Invariant : le statut d'une clé = celui de son créateur, à chaque requête."""
    client, Session, (tenant_id, admin_id, reader_id) = env
    _, reader_token = _mint(Session, reader_id)
    _, admin_token = _mint(Session, admin_id)
    assert _get(client, reader_token).status_code == 403  # lecteur : pas admin.users.manage
    assert _get(client, admin_token).status_code == 200
    # rétrogradation du créateur -> la clé perd aussitôt ses droits
    with Session() as s:
        roles = ensure_built_in_roles(s, tenant_id=tenant_id)
        set_user_role(
            s, tenant_id=tenant_id, user_id=admin_id, role_id=roles["reader"].id, role_slug="reader"
        )
        s.commit()
    assert _get(client, admin_token).status_code == 403


def test_erased_creator_key_is_401(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id)
    with Session() as s:
        from datetime import UTC, datetime

        s.get(User, admin_id).erased_at = datetime.now(UTC)
        s.commit()
    assert _get(client, token).status_code == 401


def test_anonymize_revokes_keys(env):
    from app.compliance.service import anonymize_user

    _, Session, (tenant_id, _, reader_id) = env
    key_id, _ = _mint(Session, reader_id)
    with Session() as s:
        anonymize_user(s, tenant_id=tenant_id, user_id=reader_id)
        s.commit()
        assert s.get(ApiKey, key_id).revoked_at is not None


def test_management_routes_create_list_revoke_and_secret_shown_once(env):
    client, Session, (_, admin_id, _) = env
    h = {"Authorization": "Bearer session-jwt"}  # mock : mockuser
    created = client.post("/v1/api-keys", json={"name": "ci", "expiresInDays": 30}, headers=h)
    assert created.status_code == 201
    body = created.json()
    assert body["token"].startswith("gsk_") and body["prefix"] == body["token"][:16]
    assert created.headers["cache-control"] == "no-store"
    listed = client.get("/v1/api-keys", headers=h)
    assert listed.status_code == 200
    assert body["token"] not in listed.text and "token" not in listed.json()[0]
    # le secret n'est ni en base en clair ni dans l'audit
    with Session() as s:
        assert body["token"] not in s.scalars(select(ApiKey.key_hash)).all()
        for row in s.scalars(select(AuditLog)):
            assert body["token"] not in str(row.payload)
    assert client.delete(f"/v1/api-keys/{body['id']}", headers=h).json()["revokedAt"]
    assert _get(client, body["token"]).status_code == 401
    assert client.delete("/v1/api-keys/nope", headers=h).status_code == 404


def test_lifetime_over_one_year_is_rejected(env):
    client, _, _ = env
    h = {"Authorization": "Bearer session-jwt"}
    assert (
        client.post("/v1/api-keys", json={"name": "x", "expiresInDays": 366}, headers=h).status_code
        == 422
    )
    assert (
        client.post("/v1/api-keys", json={"name": "x", "expiresInDays": 0}, headers=h).status_code
        == 422
    )


def test_a_key_cannot_manage_keys(env):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id)
    assert _get(client, token, "/v1/api-keys").status_code == 403
    r = client.post(
        "/v1/api-keys", json={"name": "x"}, headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 403


def test_keys_are_private_to_their_owner(env):
    client, Session, (_, admin_id, reader_id) = env
    key_id, _ = _mint(Session, reader_id)
    with Session() as s:
        assert service.revoke_api_key(s, user=s.get(User, admin_id), key_id=key_id) is None
        assert service.list_api_keys(s, user=s.get(User, admin_id)) == []


def test_usage_is_audited_and_throttled(env):
    client, Session, (_, admin_id, _) = env
    key_id, token = _mint(Session, admin_id)
    for _ in range(3):
        _get(client, token)
    with Session() as s:
        uses = s.scalars(select(AuditLog).where(AuditLog.action == "api_key.use")).all()
        assert len(uses) == 1 and uses[0].object_id == key_id and uses[0].actor_kind == "api_key"
        s.get(ApiKey, key_id).last_used_at = service._utcnow() - timedelta(minutes=5)
        s.commit()
    _get(client, token)
    with Session() as s:
        assert len(s.scalars(select(AuditLog).where(AuditLog.action == "api_key.use")).all()) == 2
        assert s.scalars(select(AuditLog).where(AuditLog.action == "api_key.create")).first()


def test_usage_audit_survives_a_rolled_back_request(env):
    # REV-367 e : une requête en erreur (rollback) n'annule plus last_used_at ni l'audit.
    _client, Session, (tenant_id, admin_id, _) = env
    key_id, token = _mint(Session, admin_id)
    with Session() as s:
        assert service.authenticate(s, token=token, tenant_id=tenant_id) is not None
        s.rollback()  # réponse en erreur : request_scoped_session annule la transaction
    with Session() as s:
        assert s.get(ApiKey, key_id).last_used_at is not None
        uses = s.scalars(select(AuditLog).where(AuditLog.action == "api_key.use")).all()
        assert [u.object_id for u in uses] == [key_id]


def test_hash_comparison_is_constant_time(env, monkeypatch):
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id)
    calls = []
    real = hmac.compare_digest
    monkeypatch.setattr(service.hmac, "compare_digest", lambda a, b: calls.append(1) or real(a, b))
    _get(client, token)
    _get(client, "gsk_" + "0" * 12 + "_unknownprefix")  # préfixe inconnu : compare quand même
    assert len(calls) == 2


def test_stored_value_is_a_sha256_not_the_token(env):
    _, Session, (_, admin_id, _) = env
    key_id, token = _mint(Session, admin_id)
    with Session() as s:
        key = s.get(ApiKey, key_id)
        assert key.key_hash == service._hash(token) and len(key.key_hash) == 64
        assert token not in (key.key_hash, key.key_prefix)


def test_scoped_key_is_capped_to_its_scopes(env):
    # AUD-091 : /v1/users exige admin.users.manage, hors de la portée de la clé.
    client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id, scopes=["maps.manage"])
    assert _get(client, token).status_code == 403
    _, full = _mint(Session, admin_id, scopes=["admin.users.manage"])
    assert _get(client, full).status_code == 200


def test_read_only_key_refuses_writes(env):
    # AUD-091 : une clé en lecture seule ne fait que des GET/HEAD/OPTIONS.
    client, Session, (_, admin_id, _) = env
    from fastapi import Depends

    from app.auth.dependency import get_current_user

    @client.app.post("/v1/_probe")
    def _probe(user: User = Depends(get_current_user)) -> dict:
        return {"ok": True}

    _, token = _mint(Session, admin_id, read_only=True)
    assert _get(client, token).status_code == 200
    headers = {"Authorization": f"Bearer {token}"}
    resp = client.post("/v1/_probe", headers=headers)
    assert resp.status_code == 403 and "read-only" in resp.json()["detail"]
    _, writer = _mint(Session, admin_id)
    assert client.post("/v1/_probe", headers={"Authorization": f"Bearer {writer}"}).json()["ok"]


def test_scopes_cannot_exceed_creator_privileges(env):
    # compliance.manage est exclu même du rôle Administrateur (SP-58).
    client, _, _ = env
    headers = {"Authorization": "Bearer mock"}
    denied = client.post(
        "/v1/api-keys", json={"name": "x", "scopes": ["compliance.manage"]}, headers=headers
    )
    assert denied.status_code == 403
    unknown = client.post("/v1/api-keys", json={"name": "x", "scopes": ["nope"]}, headers=headers)
    assert unknown.status_code == 422
    ok = client.post(
        "/v1/api-keys",
        json={"name": "x", "scopes": ["maps.manage"], "readOnly": True},
        headers=headers,
    )
    assert ok.status_code == 201
    assert ok.json()["scopes"] == ["maps.manage"] and ok.json()["readOnly"] is True


@pytest.mark.parametrize(
    ("method", "path"),
    [
        ("post", "/v1/items/i1/share-links"),
        ("post", "/v1/pipelines/i1/webhook-tokens"),
        ("post", "/v1/roles"),
        ("patch", "/v1/roles/r1"),
        ("delete", "/v1/roles/r1"),
        ("patch", "/v1/users/u1"),
        ("post", "/v1/compliance/users/me/erase"),
    ],
)
def test_sensitive_routes_refuse_an_api_key(env, method, path, monkeypatch):
    # AUD-094 : jumelles de forbid_api_key, même avec une clé admin valide.
    _client, Session, (_, admin_id, _) = env
    from app.main import create_app

    monkeypatch.setenv("CORE_ETL_ENABLED", "true")  # monte le routeur pipelines
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    _, token = _mint(Session, admin_id)
    resp = getattr(TestClient(app), method)(path, headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403, resp.text
    assert resp.json()["detail"] == "not allowed with an api key"


def _real_client(Session):
    from app.main import create_app

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    return TestClient(app)


_READ_POSTS = [
    "/v1/collections/nope/aggregate",
    "/v1/datasets/nope/arcgis/aggregate",
]


def _assert_read_posts_pass_and_writes_refused(client, token):
    headers = {"Authorization": f"Bearer {token}"}
    for path in _READ_POSTS:
        resp = client.post(path, json={"measures": [{"op": "count"}]}, headers=headers)
        # l'authentification passe : la route répond sur la ressource (inconnue ici)
        assert resp.status_code not in (401, 403), (path, resp.text)
        assert resp.json().get("detail") != "Not Found", path  # la route existe
    write = client.post(
        "/v1/collections/nope/items",
        json={"type": "Feature", "geometry": None, "properties": {}},
        headers=headers,
    )
    assert write.status_code == 403 and "read-only" in write.json()["detail"], write.text


def test_read_only_key_can_post_marked_reads_but_not_write(env):
    # C1 revue SP-L2 : agrégats en POST = lectures explicitement autorisées.
    _client, Session, (_, admin_id, _) = env
    _, token = _mint(Session, admin_id, read_only=True)
    _assert_read_posts_pass_and_writes_refused(_real_client(Session), token)


def test_scoped_admin_key_loses_the_collection_admin_bypass(env):
    # I1 revue SP-L2 : actor_is_admin=user.is_admin contournait la portée de la
    # clé. Clé d'un admin sans admin.collections.manage : plus d'écriture sur
    # la collection d'autrui, ni par OGC Features ni par import (ajout).
    from app.collections import repository as collections_repo

    _client, Session, (tenant_id, admin_id, reader_id) = env
    with Session() as s:
        collections_repo.create_collection(
            s,
            tenant_id=tenant_id,
            owner_id=reader_id,
            table_name="incidents",
            title="Incidents",
            description="",
            is_public=True,
            pk_column="id",
            geometry_column="geom",
            geometry_type="POINT",
            srid=4326,
        )
        s.commit()
    from app.ingestion import routes as ingestion_routes

    client = _real_client(Session)
    client.app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: object()

    def attempts(token):
        from fastapi import HTTPException

        from app.features.routes import _get_writable

        headers = {"Authorization": f"Bearer {token}"}
        # écriture OGC : même garde que POST/PUT/PATCH/DELETE .../items (l'introspection
        # PostGIS qui la suit n'existe pas sous SQLite) ; la clé est résolue comme en HTTP.
        with Session() as s:
            user = service.authenticate(s, token=token, tenant_id=tenant_id)
            try:
                _get_writable(s, user, "incidents")
                feature_detail = None
            except HTTPException as exc:
                feature_detail = exc.detail
        upload = client.post(
            "/v1/uploads",
            json={
                "key": f"uploads/{tenant_id}/x.geojson",
                "filename": "x.geojson",
                "collectionTitle": "x",
                "collectionId": "incidents",
            },
            headers=headers,
        )
        return [feature_detail, upload.json().get("detail")]

    _, scoped = _mint(Session, admin_id, scopes=["data.view", "data.manage"])
    assert attempts(scoped) == ["write access required", "write access required"]
    _, full = _mint(Session, admin_id)
    assert "write access required" not in attempts(full)


def test_export_token_can_post_marked_reads_but_not_write(env, monkeypatch):
    # C1 revue SP-L2 : le rendu PDF des widgets lit ses agrégats en POST.
    from app.auth.export_tokens import mint_export_token

    _client, Session, (tenant_id, admin_id, _) = env
    monkeypatch.setenv("CORE_EXPORT_TOKEN_SECRET", "test-export-secret-padding-01234")
    monkeypatch.delenv("CORE_AUTH_MODE")  # la branche jeton d'export suit la branche mock
    token = mint_export_token(tenant_id=tenant_id, user_id=admin_id, job_id="j", item_id="i")
    _assert_read_posts_pass_and_writes_refused(_real_client(Session), token)
