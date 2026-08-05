# SPDX-License-Identifier: Apache-2.0
import csv
import dataclasses
import io
import json

import geopandas as gpd
import pytest
from shapely.geometry import Point
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection import ColumnInfo, TableInfo
from app.db import Base, make_engine, make_session_factory
from app.items import repository as items_repo  # noqa: F401 -- enregistre Item
# sur Base.metadata (FK pipeline_runs.pipeline_item_id -> items.id) avant
# Base.metadata.create_all() ; sans cet import, ce module exécuté seul (donc
# sans qu'un autre fichier de test ait déjà importé app.items) échoue avec
# NoReferencedTableError (cf. tests/test_pipeline_repository.py, même patron).
from app.pipelines import runtime
from app.pipelines.repository import get_run
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = []

TABLE_INFO = TableInfo(
    table_name="villes", pk_column="id", geometry_column="geometry",
    geometry_type="Point", srid=4326,
    columns=[
        ColumnInfo(name="region", type="string", required=True),
        ColumnInfo(name="pop", type="integer", required=True),
    ],
)


def _write_partition(base_dir, *, tenant_id="t1", collection_id="villes", rows):
    partition_dir = base_dir / f"tenant_id={tenant_id}" / f"collection_id={collection_id}" / "dt=2026-08-05"
    partition_dir.mkdir(parents=True, exist_ok=True)
    gdf = gpd.GeoDataFrame(rows, geometry="geometry", crs="EPSG:4326")
    gdf.to_parquet(partition_dir / "part-1.parquet")


def _row(id_, region, pop, *, op="insert", lsn=1, x=0.0, y=0.0):
    return {"id": id_, "region": region, "pop": pop, "_op": op, "_lsn": lsn,
            "_ts": 1.0, "geometry": Point(x, y)}


def _table_info_for(collection_id: str) -> TableInfo:
    # Comme le ferait le vrai introspect_table(session, table_name) : le
    # TableInfo renvoyé porte toujours le nom de table demandé. Un TABLE_INFO
    # fixe (table_name="villes" en dur) casserait writer.collection dès que
    # la collection cible a un table_name différent (insert_feature écrirait
    # dans la mauvaise table Postgres).
    return dataclasses.replace(TABLE_INFO, table_name=collection_id)


class _FakeCollections:
    """Stand-in that lets Task 8's tests exercise the reader/transform chain
    without a real collections table — the reader/transform half of the
    runtime only needs table_info + base_uri, never a live Collection row."""


class _FakeS3:
    """Stand-in pour boto3 S3 client : capture les put_object() de
    writer.export sans dépendance à un vrai bucket — même esprit que
    _FakeCollections pour le côté lecture."""

    def __init__(self):
        self.calls: list[dict] = []

    def put_object(self, *, Bucket, Key, Body):
        self.calls.append({"Bucket": Bucket, "Key": Key, "Body": Body})


def test_preview_filter_and_derive(tmp_path, monkeypatch):
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", 10), _row(2, "Sud", 5), _row(3, "Nord", 20),
    ])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    payload_nodes = [
        {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
        {"id": "t1", "kind": "transform", "op": "transform.filter", "params": {"expr": "pop > 8"}},
        {"id": "t2", "kind": "transform", "op": "transform.derive",
         "params": {"column": "pop_double", "expr": "pop * 2"}},
        {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "out.csv"}},
    ]
    edges = [
        {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
        {"id": "e3", "from": "t2", "to": "w1"},
    ]
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({"nodes": payload_nodes, "edges": edges})

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    by_id = {r["id"]: r for r in rows}
    # pop_double = pop * 2 : id=1 a pop=10 (20), id=3 a pop=20 (40) — la
    # valeur 40 pour les deux dans le brief d'origine était une coquille du
    # brief (id=1 a pop=10, pas 20) ; corrigée ici, sans toucher au calcul.
    assert by_id[1]["pop_double"] == 20
    assert by_id[3]["pop_double"] == 40
    assert 2 not in by_id  # filtered out (pop=5 <= 8)


def test_preview_rejects_writer_node_as_up_to(tmp_path, monkeypatch):
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })
    with pytest.raises(runtime.PipelineRuntimeError, match="writer"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="w1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def test_preview_pipeline_serializes_geometry(tmp_path, monkeypatch):
    # Régression finding 1 (revue finale SP-15a) : preview_pipeline renvoyait
    # la géométrie en WKB (bytes) — jsonable_encoder (route FastAPI) plantait
    # en UnicodeDecodeError dessus. json.dumps(rows) ci-dessous prouve ce que
    # la vraie route HTTP ferait sans planter.
    _write_partition(tmp_path, rows=[
        _row(1, "Nord", 10, x=3.0, y=44.0), _row(2, "Sud", 5, x=4.0, y=43.0),
    ])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="r1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    by_id = {r["id"]: r for r in rows}
    assert by_id[1]["geometry"] == {"type": "Point", "coordinates": [3.0, 44.0]}
    assert by_id[2]["geometry"] == {"type": "Point", "coordinates": [4.0, 43.0]}
    json.dumps(rows)  # ne doit pas lever (bytes non sérialisables pré-fix)


def test_write_export_geojson_serializes_geometry(tmp_path, monkeypatch):
    # Régression finding 2 (revue finale SP-15a) : writer.export en geojson
    # plantait sur json.dumps(bytes) et, indépendamment, posait toujours
    # "geometry": None en dur dans chaque feature.
    _write_partition(tmp_path, rows=[_row(1, "Nord", 10, x=1.5, y=45.5)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export",
             "params": {"format": "geojson", "key": "out.geojson"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })
    fake_s3 = _FakeS3()

    stats = runtime.run_pipeline(
        None, payload=payload, tenant_id="t1", user=None,
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), s3_client=fake_s3, exports_bucket="exports",
    )

    assert any(stat.op == "writer.export" and stat.rowCount == 1 for stat in stats)
    assert len(fake_s3.calls) == 1
    body = fake_s3.calls[0]["Body"]
    parsed = json.loads(body)  # ne doit pas lever (bytes non sérialisables pré-fix)
    assert parsed["type"] == "FeatureCollection"
    [feature] = parsed["features"]
    assert feature["geometry"] == {"type": "Point", "coordinates": [1.5, 45.5]}
    assert "geometry" not in feature["properties"]  # pas dupliquée dans properties
    assert feature["properties"]["region"] == "Nord"


def test_write_export_csv_geometry_as_geojson_string(tmp_path, monkeypatch):
    # Régression finding 2 (revue finale SP-15a), branche csv : la colonne
    # geometry contenait le repr Python des bytes WKB (b'\x01...'), inutile
    # en cellule CSV — doit désormais contenir une chaîne GeoJSON exploitable.
    _write_partition(tmp_path, rows=[_row(1, "Nord", 10, x=1.5, y=45.5)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_for(collection_id),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export",
             "params": {"format": "csv", "key": "out.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })
    fake_s3 = _FakeS3()

    runtime.run_pipeline(
        None, payload=payload, tenant_id="t1", user=None,
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), s3_client=fake_s3, exports_bucket="exports",
    )

    body = fake_s3.calls[0]["Body"].decode("utf-8")
    assert "b'\\x" not in body  # pas le repr Python des bytes WKB
    reader = csv.reader(io.StringIO(body))
    header = next(reader)
    data_row = next(reader)
    geometry_cell = data_row[header.index("geometry")]
    parsed_geometry = json.loads(geometry_cell)  # doit être une chaîne GeoJSON valide
    assert parsed_geometry == {"type": "Point", "coordinates": [1.5, 45.5]}


@pytest.mark.postgis
def test_run_pipeline_writes_into_target_collection(pg_engine, monkeypatch, tmp_path):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('villes_propres', :t, :o, 'villes_propres', 'Villes propres', "
            # false/true, pas 0/1 : Postgres ne convertit pas implicitement un
            # littéral entier en boolean (contrairement à MySQL) — coquille du
            # brief d'origine, corrigée ici sans toucher au schéma. created_at/
            # updated_at : le default=_now du modèle est côté Python (ORM),
            # jamais appliqué à un INSERT SQL brut — il faut les poser ici.
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_propres (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        # Sans ceci, INSERT échoue "permission denied" : gis_rls n'a aucun
        # droit sur une table créée à la main (le CREATE TABLE brut ci-dessus
        # ne fait pas ce qu'une vraie inscription de collection ferait) —
        # même GRANTs/RLS/politique que app.collections.ddl.apply_collection_ddl,
        # déjà utilisé par les autres tests postgis d'écriture de features.
        apply_collection_ddl(s, "villes_propres")
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[
            _row(1, "Nord", 10, x=1.0, y=45.0), _row(2, "Sud", 5, x=2.0, y=46.0),
        ])

        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
                {"id": "w1", "kind": "writer", "op": "writer.collection",
                 "params": {"collectionId": "villes_propres"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
        })

        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        count = s.execute(text("SELECT count(*) FROM villes_propres")).scalar()
        assert count == 2
        assert any(stat.op == "writer.collection" and stat.rowCount == 2 for stat in stats)

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_propres; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
