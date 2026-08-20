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
            table_name=ti["tableName"],
            pk_column=ti["pkColumn"],
            geometry_column=ti["geometryColumn"],
            geometry_type=ti["geometryType"],
            srid=ti["srid"],
            columns=[ColumnInfo(**c) for c in ti["columns"]],
        )
        entries.append(
            CollectionSnapshotEntry(
                id=raw["id"],
                tenant_id=raw["tenantId"],
                collection_json=raw["collectionJson"],
                schema_json=raw["schemaJson"],
                table_info=table_info,
            )
        )
    return entries
