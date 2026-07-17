# SPDX-License-Identifier: Apache-2.0
"""Upload S3/MinIO pour les fichiers GeoParquet CDC (SP-11a). Réutilise
make_s3_client (app.ingestion.storage, SP-6a) — même client boto3, bucket
dédié (S3_CDC_BUCKET) plutôt que le bucket d'uploads."""
from botocore.exceptions import ClientError

from app.ingestion.storage import make_s3_client  # noqa: F401  (ré-export pour app.cdc.main)


def ensure_cdc_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise


def upload_parquet_file(client, *, bucket: str, key: str, local_path: str) -> None:
    client.upload_file(local_path, bucket, key)
