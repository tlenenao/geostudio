# SPDX-License-Identifier: Apache-2.0
"""Stockage S3 de conformité, HORS du périmètre des sauvegardes de la base (AUD-092/121) :
archives de rétention de l'audit et journal d'effacement append-only.

Un objet par événement (jamais un fichier réécrit) : pas de course d'ajout, et un objet
écrit ne se modifie pas. Aucune donnée personnelle dans le journal d'effacement : des
identifiants et des horodatages seulement."""

import json
import os
from datetime import UTC, datetime

from botocore.exceptions import ClientError

ERASURE_PREFIX = "erasures/"


def compliance_bucket() -> str:
    return os.environ.get("S3_COMPLIANCE_BUCKET", "geostudio-compliance")


def _ensure_bucket(s3, bucket: str) -> None:
    try:
        s3.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


def put_object(s3, key: str, body: bytes) -> None:
    bucket = compliance_bucket()
    _ensure_bucket(s3, bucket)
    s3.put_object(Bucket=bucket, Key=key, Body=body, ContentType="application/x-ndjson")


def journal_erasure(s3, *, kind: str, tenant_id: str, subject_id: str) -> None:
    """kind : `user` (anonymize_user) ou `tenant` (purge_tenant). subject_id : id du compte
    ou du tenant — jamais un nom ni un e-mail."""
    at = datetime.now(UTC)
    key = f"{ERASURE_PREFIX}{at:%Y%m%dT%H%M%S%f}-{kind}-{subject_id}.json"
    body = json.dumps(
        {"kind": kind, "tenantId": tenant_id, "subjectId": subject_id, "at": at.isoformat()}
    )
    put_object(s3, key, body.encode())


def list_erasures(s3) -> list[dict]:
    bucket = compliance_bucket()
    entries: list[dict] = []
    token: str | None = None
    while True:
        kwargs: dict = {"Bucket": bucket, "Prefix": ERASURE_PREFIX}
        if token:
            kwargs["ContinuationToken"] = token
        try:
            page = s3.list_objects_v2(**kwargs)
        except ClientError as exc:
            if exc.response["Error"]["Code"] == "NoSuchBucket":
                return entries
            raise
        for obj in page.get("Contents", []):
            body = s3.get_object(Bucket=bucket, Key=obj["Key"])["Body"].read()
            entries.append(json.loads(body))
        if not page.get("IsTruncated"):
            return sorted(entries, key=lambda e: e["at"])
        token = page.get("NextContinuationToken")
