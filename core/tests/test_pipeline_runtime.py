# SPDX-License-Identifier: Apache-2.0
import csv
import dataclasses
import io
import json

import geopandas as gpd
import pytest
from shapely.geometry import Point
from sqlalchemy import select, text

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


def _table_info_srid(collection_id: str, srid: int) -> TableInfo:
    return dataclasses.replace(TABLE_INFO, table_name=collection_id, srid=srid)


def test_preview_buffer_then_reproject(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
            {"id": "t2", "kind": "transform", "op": "transform.reproject", "params": {"targetCrs": "EPSG:3857"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "geojson", "key": "o.geojson"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
            {"id": "e3", "from": "t2", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), limit=50,
    )
    assert len(rows) == 1
    assert rows[0]["geometry"]["type"] == "Polygon"


def test_preview_h3_aggregate_requires_4326_reproject_first(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 3857),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.h3Aggregate",
             "params": {"resolution": 9, "metrics": {"n": "COUNT(*)"}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(runtime.PipelineRuntimeError, match="EPSG:4326"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def test_preview_count_within_across_two_readers(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    _write_partition(tmp_path, collection_id="incidents", rows=[
        _row(1, "Nord", 1, x=3.0001, y=45.0), _row(2, "Sud", 1, x=10.0, y=10.0),
    ])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
            {"id": "t2", "kind": "transform", "op": "transform.countWithin",
             "params": {"withCollectionId": "incidents", "countColumn": "n"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [
            {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
            {"id": "e3", "from": "t2", "to": "w1"},
        ],
    })

    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t2",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path),
    )
    assert len(rows) == 1
    assert rows[0]["n"] == 1  # only the nearby incident falls in the 500m buffer


def test_preview_intersection_crs_mismatch_raises(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    _write_partition(tmp_path, collection_id="communes", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    srids = {"ecoles": 4326, "communes": 3857}
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, srids[collection_id]),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.intersection",
             "params": {"withCollectionId": "communes"}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(runtime.PipelineRuntimeError, match="transform.reproject"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def test_h3_aggregate_metrics_expression_is_bounded(tmp_path, monkeypatch):
    _write_partition(tmp_path, collection_id="ecoles", rows=[_row(1, "Nord", 1, x=3.0, y=45.0)])
    monkeypatch.setattr(
        runtime, "_table_info_for_collection",
        lambda session, collection_id: _table_info_srid(collection_id, 4326),
    )
    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    from app.configs.schemas import PipelinePayload
    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
            {"id": "t1", "kind": "transform", "op": "transform.h3Aggregate",
             # "(SELECT 1)" seul ne référence AUCUNE table (collect_table_refs
             # le laisserait passer) — l'expression doit référencer une vraie
             # table/vue pour exercer la garde ; "node_r1" est le nom de vue
             # que _prepare a matérialisé pour le reader r1 à ce stade.
             "params": {"resolution": 9, "metrics": {"n": "(SELECT count(*) FROM node_r1)"}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })

    with pytest.raises(Exception, match="must not reference a table"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


def _dataset_pipeline_payload(*, reader_collection: str, writer_collection: str, dataset_id=None, title=None):
    from app.configs.schemas import PipelinePayload
    params = {"collectionId": writer_collection}
    if dataset_id is not None:
        params["datasetId"] = dataset_id
    if title is not None:
        params["title"] = title
    return PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": reader_collection}},
            {"id": "w1", "kind": "writer", "op": "writer.dataset", "params": params},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "w1"}],
    })


@pytest.mark.postgis
def test_writer_dataset_creates_new_dataset_item(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.items.models import Item

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
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", title="Mon dataset",
        )
        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        assert any(stat.op == "writer.dataset" and stat.rowCount == 1 for stat in stats)
        item = s.execute(select(Item).where(Item.tenant_id == tenant.id, Item.resource_type == "dataset")).scalar_one()
        assert item.title == "Mon dataset"
        config = configs_repo.get_config_by_item(s, item.id)
        assert config is not None
        assert config.config.dataset.source == "collection"
        assert config.config.dataset.collectionId == "villes_out"

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.mark.postgis
def test_writer_dataset_updates_existing_dataset_preserving_metadata(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, DatasetPayload
    from app.items import repository as items_repo

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
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")

        existing_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Ancien dataset",
        )
        existing_config = configs_repo.create_config(
            s, BuilderConfig(kind="dataset", dataset=DatasetPayload(
                source="collection", collectionId="villes_out_old", timeField="createdAt",
            )),
            item_id=existing_item.id, tenant_id=tenant.id,
        )
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", dataset_id=existing_item.id,
        )
        runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        updated = configs_repo.get_config(s, existing_config.id)
        # Seeded as "villes_out_old"; only a real update_config() call in the
        # writer's update branch can refresh it to "villes_out".
        assert updated.config.dataset.collectionId == "villes_out"
        assert updated.config.dataset.timeField == "createdAt"  # preserved, not regenerated

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.mark.postgis
def test_writer_dataset_refuses_update_without_write_access(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, DatasetPayload
    from app.items import repository as items_repo

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        owner = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        other = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": owner.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")

        other_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=other.id, resource_type="dataset", title="Dataset de Bob",
        )
        configs_repo.create_config(
            s, BuilderConfig(kind="dataset", dataset=DatasetPayload(source="collection", collectionId="villes_out")),
            item_id=other_item.id, tenant_id=tenant.id,
        )
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", dataset_id=other_item.id,
        )
        with pytest.raises(runtime.PipelineRuntimeError, match="not writable"):
            runtime.run_pipeline(
                s, payload=payload, tenant_id=tenant.id, user=owner,  # owner, not Bob
                endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
                base_uri=str(tmp_path),
            )

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


@pytest.mark.postgis
def test_use_case_3_incidents_near_schools_by_commune(pg_engine, monkeypatch, tmp_path):
    """buffer(500m on schools) -> countWithin(incidents) -> aggregate(by
    commune) -> writer.dataset — design §3.4's worked example, end to end."""
    from app.configs import repository as configs_repo
    from app.items.models import Item

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        # Table de sortie tabulaire (pas de géométrie : l'aggregate final
        # group by commune ne conserve aucune colonne géométrie, cf. plan
        # Task 8 note — transform.aggregate ne sélectionne que groupBy+metrics).
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('communes_incidents', :t, :o, 'communes_incidents', 'Communes incidents', "
            "'', 'id', NULL, false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        # Colonne "region" (pas "commune") : c'est le nom réel de la colonne
        # groupBy en sortie de transform.aggregate ci-dessous (aucun
        # renommage n'a lieu dans compile_transform_sql pour transform.
        # aggregate — cf. plan Task 8 note). "commune" dans le vocabulaire du
        # cas d'usage #3 de l'étude == "region" dans les fixtures partagées
        # de ce fichier de test.
        s.execute(text(
            "CREATE TABLE communes_incidents (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, nearby_incidents BIGINT)"
        ))
        apply_collection_ddl(s, "communes_incidents")
        s.commit()

        # Deux écoles dans des communes différentes ; 2 incidents proches de
        # l'école "Nord" (dans le buffer 500m), 0 proche de "Sud".
        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="ecoles", rows=[
            _row(1, "Nord", 1, x=3.0, y=45.0), _row(2, "Sud", 1, x=10.0, y=10.0),
        ])
        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="incidents", rows=[
            _row(1, "x", 1, x=3.0005, y=45.0), _row(2, "x", 1, x=3.0006, y=45.0),
            _row(3, "x", 1, x=20.0, y=20.0),
        ])

        # communes_incidents (le writer.dataset target) a un schéma physique
        # DIFFÉRENT des readers ecoles/incidents (region+nearby_incidents,
        # pas de géométrie) : contrairement au reader-only TABLE_INFO
        # partagé par les autres tests de ce fichier, ce test a besoin d'un
        # TableInfo par collection_id, sans quoi validate_feature rejetterait
        # "nearby_incidents" comme unknown_property (il n'existe pas dans
        # TABLE_INFO.columns == [region, pop]).
        def _table_info(session, collection_id):
            if collection_id == "communes_incidents":
                return dataclasses.replace(
                    TABLE_INFO, table_name=collection_id, srid=4326,
                    geometry_column=None, geometry_type=None,
                    columns=[
                        ColumnInfo(name="region", type="string", required=True),
                        ColumnInfo(name="nearby_incidents", type="integer", required=True),
                    ],
                )
            return dataclasses.replace(TABLE_INFO, table_name=collection_id, srid=4326)

        monkeypatch.setattr(runtime, "_table_info_for_collection", _table_info)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        from app.configs.schemas import PipelinePayload
        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "ecoles"}},
                {"id": "t1", "kind": "transform", "op": "transform.buffer", "params": {"distance": 500}},
                {"id": "t2", "kind": "transform", "op": "transform.countWithin",
                 "params": {"withCollectionId": "incidents", "countColumn": "cnt"}},
                {"id": "t3", "kind": "transform", "op": "transform.aggregate",
                 "params": {"groupBy": ["region"], "metrics": {"nearby_incidents": "SUM(cnt)"}}},
                {"id": "w1", "kind": "writer", "op": "writer.dataset",
                 "params": {"collectionId": "communes_incidents", "title": "Incidents près des écoles"}},
            ],
            "edges": [
                {"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "t2"},
                {"id": "e3", "from": "t2", "to": "t3"}, {"id": "e4", "from": "t3", "to": "w1"},
            ],
        })

        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        rows = dict(s.execute(text(
            "SELECT region, nearby_incidents FROM communes_incidents"
        )).fetchall())
        assert rows == {"Nord": 2, "Sud": 0}
        assert any(stat.op == "writer.dataset" and stat.rowCount == 2 for stat in stats)

        # writer.dataset a bien catalogué le résultat.
        item = s.execute(select(Item).where(
            Item.tenant_id == tenant.id, Item.resource_type == "dataset",
        )).scalar_one()
        config = configs_repo.get_config_by_item(s, item.id)
        assert config.config.dataset.collectionId == "communes_incidents"

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE communes_incidents; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))


def test_execute_qgis_transform_raises_clean_error_without_worker_url(tmp_path, monkeypatch):
    """No QGIS_WORKER_URL configured (profile 'etl' not enabled) must fail
    the run cleanly, never crash on a connection error."""
    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: _table_info_for(cid))
    _write_partition(tmp_path, rows=[_row(1, "Nord", 1, x=2.35, y=48.85)])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "villes"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })
    with pytest.raises(runtime.PipelineRuntimeError, match="QGIS_WORKER_URL"):
        runtime.preview_pipeline(
            session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )


@pytest.mark.qgis
def test_execute_qgis_transform_computes_centroids(tmp_path, monkeypatch, qgis_worker_url):
    """reader.collection (2 polygons) -> transform.qgis(native:centroids) ->
    preview: real sidecar round-trip, real DuckDB COPY/ST_Read (design §6).
    Requires /scratch to be the SAME directory the qgis-worker container in
    Task 4 Step 5 has bind-mounted at /scratch — this test writes via
    DuckDB's COPY (inside this Python process, on the host), the sidecar
    reads the identical path from inside its container."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

    monkeypatch.setattr(
        runtime, "_require_readable_collection_id",
        lambda session, *, tenant_id, user, collection_id: collection_id,
    )
    polygons_info = dataclasses.replace(
        TABLE_INFO, table_name="polygons", geometry_type="Polygon",
        columns=[ColumnInfo(name="region", type="string", required=True)],
    )
    monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, cid: polygons_info)

    _write_partition(tmp_path, collection_id="polygons", rows=[
        {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(0, 0), (0, 2), (2, 2), (2, 0)])},
        {"id": 2, "region": "b", "_op": "insert", "_lsn": 1, "_ts": 1.0,
         "geometry": Polygon([(10, 10), (10, 12), (12, 12), (12, 10)])},
    ])

    payload = PipelinePayload.model_validate({
        "nodes": [
            {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons"}},
            {"id": "t1", "kind": "transform", "op": "transform.qgis",
             "params": {"algorithmId": "native:centroids", "params": {"ALL_PARTS": False}}},
            {"id": "w1", "kind": "writer", "op": "writer.export", "params": {"format": "csv", "key": "o.csv"}},
        ],
        "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
    })
    rows = runtime.preview_pipeline(
        session=None, payload=payload, tenant_id="t1", user=None, up_to="t1",
        endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
        base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
    )
    assert len(rows) == 2
    centroids = sorted(
        (row["geometry"]["coordinates"][0], row["geometry"]["coordinates"][1]) for row in rows
    )
    assert centroids == [(1.0, 1.0), (11.0, 11.0)]


@pytest.mark.postgis
@pytest.mark.qgis
def test_transform_qgis_end_to_end_dissolve_then_write(pg_engine, monkeypatch, tmp_path, qgis_worker_url):
    """reader.collection (2 adjacent polygons, same region) ->
    transform.qgis(native:dissolve) -> writer.collection: full run_pipeline,
    real Postgres write, real sidecar round-trip. Two squares sharing an
    edge dissolve (grouped by "region", both "a") into one polygon feature —
    proves the qgis dispatch composes with the pre-existing writer.collection
    path unchanged (design §6, 'no fusion to break, node-by-node as before')."""
    from shapely.geometry import Polygon

    from app.configs.schemas import PipelinePayload

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
            "VALUES ('dissolved_out', :t, :o, 'dissolved_out', 'Dissolved', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            # geometry(MultiPolygon, 4326), PAS geometry(Polygon, 4326) : verified
            # against a real qgis_process run during plan-writing that
            # native:dissolve always outputs MultiPolygon (even for a single
            # dissolved group of 1 feature) — ogrinfo on the real output showed
            # "Geometry: Multi Polygon". Using Polygon here would make
            # validate_feature reject every row ("expected Polygon").
            "CREATE TABLE dissolved_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, geometry geometry(MultiPolygon, 4326))"
        ))
        apply_collection_ddl(s, "dissolved_out")
        s.commit()

        polygons_info = dataclasses.replace(
            TABLE_INFO, table_name="polygons_in", geometry_type="Polygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )
        out_info = dataclasses.replace(
            # geometry_type="MultiPolygon" (not "Polygon") — see the CREATE
            # TABLE comment above: native:dissolve's real output type, verified.
            TABLE_INFO, table_name="dissolved_out", geometry_type="MultiPolygon", srid=4326,
            columns=[ColumnInfo(name="region", type="string", required=True)],
        )

        def _table_info(session, collection_id):
            return out_info if collection_id == "dissolved_out" else polygons_info

        monkeypatch.setattr(runtime, "_table_info_for_collection", _table_info)
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        _write_partition(tmp_path, tenant_id=tenant.id, collection_id="polygons_in", rows=[
            {"id": 1, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(0, 0), (0, 2), (1, 2), (1, 0)])},
            {"id": 2, "region": "a", "_op": "insert", "_lsn": 1, "_ts": 1.0,
             "geometry": Polygon([(1, 0), (1, 2), (2, 2), (2, 0)])},
        ])

        payload = PipelinePayload.model_validate({
            "nodes": [
                {"id": "r1", "kind": "reader", "op": "reader.collection", "params": {"collectionId": "polygons_in"}},
                {"id": "t1", "kind": "transform", "op": "transform.qgis",
                 "params": {"algorithmId": "native:dissolve",
                            "params": {"FIELD": "region", "SEPARATE_DISJOINT": False}}},
                {"id": "w1", "kind": "writer", "op": "writer.collection", "params": {"collectionId": "dissolved_out"}},
            ],
            "edges": [{"id": "e1", "from": "r1", "to": "t1"}, {"id": "e2", "from": "t1", "to": "w1"}],
        })
        stats = runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path), qgis_worker_url=qgis_worker_url,
        )
        s.commit()

        rows = s.execute(text("SELECT region FROM dissolved_out")).fetchall()
        assert len(rows) == 1
        assert rows[0][0] == "a"
        assert any(stat.op == "writer.collection" and stat.rowCount == 1 for stat in stats)

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE dissolved_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
