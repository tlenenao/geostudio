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


def ensure_uploads_bucket(client, bucket: str, *, expire_days: int | None = None) -> None:
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
    if expire_days:
        # P26.06 (j08b-011) : filet d'expiration des sources d'import jamais
        # purgées (job échoué/abandonné) — best-effort, MinIO peut ne pas
        # l'implémenter.
        try:
            client.put_bucket_lifecycle_configuration(
                Bucket=bucket,
                LifecycleConfiguration={
                    "Rules": [
                        {
                            "ID": "expire-sources",
                            "Status": "Enabled",
                            "Filter": {"Prefix": ""},
                            "Expiration": {"Days": expire_days},
                        }
                    ]
                },
            )
        except ClientError:
            logger.warning("cycle de vie non posé sur %s", bucket, exc_info=True)


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


def generate_presigned_get_url(
    client, *, bucket: str, key: str, expires_in: int = 3600, filename: str | None = None
) -> str:
    params = {"Bucket": bucket, "Key": key}
    if filename:
        safe = filename.replace('"', "")
        params["ResponseContentDisposition"] = f'attachment; filename="{safe}"'
    return _signing_client(client).generate_presigned_url(
        "get_object",
        Params=params,
        ExpiresIn=expires_in,
    )


def generate_presigned_part_url(
    client, *, bucket: str, key: str, upload_id: str, part_number: int, expires_in: int = 900
) -> str:
    return _signing_client(client).generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket, "Key": key, "PartNumber": part_number, "UploadId": upload_id},
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


# REV-268 : l'inspection d'un fichier ligne à ligne (JSONL) n'a besoin que de
# ses premières lignes — inutile de rapatrier jusqu'à CORE_UPLOAD_MAX_BYTES.
INSPECT_HEAD_BYTES = 1024 * 1024


def download_object_head(
    client,
    *,
    bucket: str,
    key: str,
    max_bytes: int | None = None,
    head_bytes: int = INSPECT_HEAD_BYTES,
    max_first_line_factor: int = 16,
) -> bytes:
    """Lit au plus `head_bytes` octets (requête S3 `Range`) d'un objet dont
    la taille reste plafonnée par `max_bytes` (même garde que
    `download_object`). Si l'objet est plus gros que la tête lue, on coupe à
    la dernière fin de ligne : une ligne tronquée ferait échouer l'analyse
    JSON de l'échantillon."""
    size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]
    if max_bytes is not None and size > max_bytes:
        raise ObjectTooLarge(f"fichier trop volumineux ({size} > {max_bytes} octets)")
    if size == 0:  # S3 répond 416 à tout Range sur un objet vide
        return b""
    obj = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{head_bytes - 1}")
    data = obj["Body"].read()
    if size > head_bytes:
        cut = data.rfind(b"\n")
        if cut < 0:
            # REV-323 A : 1re ligne plus longue que la tête — on étend la lecture
            # (bornée) plutôt que de renvoyer un JSON tronqué.
            ext = head_bytes * max_first_line_factor
            data = client.get_object(Bucket=bucket, Key=key, Range=f"bytes=0-{ext - 1}")[
                "Body"
            ].read()
            cut = data.rfind(b"\n")
            if cut < 0 and size > ext:
                raise ObjectTooLarge(f"première ligne de plus de {ext} octets")
        if cut >= 0:
            data = data[: cut + 1]
    return data
