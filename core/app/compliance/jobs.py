# SPDX-License-Identifier: Apache-2.0
"""Job procrastinate de purge de tenant (SP-58 Tâche 10). Queue "etl" —
réutilisée par analogie avec reports/alerts/pipelines (même famille de
jobs longs, rares, non temps-réel) : une queue dédiée "compliance"
demanderait d'ajouter cette file à la liste `-q ...` du service `worker`
(docker-compose.yml) — un oubli à cet endroit laisserait le job déféré
mais jamais consommé par aucun worker (piège CLAUDE.md n°2, classe de
défaut déjà payée plusieurs fois dans ce dépôt), risque qu'évite le choix
de réutiliser une file déjà dans cette liste."""

import os

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
