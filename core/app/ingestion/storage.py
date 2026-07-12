"""Stockage S3/MinIO pour l'ingestion (SP-6a) : URL présignée pour l'upload
direct navigateur→bucket (arbitrage A6 — le cœur ne doit pas être sur le
chemin des octets pour les uploads de données) et lecture par le worker."""
from botocore.exceptions import ClientError

_CORS_CONFIGURATION = {
    "CORSRules": [{
        "AllowedMethods": ["PUT"],
        "AllowedOrigins": ["*"],
        "AllowedHeaders": ["*"],
        "MaxAgeSeconds": 3000,
    }]
}
# CORS large (dev) : l'upload présigné se fait depuis le navigateur, une
# origine différente du cœur (A6). À resserrer aux origines réelles avant
# une mise en production multi-origine.


def make_s3_client(*, endpoint_url: str, access_key: str, secret_key: str):
    import boto3

    return boto3.client(
        "s3", endpoint_url=endpoint_url,
        aws_access_key_id=access_key, aws_secret_access_key=secret_key,
    )


def ensure_uploads_bucket(client, bucket: str) -> None:
    try:
        client.create_bucket(Bucket=bucket)
    except ClientError as exc:
        if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
            raise
    client.put_bucket_cors(Bucket=bucket, CORSConfiguration=_CORS_CONFIGURATION)


def generate_presigned_put_url(
    client, *, bucket: str, key: str, content_type: str, expires_in: int = 900,
) -> str:
    return client.generate_presigned_url(
        "put_object",
        Params={"Bucket": bucket, "Key": key, "ContentType": content_type},
        ExpiresIn=expires_in,
    )


def download_object(client, *, bucket: str, key: str) -> bytes:
    obj = client.get_object(Bucket=bucket, Key=key)
    return obj["Body"].read()
