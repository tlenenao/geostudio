# SPDX-License-Identifier: Apache-2.0
from typing import Protocol


class ThumbnailStore(Protocol):
    def upload(self, key: str, content: bytes, content_type: str) -> None: ...
    def read(self, key: str) -> tuple[bytes, str]: ...


class InMemoryThumbnailStore:
    def __init__(self) -> None:
        self._objects: dict[str, tuple[bytes, str]] = {}

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        self._objects[key] = (content, content_type)

    def read(self, key: str) -> tuple[bytes, str]:
        return self._objects[key]


class S3ThumbnailStore:
    def __init__(self, endpoint_url: str, access_key: str, secret_key: str, bucket: str) -> None:
        import boto3
        from botocore.exceptions import ClientError

        self._bucket = bucket
        self._client_error = ClientError
        self._client = boto3.client(
            "s3", endpoint_url=endpoint_url,
            aws_access_key_id=access_key, aws_secret_access_key=secret_key,
        )
        self._ensure_bucket()

    def _ensure_bucket(self) -> None:
        try:
            self._client.create_bucket(Bucket=self._bucket)
        except self._client_error as exc:
            if exc.response["Error"]["Code"] not in ("BucketAlreadyOwnedByYou", "BucketAlreadyExists"):
                raise

    def upload(self, key: str, content: bytes, content_type: str) -> None:
        self._client.put_object(Bucket=self._bucket, Key=key, Body=content, ContentType=content_type)

    def read(self, key: str) -> tuple[bytes, str]:
        obj = self._client.get_object(Bucket=self._bucket, Key=key)
        return obj["Body"].read(), obj.get("ContentType", "application/octet-stream")
