### Task 3: `app.appexport.manifest` — shared snapshot manifest shape

**Files:**
- Create: `core/app/appexport/manifest.py`
- Create: `core/tests/test_appexport_manifest.py`

**Interfaces:**
- Consumes: `TableInfo`/`ColumnInfo` (`app.collections.introspection`, unchanged).
- Produces: `CollectionSnapshotEntry` dataclass (`id: str`, `tenant_id: str`,
  `collection_json: dict`, `schema_json: dict`, `table_info: TableInfo`),
  `write_manifest(entries: list[CollectionSnapshotEntry], path: str) -> None`,
  `read_manifest(path: str) -> list[CollectionSnapshotEntry]`. This is the
  contract Task 4 (writer, full core) and Task 6 (reader, slim mini-server
  image) both depend on — the JSON on disk is the only thing that ever
  crosses between them, never a Python import across the image boundary.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_appexport_manifest.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from app.appexport.manifest import CollectionSnapshotEntry, read_manifest, write_manifest
from app.collections.introspection import ColumnInfo, TableInfo


def _entry() -> CollectionSnapshotEntry:
    table_info = TableInfo(
        table_name="t_x", pk_column="id", geometry_column="geom",
        geometry_type="point", srid=4326,
        columns=[ColumnInfo(name="name", type="string", required=False)],
    )
    return CollectionSnapshotEntry(
        id="col1", tenant_id="t1",
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_appexport_manifest.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.appexport.manifest'`

- [ ] **Step 3: Create `manifest.py`**

Create `core/app/appexport/manifest.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Manifeste d'instantané autoporté (SP-18c) : forme partagée entre le job
d'export (app.appexport.snapshot, tourne dans le worker complet, tous les
paquets core disponibles) et le mini-serveur (app.appexport.miniserver,
tourne dans une image Docker séparée et volontairement minimale) — les deux
processus lisent/écrivent le même fichier manifest.json sur disque, jamais
d'appel réseau ni d'import Python entre eux à l'exécution.

Réutilise TableInfo/ColumnInfo tels quels (app.collections.introspection)
plutôt qu'une forme dupliquée : ces deux dataclasses n'ont aucune dépendance
d'exécution réelle à Postgres (Session n'y sert que de type non exécuté
dans un alias inutilisé ici) — seul le paquet sqlalchemy doit être installé
pour l'import, jamais un driver ni une connexion réelle (cf.
deploy/appexport-standalone/Dockerfile, qui n'installe ni psycopg ni
psycopg2-binary)."""
import json
from dataclasses import asdict, dataclass

from app.collections.introspection import ColumnInfo, TableInfo


@dataclass(frozen=True)
class CollectionSnapshotEntry:
    id: str
    tenant_id: str
    collection_json: dict
    schema_json: dict
    table_info: TableInfo


def write_manifest(entries: list[CollectionSnapshotEntry], path: str) -> None:
    payload = {
        "collections": [
            {
                "id": e.id,
                "tenantId": e.tenant_id,
                "collectionJson": e.collection_json,
                "schemaJson": e.schema_json,
                "tableInfo": {
                    "tableName": e.table_info.table_name,
                    "pkColumn": e.table_info.pk_column,
                    "geometryColumn": e.table_info.geometry_column,
                    "geometryType": e.table_info.geometry_type,
                    "srid": e.table_info.srid,
                    "columns": [asdict(c) for c in e.table_info.columns],
                },
            }
            for e in entries
        ]
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f)


def read_manifest(path: str) -> list[CollectionSnapshotEntry]:
    with open(path, encoding="utf-8") as f:
        payload = json.load(f)
    entries: list[CollectionSnapshotEntry] = []
    for raw in payload["collections"]:
        ti = raw["tableInfo"]
        table_info = TableInfo(
            table_name=ti["tableName"], pk_column=ti["pkColumn"],
            geometry_column=ti["geometryColumn"], geometry_type=ti["geometryType"],
            srid=ti["srid"], columns=[ColumnInfo(**c) for c in ti["columns"]],
        )
        entries.append(CollectionSnapshotEntry(
            id=raw["id"], tenant_id=raw["tenantId"],
            collection_json=raw["collectionJson"], schema_json=raw["schemaJson"],
            table_info=table_info,
        ))
    return entries
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_appexport_manifest.py -v`
Expected: PASS (2 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/appexport/manifest.py core/tests/test_appexport_manifest.py
git commit -m "feat(core): app.appexport.manifest — shared snapshot manifest shape (SP-18c)"
```

---

