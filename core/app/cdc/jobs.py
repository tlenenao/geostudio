# SPDX-License-Identifier: Apache-2.0
"""Jobs périodiques du lac : compaction (SP-11b), puis snapshot (REV-280a, en
bas de fichier, qui lui a besoin de la base). La compaction tourne dans le process `worker`
partagé (docker-compose.yml), PAS dans cdc-worker : ce dernier est occupé en
continu par consumer.stream_changes (boucle bloquante), il n'a jamais de
créneau pour exécuter un job procrastinate. La compaction n'a besoin
d'aucun accès Postgres (le layout S3 encode déjà tenant_id/collection_id
dans chaque clé), seulement d'un client S3 — même client que app.cdc.main,
credentials identiques."""

import logging
import os
import re
import time
from datetime import UTC, datetime

from sqlalchemy import select

from app.analytics.duckdb_conn import open_connection, statement_timeout
from app.analytics.snapshot import latest_snapshot, list_snapshots, raw_glob, write_snapshot
from app.cdc import compaction, storage
from app.collections.models import Collection
from app.db import request_scoped_session
from app.jobs import app
from app.jobs.common import session_factory

logger = logging.getLogger(__name__)


@app.periodic(cron="*/10 * * * *")
@app.task(queue="cdc", queueing_lock="run_compaction_cycle_task")
def run_compaction_cycle_task(timestamp: int) -> None:
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(client, bucket)
    report = compaction.run_compaction_cycle(
        client,
        bucket=bucket,
        recent_days=int(os.environ.get("CORE_CDC_COMPACTION_RECENT_DAYS") or 7),
    )
    logger.info(
        "compaction cycle: %s partitions scanned, %s compacted, %s files removed, %s failed",
        report.partitions_scanned,
        report.partitions_compacted,
        report.files_removed,
        report.partitions_failed,
    )


_SNAPSHOT_TIMEOUT_S = 900  # ponytail: plafond fixe, variable CORE_* si un lac l'exige
_DT_RE = re.compile(r"/dt=(\d{4}-\d{2}-\d{2})/")


def _base_uri(bucket: str) -> str:
    return f"s3://{bucket}/cdc"


def _delta_file_count(conn, base_uri: str, tenant_id: str, collection_id: str) -> int:
    """Fichiers bruts susceptibles d'être hors du dernier snapshot : ceux des
    partitions `dt` >= date de sa coupure (sur-estimation inoffensive), tous
    sans snapshot. Pas de LastModified côté glob DuckDB, d'où la date."""
    snap = latest_snapshot(conn, base_uri, tenant_id, collection_id)
    since = datetime.fromtimestamp(snap[1] / 1000, UTC).date().isoformat() if snap else "0000-00-00"
    files = conn.execute(
        "SELECT file FROM glob(?)", [raw_glob(base_uri, tenant_id, collection_id)]
    ).fetchall()
    return sum(1 for (f,) in files if (m := _DT_RE.search(f)) and m.group(1) >= since)


def run_snapshot_cycle(
    conn,
    client,
    *,
    bucket: str,
    collections: list[tuple[str, str, str]],
    now_ms: int,
    min_delta_files: int,
    keep: int,
) -> int:
    """Snapshot de chaque collection (tenant_id, id, pk_column) dont le delta
    atteint `min_delta_files`, puis purge au-delà des `keep` plus récents.
    Isolation par collection : un échec n'empêche pas les suivantes. Idempotent
    (relancé à l'heure suivante si le cycle meurt) ; renvoie le nombre écrit."""
    base_uri = _base_uri(bucket)
    written = 0
    for tenant_id, collection_id, pk_column in collections:
        try:
            if _delta_file_count(conn, base_uri, tenant_id, collection_id) < min_delta_files:
                continue
            with statement_timeout(conn, _SNAPSHOT_TIMEOUT_S):
                uri = write_snapshot(
                    conn, base_uri, tenant_id, collection_id, pk_column, now_ms=now_ms
                )
            if uri is None:
                continue
            written += 1
            old = list_snapshots(conn, base_uri, tenant_id, collection_id)[keep:]
            if old:
                prefix = f"s3://{bucket}/"
                storage.delete_objects(
                    client, bucket=bucket, keys=[u.removeprefix(prefix) for u, _, _ in old]
                )
        except Exception:
            logger.exception("snapshot du lac: échec pour %s/%s, ignoré", tenant_id, collection_id)
    return written


@app.periodic(cron="0 * * * *")
@app.task(queue="cdc", queueing_lock="run_snapshot_cycle_task")
def run_snapshot_cycle_task(timestamp: int) -> None:
    """REV-280a : snapshot horaire d'état courant (flag CORE_LAKE_SNAPSHOT_ENABLED,
    éteint par défaut). Tourne dans `worker` (accès base pour lister les
    collections, DuckDB borné par CORE_DUCKDB_*). Pas de notification : tâche
    d'entretien sans propriétaire ; l'échec est journalisé et rejoué au cycle suivant."""
    if (os.environ.get("CORE_LAKE_SNAPSHOT_ENABLED") or "false").lower() not in ("1", "true"):
        return
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    endpoint, key, secret = (
        os.environ["S3_ENDPOINT_URL"],
        os.environ["S3_ACCESS_KEY"],
        os.environ["S3_SECRET_KEY"],
    )
    client = storage.make_s3_client(endpoint_url=endpoint, access_key=key, secret_key=secret)
    with request_scoped_session(session_factory()) as session:
        collections = [
            (c.tenant_id, c.id, c.pk_column) for c in session.execute(select(Collection)).scalars()
        ]
    conn = open_connection(endpoint_url=endpoint, access_key=key, secret_key=secret)
    try:
        written = run_snapshot_cycle(
            conn,
            client,
            bucket=bucket,
            collections=collections,
            now_ms=int(time.time() * 1000),
            min_delta_files=int(os.environ.get("CORE_LAKE_SNAPSHOT_MIN_DELTA_FILES") or 20),
            keep=max(1, int(os.environ.get("CORE_LAKE_SNAPSHOT_KEEP") or 2)),
        )
    finally:
        conn.close()
    logger.info("snapshot du lac: %s snapshot(s) écrit(s)", written)
