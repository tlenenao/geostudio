# SPDX-License-Identifier: Apache-2.0
"""Job périodique de compaction (SP-11b) — tourne dans le process `worker`
partagé (docker-compose.yml), PAS dans cdc-worker : ce dernier est occupé en
continu par consumer.stream_changes (boucle bloquante), il n'a jamais de
créneau pour exécuter un job procrastinate. La compaction n'a besoin
d'aucun accès Postgres (le layout S3 encode déjà tenant_id/collection_id
dans chaque clé), seulement d'un client S3 — même client que app.cdc.main,
credentials identiques."""

import logging
import os

from app.cdc import compaction, storage
from app.jobs import app

logger = logging.getLogger(__name__)


@app.periodic(cron="*/10 * * * *")
@app.task(queue="cdc")
def run_compaction_cycle_task(timestamp: int) -> None:
    bucket = os.environ.get("S3_CDC_BUCKET", "geostudio-cdc")
    client = storage.make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )
    storage.ensure_cdc_bucket(client, bucket)
    report = compaction.run_compaction_cycle(client, bucket=bucket)
    logger.info(
        "compaction cycle: %s partitions scanned, %s compacted, %s files removed",
        report.partitions_scanned,
        report.partitions_compacted,
        report.files_removed,
    )
