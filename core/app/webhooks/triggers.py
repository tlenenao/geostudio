# SPDX-License-Identifier: Apache-2.0
"""Déclencheur de pipeline sur dépôt de fichier S3 (ARC4-F6, ADR 0027) : sondage BORNÉ
d'un préfixe lié à un secret `s3_credentials` (ADR 0012, `bucketUrl`) — aucune écoute
d'événements MinIO. Un fichier = exactement un run : clé d'idempotence
(déclencheur, clé d'objet, etag) insérée dans la transaction qui crée le run.
Seuls les objets plus récents que la création du déclencheur sont considérés
(pas de rejeu du stock existant)."""

import logging
import uuid
from collections.abc import Callable
from datetime import datetime
from urllib.parse import urlsplit

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.outbox.models import FileTrigger, FileTriggerSeen
from app.pipelines.egress import assert_egress_allowed
from app.pipelines.service import run_pipeline_service
from app.secrets import repository as secrets_repo
from app.secrets.schemas import S3CredentialsPayload
from app.users.models import User

logger = logging.getLogger(__name__)

MAX_KEYS = 1000  # plafond de sondage par déclencheur et par passage

# (secret, bucket, key_prefix) -> [(clé, etag, dernière modification naïve UTC)]
Lister = Callable[[S3CredentialsPayload, str, str], list[tuple[str, str, datetime]]]


class TriggerConfigError(Exception):
    pass


def split_prefix(prefix: str) -> tuple[str, str]:
    parsed = urlsplit(prefix)
    if parsed.scheme != "s3" or not parsed.netloc or ".." in parsed.path.split("/"):
        raise TriggerConfigError("préfixe attendu : s3://bucket/préfixe/ (sans '..')")
    return parsed.netloc, parsed.path.lstrip("/")


def check_scope(secret: object, prefix: str) -> S3CredentialsPayload:
    """Le secret doit être `s3_credentials`, lié à un bucket, et couvrir `prefix`."""
    if not isinstance(secret, S3CredentialsPayload):
        raise TriggerConfigError("le secret doit être de type s3_credentials")
    if not secret.bucketUrl:
        raise TriggerConfigError("le secret n'est lié à aucun bucket (bucketUrl requis)")
    split_prefix(prefix)
    if not prefix.startswith(secret.bucketUrl.rstrip("/") + "/"):
        raise TriggerConfigError(f"le préfixe sort du périmètre du secret ('{secret.bucketUrl}')")
    if secret.endpointUrl:
        assert_egress_allowed(secret.endpointUrl)
    return secret


def s3_lister(secret: S3CredentialsPayload, bucket: str, key_prefix: str):
    import boto3

    client = boto3.client(
        "s3",
        endpoint_url=secret.endpointUrl or None,
        aws_access_key_id=secret.awsAccessKeyId,
        aws_secret_access_key=secret.awsSecretAccessKey,
    )
    out: list[tuple[str, str, datetime]] = []
    paginator = client.get_paginator("list_objects_v2")
    for page in paginator.paginate(
        Bucket=bucket, Prefix=key_prefix, PaginationConfig={"MaxItems": MAX_KEYS}
    ):
        for o in page.get("Contents", []):
            if o["Key"].endswith("/"):
                continue
            out.append((o["Key"], o["ETag"].strip('"'), o["LastModified"].replace(tzinfo=None)))
    return out


def poll_trigger(
    session: Session,
    trigger: FileTrigger,
    *,
    defer_task: Callable[[str, str], None],
    lister: Lister = s3_lister,
) -> int:
    """Retourne le nombre de runs créés. Une erreur est tracée dans `last_error`
    (jamais propagée) ; un run déjà actif laisse le fichier non vu : repris au
    passage suivant (donc exactement un run par fichier, en série)."""
    created = 0
    try:
        owner = session.get(User, trigger.created_by)
        secret = (
            secrets_repo.get_secret_payload(
                session, tenant_id=trigger.tenant_id, name=trigger.secret_name, user=owner
            )
            if owner is not None
            else None
        )
        if owner is None or secret is None:
            raise TriggerConfigError(f"secret '{trigger.secret_name}' introuvable ou inutilisable")
        check_scope(secret, trigger.prefix)
        bucket, key_prefix = split_prefix(trigger.prefix)
        objects = sorted(
            (o for o in lister(secret, bucket, key_prefix) if o[2] > trigger.created_at),
            key=lambda o: o[2],
        )
        for key, etag, _ in objects:
            seen = session.scalar(
                select(FileTriggerSeen.id).where(
                    FileTriggerSeen.trigger_id == trigger.id,
                    FileTriggerSeen.object_key == key,
                    FileTriggerSeen.etag == etag,
                )
            )
            if seen:
                continue
            row = FileTriggerSeen(
                id=uuid.uuid4().hex,
                tenant_id=trigger.tenant_id,
                trigger_id=trigger.id,
                object_key=key,
                etag=etag,
            )
            session.add(row)
            session.flush()
            try:
                # commit interne : la clé d'idempotence part avec la ligne du run
                row.run_id = run_pipeline_service(
                    session,
                    user=owner,
                    item_id=trigger.pipeline_item_id,
                    defer_task=defer_task,
                    actor_kind="file_trigger",
                )
            except HTTPException as exc:
                session.rollback()
                if exc.status_code != 409:
                    raise TriggerConfigError(str(exc.detail)) from exc
                break  # run actif : le fichier sera repris au passage suivant
            session.commit()
            created += 1
        trigger.last_error = None
    except TriggerConfigError as exc:
        session.rollback()
        trigger.last_error = str(exc)[:500]
    except Exception as exc:  # noqa: BLE001 — réseau/S3 : tracé, retenté au passage suivant
        session.rollback()
        logger.exception("déclencheur fichier %s : échec du sondage", trigger.id)
        trigger.last_error = f"sondage S3 échoué : {exc}"[:500]
    session.commit()
    return created
