# Sonde d'audit c03 (lecture seule sur le dépôt) — jamais commitée.
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from app.pipelines import repository as pipelines_repo
from tests.test_pipeline_routes import _make_app, _promote_owner_to_admin, _seed_webhook_pipeline

REPO = Path(__file__).resolve()


def test_delete_pipeline_item_with_a_run(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    with client.session_factory() as s:
        pipelines_repo.create_run(s, tenant_id=client.tenant.id, pipeline_item_id=item_id)
        s.commit()
    try:
        r = client.delete(f"/v1/items/{item_id}")
        print("DELETE status (run):", r.status_code, r.text[:200])
    except Exception as exc:  # noqa: BLE001
        print("DELETE raised (run):", type(exc).__name__, str(exc).splitlines()[0])
        raise


def test_delete_pipeline_item_with_a_webhook_token(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    item_id = _seed_webhook_pipeline(client)
    _promote_owner_to_admin(client)
    assert client.post(f"/v1/pipelines/{item_id}/webhook-tokens").status_code in (200, 201)
    try:
        r = client.delete(f"/v1/items/{item_id}")
        print("DELETE status (token):", r.status_code, r.text[:200])
    except Exception as exc:  # noqa: BLE001
        print("DELETE raised (token):", type(exc).__name__, str(exc).splitlines()[0])
        raise


def _load_0030():
    path = Path("alembic/versions/0030_roles.py").resolve()
    spec = importlib.util.spec_from_file_location("m0030", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_0030_downgrade_maps_reader_to_creator():
    m = _load_0030()
    eng = create_engine("sqlite://")
    with eng.begin() as c:
        c.execute(text("CREATE TABLE tenants (id TEXT PRIMARY KEY)"))
        c.execute(text("CREATE TABLE roles (id TEXT PRIMARY KEY, tenant_id TEXT, name TEXT, slug TEXT, is_built_in BOOLEAN, privileges TEXT, created_at TIMESTAMP, updated_at TIMESTAMP)"))
        c.execute(text("CREATE TABLE users (id TEXT PRIMARY KEY, tenant_id TEXT, is_admin BOOLEAN, is_analyst BOOLEAN, role_id TEXT)"))
        c.execute(text("INSERT INTO tenants VALUES ('t1')"))
        m.seed_built_in_roles(c)
        reader_id = c.execute(text("SELECT id FROM roles WHERE slug='reader'")).scalar()
        c.execute(text("INSERT INTO users VALUES ('u-reader','t1',0,0,:r)"), {"r": reader_id})
        m.migrate_roles_to_booleans(c)
        row = c.execute(text("SELECT is_admin, is_analyst FROM users WHERE id='u-reader'")).one()
        print("after downgrade reader ->", tuple(row))
        # ré-upgrade : quel rôle reçoit l'ancien Lecteur ?
        c.execute(text("UPDATE users SET role_id=NULL"))
        m.migrate_users_to_roles(c)
        slug = c.execute(text("SELECT r.slug FROM users u JOIN roles r ON r.id=u.role_id WHERE u.id='u-reader'")).scalar()
        print("after downgrade+upgrade reader ->", slug)
        assert slug == "reader", f"reader devient {slug}"
