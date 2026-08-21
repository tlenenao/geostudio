# SPDX-License-Identifier: Apache-2.0
"""Wrapper S3 fin — testé avec un client boto3 factice (pas de MinIO réel
nécessaire), même patron que test_ingestion_storage.py (SP-6a)."""

from app.cdc.storage import (
    delete_objects,
    ensure_cdc_bucket,
    list_objects,
    upload_bytes,
    upload_parquet_file,
)


class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.uploaded: list[tuple[str, str, str]] = []  # (local_path, bucket, key)
        self.objects: dict[str, bytes] = {}  # key -> body, pour list/delete/upload_bytes
        self.deleted: list[str] = []

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        self.uploaded.append((Filename, Bucket, Key))

    def list_objects_v2(self, Bucket, Prefix, ContinuationToken=None):  # noqa: N803
        matching = sorted(k for k in self.objects if k.startswith(Prefix))
        # Pagine par lots de 2 pour exercer la boucle ContinuationToken.
        page_size = 2
        start = int(ContinuationToken) if ContinuationToken else 0
        page = matching[start : start + page_size]
        truncated = start + page_size < len(matching)
        return {
            "Contents": [{"Key": k, "Size": len(self.objects[k])} for k in page],
            "IsTruncated": truncated,
            "NextContinuationToken": str(start + page_size) if truncated else None,
        }

    def delete_objects(self, Bucket, Delete):  # noqa: N803
        keys = [o["Key"] for o in Delete["Objects"]]
        for k in keys:
            self.objects.pop(k, None)
            self.deleted.append(k)

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self.objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        from io import BytesIO

        return {"Body": BytesIO(self.objects[Key])}


def test_ensure_cdc_bucket_creates_bucket():
    client = _FakeS3Client()
    ensure_cdc_bucket(client, "geostudio-cdc")
    assert client.created_buckets == ["geostudio-cdc"]


def test_ensure_cdc_bucket_ignores_already_exists():
    from botocore.exceptions import ClientError

    class _AlreadyExistsClient(_FakeS3Client):
        def create_bucket(self, Bucket):  # noqa: N803
            raise ClientError(
                {"Error": {"Code": "BucketAlreadyOwnedByYou"}},
                "CreateBucket",
            )

    ensure_cdc_bucket(_AlreadyExistsClient(), "geostudio-cdc")  # ne doit pas lever


def test_upload_parquet_file_targets_upload_file():
    client = _FakeS3Client()
    upload_parquet_file(
        client, bucket="geostudio-cdc", key="cdc/part-1.parquet", local_path="/tmp/part-1.parquet"
    )
    assert client.uploaded == [("/tmp/part-1.parquet", "geostudio-cdc", "cdc/part-1.parquet")]


def test_list_objects_returns_key_and_size():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"12345", "cdc/b.parquet": b"1234567890"}
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert sorted(result, key=lambda o: o["key"]) == [
        {"key": "cdc/a.parquet", "size": 5},
        {"key": "cdc/b.parquet", "size": 10},
    ]


def test_list_objects_paginates_across_multiple_pages():
    client = _FakeS3Client()
    client.objects = {f"cdc/{i}.parquet": b"x" for i in range(5)}  # 5 objets, pages de 2
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert len(result) == 5  # sans la boucle de pagination, seuls les 2 premiers reviendraient


def test_list_objects_filters_by_prefix():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"x", "other/b.parquet": b"x"}
    result = list_objects(client, bucket="b", prefix="cdc/")
    assert [o["key"] for o in result] == ["cdc/a.parquet"]


def test_delete_objects_removes_all_given_keys():
    client = _FakeS3Client()
    client.objects = {"cdc/a.parquet": b"x", "cdc/b.parquet": b"y"}
    delete_objects(client, bucket="b", keys=["cdc/a.parquet"])
    assert "cdc/a.parquet" not in client.objects
    assert "cdc/b.parquet" in client.objects
    assert client.deleted == ["cdc/a.parquet"]


def test_upload_bytes_writes_via_put_object():
    client = _FakeS3Client()
    upload_bytes(client, bucket="b", key="cdc/merged.parquet", data=b"payload")
    assert client.objects["cdc/merged.parquet"] == b"payload"
