# SPDX-License-Identifier: Apache-2.0
"""Rejeu des effacements après une restauration de sauvegarde (AUD-121).

    docker compose exec core python -m app.compliance.replay

Lit le journal `erasures/` (hors sauvegardes de la base) et ré-applique `anonymize_user` /
`purge_tenant` à tout compte ou tenant que la base restaurée porte encore. Idempotent :
un compte déjà anonymisé ou un tenant absent est ignoré."""

import logging
import os

from sqlalchemy import select

from app.audit.store import list_erasures
from app.compliance.jobs import s3_client_from_env
from app.compliance.purge import purge_tenant
from app.compliance.service import AnonymizationLockoutError, UserAlreadyErasedError, anonymize_user
from app.db import request_scoped_session
from app.jobs.common import session_factory
from app.tenants.models import Tenant
from app.users.models import User

logger = logging.getLogger(__name__)


def replay(session, s3) -> dict[str, int]:
    done = {"users": 0, "tenants": 0, "skipped": 0}
    for entry in list_erasures(s3):
        if entry["kind"] == "tenant":
            if session.get(Tenant, entry["subjectId"]) is None:
                done["skipped"] += 1
                continue
            purge_tenant(
                session,
                s3,
                tenant_id=entry["subjectId"],
                requested_by_user_id="erasure-replay",
            )
            done["tenants"] += 1
        else:
            user = session.scalar(select(User).where(User.id == entry["subjectId"]))
            if user is None or user.erased_at is not None:
                done["skipped"] += 1
                continue
            try:
                anonymize_user(session, tenant_id=user.tenant_id, user_id=user.id)
            except (UserAlreadyErasedError, AnonymizationLockoutError, LookupError):
                done["skipped"] += 1
                continue
            done["users"] += 1
        session.commit()
    return done


def main() -> None:
    if not os.environ.get("S3_ENDPOINT_URL"):
        raise SystemExit("S3_ENDPOINT_URL absent : journal d'effacement illisible")
    with request_scoped_session(session_factory()) as session:
        print(replay(session, s3_client_from_env()))  # noqa: T201


if __name__ == "__main__":
    main()
