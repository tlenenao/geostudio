# SPDX-License-Identifier: Apache-2.0
"""Balayage des objets S3 orphelins (migration 0043 : la suppression d'un
item supprime ses export_jobs/app_export_jobs en CASCADE, mais pas leurs
fichiers de résultat ; REV-268 : un échec après upload laisse aussi des
objets sans ligne en base dans les buckets uploads et attachments).

Seules des clés dont on sait reconstruire la ligne propriétaire sont
candidates :
- bucket exports : `renders/{job_id}.{ext}` ↔ `ExportJob.id` ;
- bucket exports : `{tenant}/data-exports/{job_id}.{fmt}` ↔ `CollectionExportJob.id`
  (la suppression d'une collection supprime ses jobs en CASCADE) ;
- bucket appexports : `appexports/{job_id}.zip` ↔ `AppExportJob.id` ;
- bucket uploads : `{tenant}/{uuid}-{fichier}` ↔ `IngestionJob.source_key`
  d'un job NON terminé avec succès (un job `pending`/`running`/`error` garde
  sa source ; `done` signifie que la suppression de la source a échoué) ;
- bucket attachments : `{tenant}/{collection}/{fid}/…` ↔ `Attachment.s3_key`.

Jamais `{tenant}/pipelines/...` (écrit par writer.export, sans ligne de job)
ni aucune autre clé. Un objet n'est supprimé que s'il n'a plus de ligne
vivante ET s'il a plus de `GRACE` (la ligne est insérée avant/après l'objet
selon le flux ; le délai couvre les courses et les restaurations)."""

import logging
import os
from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.appexport.models import AppExportJob
from app.attachments.models import Attachment
from app.dataexport.models import CollectionExportJob
from app.export.models import ExportJob
from app.ingestion.models import IngestionJob

logger = logging.getLogger(__name__)

GRACE = timedelta(hours=24)
# Garde anti-effacement massif : une page d'au moins MASS_PAGE objets
# candidats dont 100 % seraient condamnés = table de référence suspecte
# (vide, restaurée, désynchronisée) -> on abandonne le bucket.
MASS_PAGE = 100
MAX_DELETIONS_PER_PASS = 500

# (session, identifiants candidats) -> sous-ensemble encore « vivant ».
AliveLookup = Callable[[Session, set[str]], set[str]]


def _job_id(key: str, prefix: str) -> str | None:
    if not key.startswith(prefix):
        return None
    stem, dot, _ext = key[len(prefix) :].rpartition(".")
    return stem if dot and stem and "/" not in stem else None


def _data_export_id(key: str) -> str | None:
    """`{tenant}/data-exports/{job_id}.{fmt}` -> job_id (REV-283e)."""
    tenant, _, rest = key.partition("/data-exports/")
    return _job_id(f"x/{rest}", "x/") if tenant and "/" not in tenant and rest else None


def _whole_key(key: str) -> str | None:
    """Clé tenant-préfixée (`{tenant}/…`) : l'identifiant est la clé entière."""
    return key if "/" in key and not key.endswith("/") else None


def _alive_by_id(model) -> AliveLookup:
    return lambda session, ids: set(session.scalars(select(model.id).where(model.id.in_(ids))))


def _alive_ingestion_sources(session: Session, keys: set[str]) -> set[str]:
    return set(
        session.scalars(
            select(IngestionJob.source_key).where(
                IngestionJob.source_key.in_(keys), IngestionJob.status != "done"
            )
        )
    )


def _alive_attachment_keys(session: Session, keys: set[str]) -> set[str]:
    return set(session.scalars(select(Attachment.s3_key).where(Attachment.s3_key.in_(keys))))


def _sweep_bucket(
    session: Session,
    s3,
    bucket: str,
    prefix: str,
    ident: Callable[[str], str | None],
    alive: AliveLookup,
    ref_model=None,
    *,
    cutoff: datetime,
    limit: int,
) -> int:
    if ref_model is not None and session.scalar(select(ref_model.id).limit(1)) is None:
        logger.warning("balayage d'orphelins : table de référence de %s vide, bucket sauté", bucket)
        return 0
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
            o["Key"]: ident_value
            for o in page.get("Contents", [])
            if o["LastModified"] < cutoff and (ident_value := ident(o["Key"]))
        }
        if old:
            still_alive = alive(session, set(old.values()))
            doomed = [k for k, ident_value in old.items() if ident_value not in still_alive]
            if len(old) >= MASS_PAGE and len(doomed) == len(old):
                logger.warning(
                    "balayage d'orphelins : %d objets condamnés sur %d dans %s, passe abandonnée",
                    len(doomed),
                    len(old),
                    bucket,
                )
                return deleted
            doomed = doomed[: limit - deleted]
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
    uploads = os.environ.get("S3_UPLOADS_BUCKET", "geostudio-uploads")
    attachments = os.environ.get("S3_ATTACHMENTS_BUCKET", "geostudio-attachments")
    n = 0
    for bucket, prefix, ident, alive, ref_model in (
        (exports, "renders/", lambda k: _job_id(k, "renders/"), _alive_by_id(ExportJob), None),
        (
            exports,
            "",
            _data_export_id,
            _alive_by_id(CollectionExportJob),
            CollectionExportJob,
        ),
        (
            appexports,
            "appexports/",
            lambda k: _job_id(k, "appexports/"),
            _alive_by_id(AppExportJob),
            None,
        ),
        (uploads, "", _whole_key, _alive_ingestion_sources, IngestionJob),
        (attachments, "", _whole_key, _alive_attachment_keys, Attachment),
    ):
        n += _sweep_bucket(
            session, s3, bucket, prefix, ident, alive, ref_model, cutoff=cutoff, limit=limit - n
        )
    return n
