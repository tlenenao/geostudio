# SPDX-License-Identifier: Apache-2.0
"""F1 (writer.collection upsert/update/delete) et F2 (rejets, quarantaine, rapport qualité)."""

import json
import os
import time
from types import SimpleNamespace

import geopandas as gpd
import pytest
from shapely.geometry import Point
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import ColumnInfo, TableInfo
from app.configs.schemas import PipelinePayload
from app.db import Base, make_session_factory
from app.items import repository as items_repo  # noqa: F401
from app.pipelines import repository as pipelines_repo
from app.pipelines import runtime
from app.pipelines.errors import PipelineRuntimeError
from app.sharing.authorization import can
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

INFO = TableInfo(
    table_name="k1_target",
    pk_column="id",
    geometry_column="geometry",
    geometry_type="Point",
    srid=4326,
    columns=[
        ColumnInfo(name="code", type="string", required=False),
        ColumnInfo(name="name", type="string", required=False),
        ColumnInfo(name="pop", type="integer", required=False),
    ],
)

_UPSERT = {"mode": "upsert", "keyColumns": ["code"]}


def _write_src(base_dir, tenant_id, rows):
    d = base_dir / f"tenant_id={tenant_id}" / "collection_id=k1_src" / "dt=2026-10-13"
    d.mkdir(parents=True, exist_ok=True)
    recs = [
        {
            "id": i,
            "code": r[0],
            "name": r[1],
            "pop": r[2],
            "_op": "insert",
            "_lsn": 1,
            "_ts": 1.0,
            "geometry": Point(i % 90, 45.0),
        }
        for i, r in enumerate(rows)
    ]
    for f in d.glob("*.parquet"):
        f.unlink()
    gpd.GeoDataFrame(recs, geometry="geometry", crs="EPSG:4326").to_parquet(d / "part-1.parquet")


@pytest.fixture()
def setup(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )  # fmt: skip
        s.execute(
            text(
                "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
                "description, pk_column, geometry_column, is_public, editable, "
                "created_at, updated_at) VALUES ('k1_target', :t, :o, 'k1_target', "
                "'Cible', '', 'id', 'geometry', false, true, now(), now())"
            ),
            {"t": tenant.id, "o": user.id},
        )
        s.execute(
            text(
                "CREATE TABLE k1_target (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
                "code VARCHAR, name VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
            )
        )
        apply_collection_ddl(s, "k1_target")
        s.commit()
        monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset())
        monkeypatch.setattr(
            runtime,
            "_table_info_for_collection",
            lambda session, cid: INFO,
        )
        monkeypatch.setattr(
            runtime,
            "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )
        yield s, tenant, user, tmp_path
    with pg_engine.begin() as conn:
        conn.execute(
            text(
                'DROP TABLE IF EXISTS k1_target, "k1_target__rejected"; '
                "TRUNCATE entity_history, collection_shares, group_members, groups, items, "
                "configs, config_revisions, collections, audit_log, users, tenants CASCADE"
            )
        )


def _run(ctx, rows, writer_params, *, mid=None, run_id="run-1"):
    _write_src(ctx[3], ctx[1].id, rows)
    return _run_prepared(ctx, writer_params, mid=mid, run_id=run_id)


def _run_prepared(ctx, writer_params=_UPSERT, *, mid=None, run_id="run-1"):
    s, tenant, user, tmp_path = ctx
    nodes = [
        {
            "id": "r1",
            "kind": "reader",
            "op": "reader.collection",
            "params": {"collectionId": "k1_src"},
        },
        {
            "id": "w1",
            "kind": "writer",
            "op": "writer.collection",
            "params": {"collectionId": "k1_target", **writer_params},
        },
    ]
    edges = [{"id": "e1", "from": "r1", "to": "w1"}]
    if mid:
        nodes.insert(1, {"id": "t1", "kind": "transform", **mid})
        edges = [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}]
    stats = runtime.run_pipeline(
        s,
        payload=PipelinePayload.model_validate({"nodes": nodes, "edges": edges}),
        tenant_id=tenant.id,
        user=user,
        endpoint_url="http://localhost:9000",
        access_key="x",
        secret_key="y",
        base_uri=str(tmp_path),
        run_id=run_id,
    )
    s.commit()
    return stats[-1]


def _count(s, table="k1_target"):
    return s.execute(text(f'SELECT count(*) FROM "{table}"')).scalar()


@pytest.mark.postgis
def test_upsert_is_idempotent_and_updates_changed_rows(setup):
    s = setup[0]
    rows = [(f"c{i}", f"n{i}", i) for i in range(5)]
    st = _run(setup, rows, _UPSERT)
    assert (st.extra["inserted"], st.extra["updated"], st.rowCount) == (5, 0, 5)
    st = _run(setup, rows, _UPSERT)  # 2e run : 0 écriture
    assert (st.rowCount, st.extra["unchanged"], _count(s)) == (0, 5, 5)
    rows[2] = ("c2", "renamed", 22)
    st = _run(setup, rows, _UPSERT)
    assert (st.extra["updated"], st.rowCount, _count(s)) == (1, 1, 5)
    assert s.execute(text("SELECT name, pop FROM k1_target WHERE code='c2'")).one() == (
        "renamed",
        22,
    )
    # ARC-15 : la mise à jour est journalisée avec avant/après
    h = s.execute(text("SELECT op, before, after FROM entity_history")).one()
    assert (
        h[0] == "update" and h[1]["properties"]["name"] == "n2" and h[2]["properties"]["pop"] == 22
    )
    assert (
        s.execute(text("SELECT feature_count FROM collections WHERE id='k1_target'")).scalar() == 5
    )


@pytest.mark.postgis
def test_update_never_inserts_and_delete_is_bounded_to_given_keys(setup):
    s = setup[0]
    _run(setup, [(f"c{i}", f"n{i}", i) for i in range(10)], _UPSERT)
    st = _run(setup, [("c1", "x", 1), ("zzz", "y", 2)], {"mode": "update", "keyColumns": ["code"]})
    assert (st.extra["updated"], _count(s)) == (1, 10)  # "zzz" inconnu : ignoré, pas inséré
    st = _run(
        setup,
        [("c3", None, None), ("c4", None, None), ("nope", None, None)],
        {"mode": "delete", "keyColumns": ["code"]},
    )
    assert (st.extra["deleted"], _count(s)) == (2, 8)  # jamais de vidage implicite
    assert s.execute(text("SELECT count(*) FROM entity_history WHERE op='delete'")).scalar() == 2
    assert (
        s.execute(text("SELECT feature_count FROM collections WHERE id='k1_target'")).scalar() == 8
    )


@pytest.mark.postgis
def test_status_column_drives_the_mode(setup):
    s = setup[0]
    rows = [(f"c{i}", f"n{i}", i) for i in range(4)]
    _run(setup, rows, _UPSERT)
    status = {
        "op": "transform.derive",
        "params": {
            "column": "st",
            "expr": "CASE WHEN pop % 2 = 0 THEN 'deleted' ELSE 'unchanged' END",
        },
    }
    st = _run(
        setup, rows, {"mode": "delete", "keyColumns": ["code"], "statusColumn": "st"}, mid=status
    )
    assert (st.extra["deleted"], _count(s)) == (2, 2)  # seules les lignes « deleted »


@pytest.mark.postgis
def test_missing_and_duplicate_keys_are_rejected_not_written(setup):
    s = setup[0]
    rows = [("a", "n", 1), (None, "n", 2), ("a", "dup", 3), ("b", "n", 4)]
    st = _run(setup, rows, {**_UPSERT, "onInvalid": "reject"})
    assert (_count(s), st.extra["rejected"]) == (2, 2)
    assert st.extra["rejectsByRule"] == {"missing_key": 1, "duplicate_key": 1}


@pytest.mark.postgis
def test_quarantine_50_rows_7_invalid(setup, monkeypatch):
    s, tenant, user, _ = setup
    rows = [(f"c{i}", None if i % 7 == 0 and i else f"n{i}", i) for i in range(50)]
    invalid = sum(1 for r in rows if r[1] is None)  # 7
    assert invalid == 7
    mid = {
        "op": "transform.validateAttributes",
        "params": {"nonNullColumns": ["name"], "nonNullResultColumn": "name_ok"},
    }
    st = _run(setup, rows, {"mode": "append", "rejectWhenFalse": ["name_ok"]}, mid=mid)
    assert (_count(s), st.extra["rejected"], st.rowCount) == (43, 7, 43)
    assert st.extra["rejectedCollectionId"] == "k1_target__rejected"
    q = s.execute(text('SELECT source_row, rule, message, run_id FROM "k1_target__rejected"')).all()
    assert len(q) == 7 and {r[1] for r in q} == {"name_ok"} and {r[3] for r in q} == {"run-1"}
    assert "name_ok" in q[0][2] and json.loads(q[0][0])["code"].startswith("c")
    # rapport qualité : taux de nulls de l'entrée
    name = next(c for c in st.extra["quality"]["columns"] if c["name"] == "name")
    assert name["nulls"] == 7 and name["nullRate"] == 0.14
    # le run est « succeeded_with_rejects » (émission outbox F6 hors sujet ici)
    monkeypatch.setattr(pipelines_repo, "_emit_run_finished", lambda *_, **__: None)
    run = SimpleNamespace(status="running")
    fake = SimpleNamespace(get=lambda *_: run, flush=lambda: None, scalar=lambda *_: "running")
    pipelines_repo.mark_succeeded(fake, run_id="x", node_stats={"w1": st.to_dict()})
    assert run.status == "succeeded_with_rejects"
    run2 = SimpleNamespace(status="running")
    fake2 = SimpleNamespace(get=lambda *_: run2, flush=lambda: None, scalar=lambda *_: "running")
    pipelines_repo.mark_succeeded(fake2, run_id="x", node_stats={"w1": {"rowCount": 1}})
    assert run2.status == "succeeded"


@pytest.mark.postgis
def test_quarantine_is_readable_only_by_who_can_write_the_target(setup):
    s, tenant, owner, _ = setup
    editor = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="e", username="ed",
        email=None, first_name="", last_name="",
    )  # fmt: skip
    viewer = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="v", username="vw",
        email=None, first_name="", last_name="",
    )  # fmt: skip
    for gid, uid, role in (("g-ed", editor.id, "editor"), ("g-vw", viewer.id, "viewer")):
        s.execute(
            text(
                "INSERT INTO groups (id, tenant_id, name, created_by, created_at) "
                "VALUES (:g, :t, :g, :o, now())"
            ),
            {"g": gid, "t": tenant.id, "o": owner.id},
        )
        s.execute(
            text("INSERT INTO group_members (group_id, user_id, tenant_id) VALUES (:g, :u, :t)"),
            {"g": gid, "u": uid, "t": tenant.id},
        )
        s.execute(
            text(
                "INSERT INTO collection_shares (collection_id, group_id, tenant_id, role) "
                "VALUES ('k1_target', :g, :t, :r)"
            ),
            {"g": gid, "t": tenant.id, "r": role},
        )
    s.commit()
    _run(setup, [(None, "n", 1)], {**_UPSERT, "onInvalid": "reject"})
    from app.collections import repository as crepo

    q = crepo.get_collection(s, tenant_id=tenant.id, collection_id="k1_target__rejected")
    facts = crepo.get_access_facts(q)

    def readable(u):
        return can(s, user_id=u.id, action="read", item=facts, kind="collection")

    assert (readable(owner), readable(editor), readable(viewer)) == (True, True, False)
    assert q.is_public is False and q.editable is False


@pytest.mark.postgis
def test_masked_field_is_not_writable(setup, monkeypatch):
    monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset({"name"}))
    # le reader ne livre pas la colonne masquée, le writer la retire de sa cible : jamais écrite
    _run(setup, [("a", "secret", 1)], _UPSERT)
    assert setup[0].execute(text("SELECT name, pop FROM k1_target")).one() == (None, 1)
    # une valeur masquée qui arriverait quand même au writer est rejetée comme propriété inconnue
    with pytest.raises(PipelineRuntimeError, match="unknown_property"):
        _run(
            setup,
            [("a", "secret", 1)],
            _UPSERT,
            mid={"op": "transform.derive", "params": {"column": "name", "expr": "'x'"}},
        )


@pytest.mark.postgis
def test_keyed_modes_require_key_columns():
    from app.pipelines.ops.schemas import WriterCollectionParams

    with pytest.raises(ValueError, match="keyColumns"):
        WriterCollectionParams(collectionId="c", mode="upsert")


@pytest.mark.postgis
def test_upsert_100k_rows_under_60s(setup):
    """Critère F1.3 : 100 000 lignes en upsert < 60 s (mesuré par run : insertion puis mise à
    jour de toutes les lignes ; la génération du parquet source n'est pas comptée)."""
    s, tenant, _, tmp_path = setup
    rows = [(f"c{i}", f"n{i}", i) for i in range(100_000)]
    _write_src(tmp_path, tenant.id, rows)
    t0 = time.monotonic()
    st = _run_prepared(setup)
    t_insert = time.monotonic() - t0
    assert st.extra["inserted"] == 100_000
    _write_src(tmp_path, tenant.id, [(c, n + "!", p) for c, n, p in rows])
    t0 = time.monotonic()
    st = _run_prepared(setup)
    t_update = time.monotonic() - t0
    assert st.extra["updated"] == 100_000 and _count(s) == 100_000
    print(f"upsert 100k : insertion {t_insert:.1f}s, mise à jour {t_update:.1f}s")
    # Critère F1.3 = 60 s en local ; un runner CI partagé a mesuré 70 s pour une mise à jour
    # qui prend 20 s en isolation (piège n°7 : une durée mesure la machine), d'où la marge.
    budget = 150 if os.environ.get("CI") else 60
    assert t_insert < budget and t_update < budget, (t_insert, t_update)


@pytest.mark.postgis
def test_rejected_source_row_never_leaks_sensitive_fields(setup, monkeypatch):
    """GAP-22 : la quarantaine est lue par des groupes qui ne lisent pas la cible en clair."""
    s = setup[0]
    s.execute(text("UPDATE collections SET sensitive_fields = '[\"name\"]'::jsonb"))
    s.commit()
    monkeypatch.setattr(runtime, "_masked_fields", lambda *a, **k: frozenset({"name"}))
    _run(
        setup,
        [("a", "secret", 1)],
        {**_UPSERT, "onInvalid": "reject"},
        mid={"op": "transform.derive", "params": {"column": "name", "expr": "'LEAK-VALUE'"}},
    )
    src = s.execute(text('SELECT source_row FROM "k1_target__rejected"')).scalar_one()
    assert "LEAK-VALUE" not in src and "secret" not in src and '"pop"' in src


@pytest.mark.postgis
def test_quality_report_never_profiles_sensitive_fields(setup):
    """Revue finale vague 4, I2 : le rapport qualité (servi par GET /pipelines/{id}/runs, lecture
    du pipeline) ne publie ni min/max ni distincts d'un champ sensible de la cible, même quand
    l'acteur du run le lit en clair."""
    s = setup[0]
    s.execute(text("UPDATE collections SET sensitive_fields = '[\"name\"]'::jsonb"))
    s.commit()
    st = _run(setup, [("a", "zz-secret", 1), ("b", "aa-secret", 2)], _UPSERT)
    names = {c["name"] for c in st.extra["quality"]["columns"]}
    assert "name" not in names and {"code", "pop"} <= names
    assert "secret" not in json.dumps(st.extra["quality"])


@pytest.mark.postgis
def test_rejected_source_row_carries_no_geometry(setup):
    """Revue finale vague 4, I3 : la quarantaine est lisible par les groupes editor/manager de la
    cible, éventuellement limités géographiquement (GAP-27) : jamais de géométrie dans
    `source_row` (la ligne reste identifiable par ses attributs)."""
    s = setup[0]
    _run(setup, [(None, "n", 1)], {**_UPSERT, "onInvalid": "reject"})
    src = json.loads(s.execute(text('SELECT source_row FROM "k1_target__rejected"')).scalar_one())
    assert "geometry" not in src and src["pop"] == 1


def _group(s, tenant, owner, gid, role, suffix):
    u = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub=suffix, username=suffix,
        email=None, first_name="", last_name="",
    )  # fmt: skip
    s.execute(
        text(
            "INSERT INTO groups (id, tenant_id, name, created_by, created_at) "
            "VALUES (:g, :t, :g, :o, now())"
        ),
        {"g": gid, "t": tenant.id, "o": owner.id},
    )
    s.execute(
        text("INSERT INTO group_members (group_id, user_id, tenant_id) VALUES (:g, :u, :t)"),
        {"g": gid, "u": u.id, "t": tenant.id},
    )
    s.execute(
        text(
            "INSERT INTO collection_shares (collection_id, group_id, tenant_id, role) "
            "VALUES ('k1_target', :g, :t, :r)"
        ),
        {"g": gid, "t": tenant.id, "r": role},
    )
    return u


@pytest.mark.postgis
def test_quarantine_shares_follow_target_even_without_rejects(setup):
    s, tenant, owner, _ = setup
    editor = _group(s, tenant, owner, "g-ed", "editor", "ed")
    s.commit()
    _run(setup, [(None, "n", 1)], {**_UPSERT, "onInvalid": "reject"})
    from app.collections import repository as crepo

    def readable():
        q = crepo.get_collection(s, tenant_id=tenant.id, collection_id="k1_target__rejected")
        facts = crepo.get_access_facts(q)
        return can(s, user_id=editor.id, action="read", item=facts, kind="collection")

    assert readable() is True
    s.execute(text("DELETE FROM collection_shares WHERE collection_id = 'k1_target'"))
    s.commit()
    _run(setup, [("a", "n", 1)], {**_UPSERT, "onInvalid": "reject"}, run_id="run-2")  # sans rejet
    s.expire_all()
    assert readable() is False


@pytest.mark.postgis
def test_quarantine_quota_fails_the_run_with_a_clear_message(setup, monkeypatch):
    s = setup[0]
    monkeypatch.setenv("CORE_QUOTAS_ENABLED", "true")
    monkeypatch.setenv("CORE_QUOTA_MAX_COLLECTIONS_PER_TENANT", "1")
    with pytest.raises(PipelineRuntimeError, match="quota de collections"):
        _run(setup, [("ok", "n", 1), (None, "n", 2)], {**_UPSERT, "onInvalid": "reject"})
    s.rollback()
    assert _count(s) == 0  # échec en bloc : aucune écriture partielle


@pytest.mark.postgis
def test_deleted_counts_rows_actually_deleted(setup):
    s = setup[0]
    _run(setup, [("a", "n", 1)], _UPSERT)
    st = _run(setup, [("a", "n", 1), ("zz", "n", 1)], {**_UPSERT, "mode": "delete"})
    assert st.extra["deleted"] == 1 and _count(s) == 0
