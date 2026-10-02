# SPDX-License-Identifier: Apache-2.0
"""Balayage des objets S3 orphelins de jobs d'export (migration 0043 : la
suppression d'un item supprime ses export_jobs/app_export_jobs en CASCADE,
mais pas leurs fichiers de résultat).

Seules les clés construites par les jobs (`renders/{job_id}.{ext}` dans le
bucket exports, `appexports/{job_id}.zip` dans le bucket appexports) sont
candidates — jamais `{tenant}/pipelines/...` (écrit par writer.export, sans
ligne de job) ni aucune autre clé. Un objet n'est supprimé que si son job_id
n'existe plus en base ET s'il a plus de `GRACE` (le job insère sa ligne avant
d'écrire l'objet ; le délai couvre les courses et les restaurations)."""

import os
from datetime import UTC, datetime, timedelta

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob
from app.export.models import ExportJob

GRACE = timedelta(hours=24)
MAX_DELETIONS_PER_PASS = 500


def _job_id(key: str, prefix: str) -> str | None:
    if not key.startswith(prefix):
        return None
    stem, dot, _ext = key[len(prefix) :].rpartition(".")
    return stem if dot and stem and "/" not in stem else None


def _sweep_bucket(
    session: Session, s3, bucket: str, prefix: str, model, *, cutoff: datetime, limit: int
) -> int:
    deleted = 0
    token: str | None = None
    while deleted < limit:
        kwargs: dict = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        try:
            page = s3.list_objects_v2(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchBucket":  # capacité non activée
                return deleted
            raise
        old = {
            o["Key"]: jid
            for o in page.get("Contents", [])
            if o["LastModified"] < cutoff and (jid := _job_id(o["Key"], prefix))
        }
        if old:
            alive = set(session.scalars(select(model.id).where(model.id.in_(set(old.values())))))
            doomed = [k for k, jid in old.items() if jid not in alive][: limit - deleted]
            if doomed:
                s3.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in doomed]})
                deleted += len(doomed)
        if not page.get("IsTruncated"):
            break
        token = page.get("NextContinuationToken")
    return deleted


def sweep_orphan_job_objects(
    session: Session, s3, *, now: datetime | None = None, limit: int = MAX_DELETIONS_PER_PASS
) -> int:
    cutoff = (now or datetime.now(UTC)) - GRACE
    exports = os.environ.get("S3_EXPORTS_BUCKET", "geostudio-exports")
    appexports = os.environ.get("S3_APPEXPORTS_BUCKET", "geostudio-appexports")
    n = _sweep_bucket(session, s3, exports, "renders/", ExportJob, cutoff=cutoff, limit=limit)
    n += _sweep_bucket(
        session, s3, appexports, "appexports/", AppExportJob, cutoff=cutoff, limit=limit - n
    )
    return n
