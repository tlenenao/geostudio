# SPDX-License-Identifier: Apache-2.0
"""Stockage S3/MinIO pour l'ingestion (SP-6a) : URL présignée pour l'upload
direct navigateur→bucket (arbitrage A6 — le cœur ne doit pas être sur le
chemin des octets pour les uploads de données) et lecture par le worker."""

import logging
import os

from botocore.exceptions import ClientError

logger = logging.getLogger(__name__)

_CORS_CONFIGURATION = {
    "CORSRules": [
        {
            "AllowedMethods": ["PUT"],
            "AllowedOrigins": ["*"],
            "AllowedHeaders": ["*"],
            # ETag n'est PAS un en-tête de réponse safelisté CORS : sans cette
            # ligne, un PUT présigné multipart lancé depuis le navigateur ne peut
            # pas relire res.headers.get("ETag"), et /complete reçoit un etag vide
            # (422 systématique contre un vrai S3/MinIO).
            "ExposeHeaders": ["ETag"],
            "MaxAgeSeconds": 3000,
        }
    ]
}
# CORS large (dev) : l'upload présigné se fait depuis le navigateur, une
# origine différente du cœur (A6). À resserrer aux origines réelles avant
# une mise en production multi-origine.


def make_s3_client(*, endpoint_url: str, access_key: str, secret_key: str):
    import boto3

    return boto3.client(
        "s3",
        endpoint_url=endpoint_url,
        aws_access_key_id=access_key,
        aws_secret_access_key=secret_key,
    )


def ensure_uploads_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    try:
        client.put_bucket_cors(Bucket=bucket, CORSConfiguration=_CORS_CONFIGURATION)
    except ClientError as exc:
        # MinIO reconstruit depuis les sources AGPL : pas d'API CORS par bucket
        # (NotImplemented). Le CORS est alors porté par MINIO_API_CORS_ALLOW_ORIGIN
        # (docker-compose.yml) — l'absence de l'API n'est pas fatale.
        if exc.response["Error"]["Code"] != "NotImplemented":
            raise
        logger.warning("put_bucket_cors non supporté (%s) : CORS global attendu", bucket)


def _signing_client(client):
    """Client dont l'hôte est celui que voit le destinataire du lien.

    Un lien signé sur l'hôte interne (http://minio:9000) est injoignable hors
    du réseau Docker (RC-13) ; la signature couvre l'hôte, on ne peut donc pas
    le réécrire après coup. S3_PUBLIC_ENDPOINT_URL absent = comportement
    historique (client passé tel quel). Signer ne fait aucun appel réseau.
    """
    public = os.environ.get("S3_PUBLIC_ENDPOINT_URL")
    if not public:
        return client
    return make_s3_client(
        endpoint_url=public,
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def generate_presigned_put_url(
    client,
    *,
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int = 900,
) -> str:
    return _signing_client(client).generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def generate_presigned_get_url(client, *, bucket: str, key: str, expires_in: int = 3600) -> str:
    return _signing_client(client).generate_presigned_url(
        "get_object",
        Params={"Bucket": bucket, "Key": key},
        ExpiresIn=expires_in,
    )


class ObjectTooLarge(Exception):
    """Objet plus gros que le plafond de lecture (chargé entièrement en mémoire)."""


def max_upload_bytes() -> int:
    return int(os.environ.get("CORE_UPLOAD_MAX_BYTES") or 512 * 1024 * 1024)


def download_object(client, *, bucket: str, key: str, max_bytes: int | None = None) -> bytes:
    if max_bytes is not None:
        size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
        if size > max_bytes:
            raise ObjectTooLarge(f"fichier trop volumineux ({size} > {max_bytes} octets)")
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()
