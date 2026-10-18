# SPDX-License-Identifier: Apache-2.0
"""Journal d'effacement hors base (AUD-121) : après le commit d'un effacement RGPD, un objet
S3 `erasures/…` consigne (type, tenant, id, horodatage) — jamais une donnée personnelle.
Une restauration de sauvegarde ramène les comptes/tenants effacés depuis ; `replay` (CLI
`python -m app.compliance.replay`) les efface de nouveau à partir de ce journal.

Best-effort après commit : un S3 indisponible ne bloque pas l'effacement (déjà acquis en
base), il est journalisé en erreur. Sans `S3_ENDPOINT_URL` (dev/tests) : sans effet."""

import logging
import os

from sqlalchemy.orm import Session

from app.audit.store import journal_erasure
from app.ingestion.storage import make_s3_client
from app.jobs.after_commit import run_after_commit

logger = logging.getLogger(__name__)


def schedule_erasure_journal(
    session: Session, *, kind: str, tenant_id: str, subject_id: str
) -> None:
    if not os.environ.get("S3_ENDPOINT_URL"):
        return

    def write() -> None:
        try:
            s3 = make_s3_client(
                endpoint_url=os.environ["S3_ENDPOINT_URL"],
                access_key=os.environ["S3_ACCESS_KEY"],
                secret_key=os.environ["S3_SECRET_KEY"],
            )
            journal_erasure(s3, kind=kind, tenant_id=tenant_id, subject_id=subject_id)
        except Exception:
            logger.exception("journal d'effacement non écrit (%s %s)", kind, subject_id)

    run_after_commit(session, write)
