# SPDX-License-Identifier: Apache-2.0
"""Compaction périodique du change-log GeoParquet CDC (SP-11b) : fusionne
les petits fichiers d'une même partition tenant_id=/collection_id=/dt= en
un seul, SANS jamais changer la sémantique de change-log — toujours
append-only en sortie, aucune déduplication ni suppression de tombstone à
l'écriture (cf. spec §Architecture, "approche A"). La réduction à l'état
courant reste entièrement à la charge du lecteur (app.analytics).

Sûreté à l'interruption : le fichier fusionné est TOUJOURS écrit avant la
suppression des fichiers d'entrée (compact_partition), jamais l'inverse.
Un crash entre les deux laisse des doublons inoffensifs (le lecteur réduit
par (pk, max(_lsn))), jamais de perte ni de suppression partielle
dangereuse — aucun verrou ni coordination avec le worker CDC nécessaire."""

import logging
import re
import uuid
from dataclasses import dataclass
from io import BytesIO

import geopandas as gpd
import pandas as pd

from app.cdc import storage
from app.ingestion.storage import download_object

logger = logging.getLogger(__name__)

CDC_PREFIX = "cdc/"
DEFAULT_SIZE_THRESHOLD_BYTES = 32 * 1024 * 1024

_PARTITION_RE = re.compile(r"^cdc/tenant_id=[^/]+/collection_id=[^/]+/dt=[^/]+/")


@dataclass
class CompactionReport:
    partitions_scanned: int
    partitions_compacted: int
    files_removed: int
    partitions_failed: int = 0


def group_by_partition(objects: list[dict]) -> dict[str, list[dict]]:
    groups: dict[str, list[dict]] = {}
    for obj in objects:
        m = _PARTITION_RE.match(obj["key"])
        if m is None:
            continue
        groups.setdefault(m.group(0), []).append(obj)
    return groups


def select_files_to_merge(files: list[dict], *, size_threshold_bytes: int) -> list[dict]:
    eligible = [f for f in files if f["size"] < size_threshold_bytes]
    return eligible if len(eligible) > 1 else []


def merge_geoparquet(byte_blobs: list[bytes]) -> bytes:
    frames = [gpd.read_parquet(BytesIO(b)) for b in byte_blobs]
    merged = gpd.GeoDataFrame(pd.concat(frames, ignore_index=True), crs=frames[0].crs)
    buf = BytesIO()
    merged.to_parquet(buf)
    return buf.getvalue()


def compact_partition(
    client,
    *,
    bucket: str,
    partition_prefix: str,
    files: list[dict],
    size_threshold_bytes: int,
) -> int:
    to_merge = select_files_to_merge(files, size_threshold_bytes=size_threshold_bytes)
    if not to_merge:
        return 0
    blobs = [download_object(client, bucket=bucket, key=f["key"]) for f in to_merge]
    merged_bytes = merge_geoparquet(blobs)
    new_key = f"{partition_prefix}part-{uuid.uuid4().hex}.parquet"
    # Écriture AVANT suppression, jamais l'inverse (cf. docstring module).
    storage.upload_bytes(client, bucket=bucket, key=new_key, data=merged_bytes)
    storage.delete_objects(client, bucket=bucket, keys=[f["key"] for f in to_merge])
    return len(to_merge)


def run_compaction_cycle(
    client,
    *,
    bucket: str,
    size_threshold_bytes: int = DEFAULT_SIZE_THRESHOLD_BYTES,
) -> CompactionReport:
    objects = storage.list_objects(client, bucket=bucket, prefix=CDC_PREFIX)
    groups = group_by_partition(objects)
    partitions_compacted = 0
    partitions_failed = 0
    files_removed = 0
    for partition_prefix, files in groups.items():
        try:
            merged_count = compact_partition(
                client,
                bucket=bucket,
                partition_prefix=partition_prefix,
                files=files,
                size_threshold_bytes=size_threshold_bytes,
            )
        except Exception:
            # Isolation par partition (REV-025) : une partition trop
            # fragmentée ou corrompue ne doit jamais bloquer la compaction
            # des autres tenants/collections pour tout le cycle.
            partitions_failed += 1
            logger.exception(
                "compaction cycle: échec de la compaction de la partition %s, ignorée",
                partition_prefix,
            )
            continue
        if merged_count:
            partitions_compacted += 1
            files_removed += merged_count
    return CompactionReport(
        partitions_scanned=len(groups),
        partitions_compacted=partitions_compacted,
        files_removed=files_removed,
        partitions_failed=partitions_failed,
    )
