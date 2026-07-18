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


def list_objects(client, *, bucket: str, prefix: str) -> list[dict]:
    """Liste paginée (list_objects_v2 ne renvoie qu'1000 clés par appel) —
    une collection à forte écriture accumule aisément plus de fichiers que
    ça avant un cycle de compaction ; une boucle non paginée tronquerait
    silencieusement la découverte des partitions (cf. test dédié)."""
    objects: list[dict] = []
    token = None
    while True:
        kwargs = {"Bucket": bucket, "Prefix": prefix}
        if token:
            kwargs["ContinuationToken"] = token
        resp = client.list_objects_v2(**kwargs)
        for obj in resp.get("Contents", []):
            objects.append({"key": obj["Key"], "size": obj["Size"]})
        if resp.get("IsTruncated"):
            token = resp.get("NextContinuationToken")
        else:
            break
    return objects


def delete_objects(client, *, bucket: str, keys: list[str]) -> None:
    client.delete_objects(Bucket=bucket, Delete={"Objects": [{"Key": k} for k in keys]})


def upload_bytes(client, *, bucket: str, key: str, data: bytes) -> None:
    client.put_object(Bucket=bucket, Key=key, Body=data)
