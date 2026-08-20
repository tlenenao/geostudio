# SPDX-License-Identifier: Apache-2.0
"""Écrit un instantané GeoParquet local par collection référencée par une
config (SP-18c) — même patron in-process que app.appexport.freeze
(introspect_table + select_features sous rls_scope), mais au lieu
d'embarquer des enregistrements JSON dans la config, écrit une partition
GeoParquet au format CDC (app.cdc.parquet_writer.write_geoparquet/ChangeRow)
avec un seul _lsn=0/_op="insert" par ligne — un instantané est exactement
« un lot CDC de rien que des insertions ». app.analytics.aggregate.
run_collection_aggregate (réutilisé tel quel par le mini-serveur, Task 6)
attend cette disposition hive-partitionnée
(tenant_id=X/collection_id=Y/dt=*/*.parquet) avec colonnes _lsn/_op — c'est
pour ça, pas par choix arbitraire.

Une collection sans aucune ligne ne produit aucun fichier parquet (au lieu
d'un GeoDataFrame vide dont le schéma serait mal inféré) — le mini-serveur
(items.py/run_collection_aggregate) tolère déjà un glob sans fichier
(retourne une page vide), donc rien à modifier côté lecture.

Une même collection référencée par plusieurs DataSources (ex. une carte et
un widget d'agrégat sur la même collection) n'est écrite qu'une fois —
dédoublonnage par collection_id."""

import os

from shapely.geometry import shape as shapely_shape

from app.appexport.manifest import CollectionSnapshotEntry, write_manifest
from app.cdc.parquet_writer import ChangeRow, write_geoparquet
from app.collections import repository as collections_repo
from app.collections.introspection_pg import introspect_table
from app.collections.schema_json import table_info_to_schema
from app.configs.schemas import BuilderConfig
from app.features.repository import select_features
from app.features.rls import rls_scope

_PAGE_SIZE = 1000


def _collection_json(col, *, feature_count: int) -> dict:
    return {
        "id": col.id,
        "title": col.title,
        "description": col.description,
        "tableName": col.table_name,
        "isPublic": col.is_public,
        "editable": False,
        "geometryType": col.geometry_type,
        "srid": col.srid,
        "pkColumn": col.pk_column,
        "canWrite": False,
        "featureCount": feature_count,
        "owner": None,
    }


def _fetch_rows(session, *, tenant_id: str, info, max_records: int) -> list[ChangeRow]:
    rows: list[ChangeRow] = []
    offset = 0
    with rls_scope(session, tenant_id):
        while len(rows) < max_records:
            page = select_features(
                session,
                info,
                limit=_PAGE_SIZE,
                offset=offset,
                bbox=None,
                geom_intersects=None,
                filters=None,
            )
            for feature in page.features:
                geometry = feature["geometry"]
                wkb_hex = shapely_shape(geometry).wkb_hex if geometry else None
                rows.append(
                    ChangeRow(
                        op="insert",
                        lsn=0,
                        ts=0.0,
                        pk_column=info.pk_column,
                        pk_value=feature["id"],
                        columns=feature["properties"],
                        geometry_column=info.geometry_column,
                        geometry_wkb_hex=wkb_hex,
                    )
                )
            if len(page.features) < _PAGE_SIZE:
                break
            offset += _PAGE_SIZE
    return rows[:max_records]


def write_snapshot(
    session,
    *,
    tenant_id: str,
    config: BuilderConfig,
    snapshot_dir: str,
    max_records_per_source: int = 50_000,
) -> list[CollectionSnapshotEntry]:
    entries: list[CollectionSnapshotEntry] = []
    seen: set[str] = set()

    for source in config.dataSources:
        if source.type not in ("features", "statistics"):
            continue
        collection_id = source.layer
        if collection_id in seen:
            continue
        seen.add(collection_id)

        col = collections_repo.get_collection(
            session, tenant_id=tenant_id, collection_id=collection_id
        )
        info = introspect_table(session, col.table_name)
        rows = _fetch_rows(
            session, tenant_id=tenant_id, info=info, max_records=max_records_per_source
        )

        if rows:
            parquet_dir = os.path.join(
                snapshot_dir,
                "snapshot",
                f"tenant_id={tenant_id}",
                f"collection_id={collection_id}",
                "dt=snapshot",
            )
            os.makedirs(parquet_dir, exist_ok=True)
            write_geoparquet(
                rows, srid=info.srid or 4326, path=os.path.join(parquet_dir, "data.parquet")
            )

        entries.append(
            CollectionSnapshotEntry(
                id=col.id,
                tenant_id=tenant_id,
                collection_json=_collection_json(col, feature_count=len(rows)),
                schema_json=table_info_to_schema(info),
                table_info=info,
            )
        )

    os.makedirs(snapshot_dir, exist_ok=True)
    write_manifest(entries, os.path.join(snapshot_dir, "manifest.json"))
    return entries
