# SPDX-License-Identifier: Apache-2.0
"""Wrapper S3 fin — testé avec un client boto3 factice (pas de MinIO réel
nécessaire), même patron que test_ingestion_storage.py (SP-6a)."""
from app.cdc.storage import ensure_cdc_bucket, upload_parquet_file


class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.uploaded: list[tuple[str, str, str]] = []  # (local_path, bucket, key)

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        self.uploaded.append((Filename, Bucket, Key))


def test_ensure_cdc_bucket_creates_bucket():
    client = _FakeS3Client()
    ensure_cdc_bucket(client, "geostudio-cdc")
    assert client.created_buckets == ["geostudio-cdc"]


def test_ensure_cdc_bucket_ignores_already_exists():
    from botocore.exceptions import ClientError

    class _AlreadyExistsClient(_FakeS3Client):
        def create_bucket(self, Bucket):  # noqa: N803
            raise ClientError(
                {"Error": {"Code": "BucketAlreadyOwnedByYou"}}, "CreateBucket",
            )

    ensure_cdc_bucket(_AlreadyExistsClient(), "geostudio-cdc")  # ne doit pas lever


def test_upload_parquet_file_targets_upload_file():
    client = _FakeS3Client()
    upload_parquet_file(client, bucket="geostudio-cdc", key="cdc/part-1.parquet", local_path="/tmp/part-1.parquet")
    assert client.uploaded == [("/tmp/part-1.parquet", "geostudio-cdc", "cdc/part-1.parquet")]
