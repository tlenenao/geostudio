"""Tests reproducteurs (audit lot 3). Chaque test échoue tant que le bug existe."""

import json
from pathlib import Path

import pytest
from sqlalchemy import text

from app.db import Base, make_session_factory
from app.harvest.models import HarvestRecord
from app.ingestion.importer import run_import
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s,
            tenant_id=tenant.id,
            oidc_sub="a",
            username="alice",
            email=None,
            first_name="",
            last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                "TRUNCATE items, configs, config_revisions, collections, "
                "audit_log, users, tenants CASCADE"
            )
        )


def _import(env, filename, content):
    Session, tenant, user = env
    with Session() as s:
        res = run_import(
            s,
            tenant_id=tenant.id,
            created_by=user.id,
            filename=filename,
            content=content,
            collection_title="T",
            lat_field=None,
            lon_field=None,
        )
        s.commit()
        return res


@pytest.mark.postgis
def test_embedding_defer_happens_after_commit(env, pg_engine, monkeypatch):
    from app.items.jobs import embed_item_task

    Session, tenant, user = env
    seen = {}

    def fake_defer(**kw):
        # le worker voit l'item via une AUTRE connexion
        with pg_engine.connect() as c:
            seen["visible"] = (
                c.execute(
                    text("SELECT count(*) FROM items WHERE id=:i"), {"i": kw["item_id"]}
                ).scalar()
                == 1
            )

    monkeypatch.setattr(embed_item_task, "defer", fake_defer)
    with Session() as s:
        items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="x"
        )
        s.commit()
    assert seen["visible"] is True


def test_harvest_record_collection_fk_has_ondelete():
    fk = next(iter(HarvestRecord.__table__.c.collection_id.foreign_keys))
    assert fk.ondelete in ("SET NULL", "CASCADE")


def test_vector_index_is_not_ivfflat_built_on_empty_table():
    versions = [
        p for p in (ROOT / "alembic" / "versions").glob("*.py") if not p.name.startswith("0012_")
    ]
    src = "\n".join(p.read_text() for p in versions).lower()
    assert "hnsw" in src or "reindex" in src


@pytest.mark.postgis
@pytest.mark.xfail(
    strict=True, reason="REV-audit: en-tête CSV avec espace -> bind param tronqué (importer.py:304)"
)
def test_csv_header_with_space_imports(env):
    res = _import(env, "c.csv", b"Code postal,lat,lon\n19000,45.1,1.5\n")
    assert res.collection_id


@pytest.mark.postgis
@pytest.mark.xfail(
    strict=True, reason="REV-audit: propriété 'id' GeoJSON collisionne avec la PK (parsers.py:464)"
)
def test_geojson_property_id_imports(env):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": 1},
                "geometry": {"type": "Point", "coordinates": [1, 2]},
            }
        ],
    }
    res = _import(env, "a.geojson", json.dumps(gj).encode())
    assert res.collection_id


@pytest.mark.postgis
@pytest.mark.xfail(
    strict=True, reason="REV-audit: géométrie Z rejetée par colonne 2D (importer.py:322)"
)
def test_geojson_3d_point_imports(env):
    gj = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"n": "a"},
                "geometry": {"type": "Point", "coordinates": [1, 2, 3]},
            }
        ],
    }
    res = _import(env, "z.geojson", json.dumps(gj).encode())
    assert res.collection_id


@pytest.mark.postgis
def test_embedding_defer_is_dropped_on_rollback(env, monkeypatch):
    from app.items.jobs import embed_item_task

    Session, tenant, user = env
    calls = []
    monkeypatch.setattr(embed_item_task, "defer", lambda **kw: calls.append(kw))
    with Session() as s:
        items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="map", title="x"
        )
        s.rollback()
        s.commit()
    assert calls == []
