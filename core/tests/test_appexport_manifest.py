# SPDX-License-Identifier: Apache-2.0
from app.appexport.manifest import CollectionSnapshotEntry, read_manifest, write_manifest
from app.collections.introspection import ColumnInfo, TableInfo


def _entry() -> CollectionSnapshotEntry:
    table_info = TableInfo(
        table_name="t_x",
        pk_column="id",
        geometry_column="geom",
        geometry_type="point",
        srid=4326,
        columns=[ColumnInfo(name="name", type="string", required=False)],
    )
    return CollectionSnapshotEntry(
        id="col1",
        tenant_id="t1",
        collection_json={"id": "col1", "title": "X"},
        schema_json={"collection": "t_x", "pk": "id", "geometry": None, "fields": []},
        table_info=table_info,
    )


def test_write_then_read_manifest_round_trips(tmp_path):
    path = str(tmp_path / "manifest.json")
    write_manifest([_entry()], path)

    entries = read_manifest(path)

    assert len(entries) == 1
    e = entries[0]
    assert e.id == "col1"
    assert e.tenant_id == "t1"
    assert e.collection_json == {"id": "col1", "title": "X"}
    assert e.schema_json == {"collection": "t_x", "pk": "id", "geometry": None, "fields": []}
    assert e.table_info.table_name == "t_x"
    assert e.table_info.pk_column == "id"
    assert e.table_info.geometry_column == "geom"
    assert e.table_info.srid == 4326
    assert e.table_info.columns[0].name == "name"
    assert e.table_info.columns[0].type == "string"


def test_write_manifest_with_no_entries(tmp_path):
    path = str(tmp_path / "manifest.json")
    write_manifest([], path)
    assert read_manifest(path) == []


def test_manifest_from_a_newer_core_fails_with_a_clear_message(tmp_path):
    import json

    import pytest

    from app.appexport.manifest import UnsupportedManifestVersion

    path = tmp_path / "manifest.json"
    path.write_text(json.dumps({"formatVersion": 999, "collections": []}))
    with pytest.raises(UnsupportedManifestVersion, match="v999"):
        read_manifest(str(path))


def test_read_manifest_tolerates_unknown_column_keys(tmp_path):
    import json

    path = tmp_path / "manifest.json"
    write_manifest([_entry()], str(path))
    payload = json.loads(path.read_text())
    payload["collections"][0]["tableInfo"]["columns"][0]["futureKey"] = 1
    path.write_text(json.dumps(payload))
    assert read_manifest(str(path))[0].table_info.columns[0].name == "name"
