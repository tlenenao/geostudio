# SPDX-License-Identifier: Apache-2.0
"""Wrapper S3 fin — testé avec un client boto3 factice (pas de MinIO réel
nécessaire), même patron que fake_introspector dans test_collections_routes.py."""
from app.ingestion.storage import (
    download_object, ensure_uploads_bucket, generate_presigned_put_url,
)


class _FakeS3Client:
    def __init__(self):
        self.created_buckets: list[str] = []
        self.cors_calls: list[tuple[str, dict]] = []
        self.presign_calls: list[tuple[str, dict, int]] = []
        self._objects: dict[str, bytes] = {}

    def create_bucket(self, Bucket):  # noqa: N803 - signature boto3
        self.created_buckets.append(Bucket)

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        self.cors_calls.append((Bucket, CORSConfiguration))

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        self.presign_calls.append((operation, Params, ExpiresIn))
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}?presigned=1"

    def put_object(self, Bucket, Key, Body):  # noqa: N803
        self._objects[Key] = Body

    def get_object(self, Bucket, Key):  # noqa: N803
        class _Body:
            def __init__(self, data: bytes):
                self._data = data

            def read(self) -> bytes:
                return self._data

        return {"Body": _Body(self._objects[Key])}


def test_ensure_uploads_bucket_creates_and_sets_cors():
    client = _FakeS3Client()
    ensure_uploads_bucket(client, "geostudio-uploads")
    assert client.created_buckets == ["geostudio-uploads"]
    assert len(client.cors_calls) == 1
    assert client.cors_calls[0][0] == "geostudio-uploads"


def test_generate_presigned_put_url_targets_put_object():
    client = _FakeS3Client()
    url = generate_presigned_put_url(
        client, bucket="geostudio-uploads", key="t/abc-file.geojson",
        content_type="application/geo+json",
    )
    assert url == "https://minio.test/geostudio-uploads/t/abc-file.geojson?presigned=1"
    operation, params, expires = client.presign_calls[0]
    assert operation == "put_object"
    assert params["Bucket"] == "geostudio-uploads"
    assert params["Key"] == "t/abc-file.geojson"
    assert params["ContentType"] == "application/geo+json"
    assert expires == 900


def test_download_object_reads_body():
    client = _FakeS3Client()
    client.put_object(Bucket="b", Key="k", Body=b"hello")
    assert download_object(client, bucket="b", key="k") == b"hello"
