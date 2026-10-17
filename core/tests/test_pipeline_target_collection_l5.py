# SPDX-License-Identifier: Apache-2.0
"""SP-L5 Task 7 (AUD-088 F2) : créer la collection cible d'un writer depuis l'éditeur."""

import duckdb

from app.configs.schemas import PipelinePayload
from app.pipelines import runtime
from app.pipelines.runtime import OutputSchema
from tests.test_pipeline_routes import _demote_owner_to_reader, _make_app, _promote_owner_to_admin

PIPE = {
    "nodes": [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "x"}},
        {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": ""}},
    ],
    "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
}


def _fake_schema(monkeypatch, schema):
    monkeypatch.setattr("app.pipelines.routes.describe_pipeline_output", lambda **kw: schema)


def test_target_collection_maps_types_and_geometry(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    _promote_owner_to_admin(client)
    seen_up_to = {}

    def describe(**kw):
        seen_up_to["v"] = kw["up_to"]
        return OutputSchema(
            columns=[("name", "VARCHAR"), ("pop", "BIGINT"), ("geometry", "GEOMETRY")],
            srid=2154,
            geometry_types=["POLYGON", "MULTIPOLYGON"],
        )

    monkeypatch.setattr("app.pipelines.routes.describe_pipeline_output", describe)
    captured = {}

    def fake_create(session, **kw):
        captured.update(kw)

        class C:
            id = "c-new"

        return C()

    monkeypatch.setattr("app.pipelines.routes.create_empty_collection", fake_create)
    r = client.post(
        "/v1/pipelines/target-collection",
        json={"title": "Communes", "pipeline": PIPE, "writerNodeId": "w1"},
    )
    assert r.status_code == 201 and r.json() == {"collectionId": "c-new"}
    assert seen_up_to["v"] == "r1"  # le schéma décrit est celui du prédécesseur du writer
    assert [(c.name, c.sqlType) for c in captured["columns"]] == [
        ("name", "text"),
        ("pop", "bigint"),
    ]
    assert captured["geometry_type"] == "MultiPolygon" and captured["srid"] == 2154


def test_target_collection_refuses_mixed_or_unknown_geometry(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    _promote_owner_to_admin(client)
    for types in (["POINT", "POLYGON"], []):
        _fake_schema(
            monkeypatch,
            OutputSchema(columns=[("geometry", "GEOMETRY")], srid=4326, geometry_types=types),
        )
        r = client.post(
            "/v1/pipelines/target-collection",
            json={"title": "X", "pipeline": PIPE, "writerNodeId": "w1"},
        )
        assert r.status_code == 400, types


def test_target_collection_requires_data_manage(monkeypatch):
    client = _make_app(monkeypatch, etl_enabled=True)
    _demote_owner_to_reader(client)
    _fake_schema(monkeypatch, OutputSchema(columns=[], srid=None, geometry_types=[]))
    r = client.post(
        "/v1/pipelines/target-collection",
        json={"title": "X", "pipeline": PIPE, "writerNodeId": "w1"},
    )
    assert r.status_code == 403


def test_describe_pipeline_output_reads_columns_and_geometry_types(monkeypatch):
    """Le consommateur réel (DESCRIBE + ST_GeometryType) sur une vue DuckDB."""
    conn = duckdb.connect()
    conn.execute("INSTALL spatial; LOAD spatial;")
    conn.execute(
        "CREATE VIEW v AS SELECT 'a' AS name, 1::BIGINT AS pop, "
        "ST_GeomFromText('POLYGON((0 0,1 0,1 1,0 0))') AS geometry"
    )
    node = PipelinePayload.model_validate(PIPE).nodes[0]

    def fake_on_view(*, consume, **kw):
        return consume(conn, "v", node, 2154)

    monkeypatch.setattr(runtime, "_on_preview_view", fake_on_view)
    out = runtime.describe_pipeline_output(up_to="r1")
    assert out.columns[:2] == [("name", "VARCHAR"), ("pop", "BIGINT")]
    assert out.geometry_types == ["POLYGON"] and out.srid == 2154
