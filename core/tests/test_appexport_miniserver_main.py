# SPDX-License-Identifier: Apache-2.0
import importlib
import json

from fastapi.testclient import TestClient

from app.appexport.manifest import CollectionSnapshotEntry, write_manifest
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections.introspection import ColumnInfo, TableInfo


def _build_data_dir(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    (data_dir / "geostudio-app-config.json").write_text(json.dumps({"kind": "app"}))

    table_info = TableInfo(
        table_name="t_x",
        pk_column="id",
        geometry_column=None,
        geometry_type=None,
        srid=4326,
        columns=[
            ColumnInfo(name="id", type="integer", required=True),
            ColumnInfo(name="name", type="string", required=False),
        ],
    )
    entry = CollectionSnapshotEntry(
        id="col1",
        tenant_id="t1",
        collection_json={
            "id": "col1",
            "title": "X",
            "description": "",
            "tableName": "t_x",
            "isPublic": True,
            "editable": False,
            "geometryType": None,
            "srid": 4326,
            "pkColumn": "id",
            "canWrite": False,
            "featureCount": 1,
            "owner": None,
        },
        schema_json={
            "collection": "t_x",
            "pk": "id",
            "geometry": None,
            "fields": [{"name": "name", "type": "string", "required": False}],
        },
        table_info=table_info,
    )
    write_manifest([entry], str(data_dir / "manifest.json"))

    parquet_dir = data_dir / "snapshot" / "tenant_id=t1" / "collection_id=col1" / "dt=snapshot"
    parquet_dir.mkdir(parents=True)
    write_geoparquet(
        [
            ChangeRow(
                op="insert",
                lsn=0,
                ts=0.0,
                pk_column="id",
                pk_value=1,
                columns={"name": "Alpha"},
                geometry_column=None,
                geometry_wkb_hex=None,
            )
        ],
        srid=4326,
        path=str(parquet_dir / "data.parquet"),
    )
    return data_dir


def _client(tmp_path, monkeypatch):
    data_dir = _build_data_dir(tmp_path)
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    (runtime_dir / "index.html").write_text("<html><body>runtime</body></html>")
    monkeypatch.setenv("APPEXPORT_STANDALONE_DATA_DIR", str(data_dir))
    monkeypatch.setenv("APPEXPORT_STANDALONE_RUNTIME_DIR", str(runtime_dir))

    import app.appexport.miniserver.main as main_module

    importlib.reload(main_module)
    return TestClient(main_module.app)


def test_geostudio_app_config_is_served(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-app-config.json")
    assert response.status_code == 200
    assert response.json() == {"kind": "app"}


def test_geostudio_connection_echoes_request_origin(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/geostudio-connection.json")
    assert response.status_code == 200
    assert response.json()["coreUrl"].startswith("http")


def test_list_collections_returns_manifest_entries(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections")
    assert response.status_code == 200
    assert [c["id"] for c in response.json()["collections"]] == ["col1"]


def test_get_collection_includes_links(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1")
    assert response.status_code == 200
    body = response.json()
    assert body["itemType"] == "feature"
    assert any(link["rel"] == "items" for link in body["links"])


def test_get_collection_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/ghost").status_code == 404


def test_get_schema_returns_manifest_schema(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/schema")
    assert response.status_code == 200
    assert response.json()["pk"] == "id"


def test_list_items_reads_snapshot(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"][0]["properties"]["name"] == "Alpha"


def test_get_single_item(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items/1")
    assert response.status_code == 200
    assert response.json()["properties"]["name"] == "Alpha"


def test_get_single_item_missing_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    assert client.get("/collections/col1/items/999").status_code == 404


def test_aggregate_counts_rows(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/col1/aggregate", json={"agg": "count"})
    assert response.status_code == 200
    assert response.json()["rows"][0]["value"] == 1


def test_aggregate_unknown_collection_is_404(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.post("/collections/ghost/aggregate", json={"agg": "count"})
    assert response.status_code == 404


def test_static_runtime_is_served_at_root(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    response = client.get("/")
    assert response.status_code == 200
    assert "runtime" in response.text


def test_list_items_bbox_on_non_spatial_collection_is_400(tmp_path, monkeypatch):
    # col1's table_info has geometry_column=None (see _build_data_dir above),
    # so a bbox query against it must surface as a clean 400 (MissingGeometryColumn
    # from app.appexport.miniserver.items), not propagate as an unhandled 500.
    client = _client(tmp_path, monkeypatch)
    response = client.get("/collections/col1/items", params={"bbox": "0,0,1,1"})
    assert response.status_code == 400
