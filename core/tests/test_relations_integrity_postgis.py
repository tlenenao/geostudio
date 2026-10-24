# SPDX-License-Identifier: Apache-2.0
# ruff: noqa: F811 (fixture `env` importée puis redéclarée en argument de test)
"""G6 / AUD-163 à 167 : intégrité des relations entre collections (ADR 0021) sur PostGIS réel.

Une garde posée sur la route REST se reporte sur ses jumelles (piège n°14) : soumission
approuvée, import en ajout, `writer.collection`."""

import types
import uuid

import duckdb
import pytest
from sqlalchemy import text

from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.ingestion.importer import run_append
from app.pipelines.collection_writer import write_rows
from app.public_submit.models import Submission, SubmissionToken
from tests.test_relations_postgis import (  # noqa: F401  (fixture `env`)
    SQUARE,
    _f,
    _related,
    _relation,
    _seed,
    env,
)

pytestmark = pytest.mark.postgis


def _geo_limit(client, collection, group_id):
    r = client.put(
        f"/v1/collections/{collection}/geo-limits/group/{group_id}", json={"geometry": SQUARE}
    )
    assert r.status_code == 200, r.text


def test_aud163_number_matched_does_not_leak_rows_hidden_by_rls(env):
    client, as_user, admin, reader, group_id, _S = env
    rid = _relation(client).json()["id"]
    inside = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "in"})).json()["id"]
    outside = client.post(
        "/v1/collections/rel_parcelles/items", json=_f({"ref": "out"}, x=50, y=50)
    ).json()["id"]
    owner = client.post(
        "/v1/collections/rel_proprios/items", json=_f({"parcelle_id": inside, "nom": "x"})
    ).json()["id"]
    # un propriétaire dont le parent est hors de la limite géographique du lecteur
    hidden_owner = client.post(
        "/v1/collections/rel_proprios/items", json=_f({"parcelle_id": outside, "nom": "y"})
    ).json()["id"]
    _geo_limit(client, "rel_parcelles", group_id)
    as_user(reader)
    ok = client.get(f"/v1/collections/rel_proprios/items/{owner}/related/{rid}").json()
    assert ok["numberMatched"] == 1
    hid = client.get(f"/v1/collections/rel_proprios/items/{hidden_owner}/related/{rid}").json()
    assert hid["features"] == [] and hid["numberMatched"] == 0  # avant : 1 (total des valeurs)


def test_aud164_sensitive_fields_patch_cannot_hide_a_relation_key(env):
    client, *_ = env
    _relation(client)
    r = client.patch("/v1/collections/rel_proprios", json={"sensitiveFields": ["parcelle_id"]})
    assert r.status_code == 409 and "proprietaires" in r.json()["detail"]
    ok = client.patch("/v1/collections/rel_proprios", json={"sensitiveFields": ["tel"]})
    assert ok.status_code == 200, ok.text


def test_aud164_filter_error_on_related_records_is_a_4xx_not_a_500(env, monkeypatch):
    from app.features import repository as features_repo
    from app.relations import service

    client, *_ = env
    rid = _relation(client).json()["id"]
    pid, _owners = _seed(client)

    def boom(*a, **k):
        raise features_repo.FilterError("parcelle_id", "unusable key", code="unknown_filter")

    monkeypatch.setattr(service.features_repo, "select_features", boom)
    r = _related(client, pid, rid)
    assert r.status_code == 422, r.text


def _submission(Session, admin, payload):
    with Session() as s:
        tok = SubmissionToken(
            id=uuid.uuid4().hex,
            tenant_id=admin.tenant_id,
            collection_id="rel_proprios",
            created_by=admin.id,
            name="t",
            token_prefix=uuid.uuid4().hex[:12],
            token_hash="x",
            expires_at=__import__("datetime").datetime(2999, 1, 1),
            max_submissions=10,
        )
        s.add(tok)
        s.flush()
        sub = Submission(
            id=uuid.uuid4().hex,
            tenant_id=admin.tenant_id,
            collection_id="rel_proprios",
            token_id=tok.id,
            status="pending",
            payload=payload,
        )
        s.add(sub)
        s.commit()
        return sub.id


def test_aud165_approved_submission_cannot_orphan_a_child(env):
    client, _as, admin, _r, _g, Session = env
    _relation(client)
    pid, _ = _seed(client)
    bad = _submission(
        Session,
        admin,
        {"properties": {"parcelle_id": 9999, "nom": "X"}, "geometry": _f({})["geometry"]},
    )
    r = client.post(f"/v1/collections/rel_proprios/submissions/{bad}/approve")
    assert r.status_code == 422
    assert r.json()["errors"][0]["code"] == "relation_target_missing"
    good = _submission(
        Session,
        admin,
        {"properties": {"parcelle_id": pid, "nom": "Z"}, "geometry": _f({})["geometry"]},
    )
    assert (
        client.post(f"/v1/collections/rel_proprios/submissions/{good}/approve").status_code == 200
    )


def test_aud165_append_import_rejects_orphan_rows_in_report(env):
    client, _as, admin, _r, _g, Session = env
    _relation(client)
    pid, _ = _seed(client)
    csv = f"parcelle_id,nom,lat,lon\n{pid},ok,48,2\n9999,orphelin,48,2\n".encode()
    with Session() as s:
        report = run_append(
            s,
            tenant_id=admin.tenant_id,
            user=admin,
            collection_id="rel_proprios",
            filename="more.csv",
            content=csv,
            lat_field="lat",
            lon_field="lon",
        )
        s.commit()
        assert report["inserted"] == 1 and report["rejectedCount"] == 1
        assert report["rejected"][0]["row"] == 2
        assert report["rejected"][0]["errors"][0]["code"] == "relation_target_missing"
        n = s.execute(text("SELECT count(*) FROM rel_proprios WHERE parcelle_id = 9999")).scalar()
        assert n == 0


def _write(Session, admin, rows: list[tuple], mode="insert", keys=None):
    p = types.SimpleNamespace(
        mode=mode,
        keyColumns=keys or [],
        statusColumn=None,
        rejectWhenFalse=[],
        onInvalid="reject",
        maxRejectRate=None,
    )
    conn = duckdb.connect()
    conn.execute("CREATE TABLE src (id INTEGER, parcelle_id INTEGER, nom VARCHAR)")
    conn.executemany("INSERT INTO src VALUES (?, ?, ?)", rows)
    with Session() as s:
        col = collections_repo.get_collection(
            s, tenant_id=admin.tenant_id, collection_id="rel_proprios"
        )
        res = write_rows(
            s,
            conn,
            input_view="src",
            p=p,
            collection=col,
            info=introspect_table(s, "rel_proprios"),
            tenant_id=admin.tenant_id,
            user=admin,
            geo_limits={},
            node_id="w",
            run_id=None,
            batch_size=100,
            on_progress=None,
            should_cancel=None,
            replace_purge=lambda: 0,
        )
        s.commit()
    return res


def test_aud165_writer_collection_rejects_orphan_rows_to_quarantine(env):
    client, _as, admin, _r, _g, Session = env
    _relation(client)
    pid, _ = _seed(client)
    res = _write(Session, admin, [(100, pid, "ok"), (101, 9999, "orphelin")])
    assert res.inserted == 1 and res.rejected == 1
    assert res.rejects_by_rule == {"relation_target_missing": 1}
    with Session() as s:
        assert (
            s.execute(text("SELECT count(*) FROM rel_proprios WHERE nom='orphelin'")).scalar() == 0
        )


def test_aud165_writer_one_to_one_duplicate_in_batch_and_against_existing(env):
    client, _as, admin, _r, _g, Session = env
    _relation(client, cardinality="one_to_one")
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A"})).json()["id"]
    res = _write(Session, admin, [(1, pid, "a"), (2, pid, "b")])
    assert res.inserted == 1 and res.rejects_by_rule == {"relation_one_to_one": 1}
    again = _write(Session, admin, [(3, pid, "c")])  # déjà lié en base
    assert again.inserted == 0 and again.rejects_by_rule == {"relation_one_to_one": 1}


def test_aud166_restrict_blocks_parent_key_change_with_children(env):
    client, *_ = env
    _relation(client, parentKey="ref", childKey="nom")
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A1"})).json()["id"]
    kid = client.post("/v1/collections/rel_proprios/items", json=_f({"nom": "A1"})).json()["id"]
    r = client.put(f"/v1/collections/rel_parcelles/items/{pid}", json=_f({"ref": "B2"}))
    assert r.status_code == 409 and "orphan" in r.json()["detail"]
    got = client.get(f"/v1/collections/rel_parcelles/items/{pid}").json()
    assert got["properties"]["ref"] == "A1"
    # même valeur de clé : sans effet sur les enfants, donc permis
    same = client.put(f"/v1/collections/rel_parcelles/items/{pid}", json=_f({"ref": "A1"}))
    assert same.status_code == 204
    # sans enfant : le changement est libre
    client.delete(f"/v1/collections/rel_proprios/items/{kid}")
    free = client.put(f"/v1/collections/rel_parcelles/items/{pid}", json=_f({"ref": "B2"}))
    assert free.status_code == 204


def test_aud166_cascade_propagates_new_parent_key_to_children_journaled(env):
    from sqlalchemy import select

    from app.history.models import EntityHistory

    client, _as, _a, _r, _g, Session = env
    _relation(client, parentKey="ref", childKey="nom", onDelete="cascade")
    pid = client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A1"})).json()["id"]
    kids = [
        client.post("/v1/collections/rel_proprios/items", json=_f({"nom": "A1"})).json()["id"]
        for _ in range(2)
    ]
    r = client.put(f"/v1/collections/rel_parcelles/items/{pid}", json=_f({"ref": "B2"}))
    assert r.status_code == 204, r.text
    for k in kids:
        assert (
            client.get(f"/v1/collections/rel_proprios/items/{k}").json()["properties"]["nom"]
            == "B2"
        )
    with Session() as s:
        ops = s.scalars(
            select(EntityHistory.op).where(EntityHistory.collection_id == "rel_proprios")
        ).all()
        assert ops.count("update") == 2


def test_aud166_writer_update_refuses_parent_key_change_with_children(env):
    client, _as, admin, _r, _g, Session = env
    _relation(client, parentKey="ref", childKey="nom")
    client.post("/v1/collections/rel_parcelles/items", json=_f({"ref": "A1", "code": "k"}))
    client.post("/v1/collections/rel_proprios/items", json=_f({"nom": "A1"}))
    p = types.SimpleNamespace(
        mode="update", keyColumns=["code"], statusColumn=None, rejectWhenFalse=[],
        onInvalid="reject", maxRejectRate=None,
    )  # fmt: skip
    conn = duckdb.connect()
    conn.execute("CREATE TABLE src (code VARCHAR, ref VARCHAR)")
    with Session() as s:
        conn.execute("INSERT INTO src VALUES ('k', 'B2')")
        col = collections_repo.get_collection(
            s, tenant_id=admin.tenant_id, collection_id="rel_parcelles"
        )
        res = write_rows(
            s, conn, input_view="src", p=p, collection=col,
            info=introspect_table(s, "rel_parcelles"), tenant_id=admin.tenant_id, user=admin,
            geo_limits={}, node_id="w", run_id=None, batch_size=100, on_progress=None,
            should_cancel=None, replace_purge=lambda: 0,
        )  # fmt: skip
        s.commit()
        assert res.updated == 0 and res.rejects_by_rule == {"relation_restrict": 1}
        assert s.execute(text("SELECT ref FROM rel_parcelles")).scalar() == "A1"


def test_aud167_collection_delete_refused_while_a_relation_uses_it(env):
    client, *_ = env
    rid = _relation(client).json()["id"]
    r = client.delete("/v1/collections/rel_proprios")
    assert r.status_code == 409 and "proprietaires" in r.json()["detail"]
    assert client.get("/v1/collections/rel_proprios").status_code == 200
    # la relation retirée (route auditée `relation.delete`), la suppression passe
    assert client.delete(f"/v1/relations/{rid}").status_code == 204
    assert client.delete("/v1/collections/rel_proprios").status_code == 204
