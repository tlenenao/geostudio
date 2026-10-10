# SPDX-License-Identifier: Apache-2.0
"""Job procrastinate de purge de tenant (SP-58 Tâche 10). Queue "etl" —
réutilisée par analogie avec reports/alerts/pipelines (même famille de
jobs longs, rares, non temps-réel) : une queue dédiée "compliance"
demanderait d'ajouter cette file à la liste `-q ...` du service `worker`
(docker-compose.yml) — un oubli à cet endroit laisserait le job déféré
mais jamais consommé par aucun worker (piège CLAUDE.md n°2, classe de
défaut déjà payée plusieurs fois dans ce dépôt), risque qu'évite le choix
de réutiliser une file déjà dans cette liste."""

import logging
import os

from app.compliance.orphans import sweep_orphan_job_objects
from app.compliance.purge import purge_tenant
from app.db import request_scoped_session
from app.ingestion.storage import make_s3_client
from app.jobs import app
from app.jobs.common import session_factory as _session_factory


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


@app.task(queue="etl")
def purge_tenant_task(*, purge_id: str, tenant_id: str, requested_by_user_id: str) -> None:
    factory = _session_factory()
    s3 = s3_client_from_env()
    with request_scoped_session(factory) as session:
        purge_tenant(
            session,
            s3,
            tenant_id=tenant_id,
            requested_by_user_id=requested_by_user_id,
            receipt_id=purge_id,
        )
        session.commit()


@app.periodic(cron="23 3 * * *")
@app.task(queue="etl", queueing_lock="sweep_orphan_job_objects_task")
def sweep_orphan_job_objects_task(timestamp: int) -> None:
    """Supprime les fichiers de résultat d'export/appexport dont le job a
    disparu (suppression d'item en CASCADE) et les objets des buckets
    uploads/attachments sans ligne vivante (REV-268). Quotidien, plafonné par passe.
    Pas de garde de flag : un bucket absent (capacité éteinte) est ignoré."""
    if not os.environ.get("S3_ENDPOINT_URL"):
        return
    factory = _session_factory()
    with request_scoped_session(factory) as session:
        n = sweep_orphan_job_objects(session, s3_client_from_env())
    if n:
        logging.getLogger(__name__).info("%d objet(s) S3 orphelin(s) supprimé(s)", n)
