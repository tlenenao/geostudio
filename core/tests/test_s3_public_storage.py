# SPDX-License-Identifier: Apache-2.0
"""P03 (RC-3, RC-13) : CORS non supporté par MinIO reconstruit, liens signés sur
l'hôte public. Le dernier test tourne contre un MinIO réel quand
CORE_TEST_S3_ENDPOINT/KEY/SECRET sont définis (sinon skip)."""

import os
import urllib.request

import pytest
from botocore.exceptions import ClientError

from app.ingestion.storage import (
    ensure_uploads_bucket,
    generate_presigned_get_url,
    generate_presigned_put_url,
    make_s3_client,
)


class _Client:
    def __init__(self, cors_code: str | None = None):
        self.cors_code = cors_code
        self.presigned = 0

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        if self.cors_code:
            raise ClientError({"Error": {"Code": self.cors_code}}, "PutBucketCors")

    def generate_presigned_url(self, *a, **k):
        self.presigned += 1
        return "http://minio:9000/x"


def test_notimplemented_cors_is_tolerated():
    ensure_uploads_bucket(_Client("NotImplemented"), "b")


def test_other_cors_errors_still_raise():
    with pytest.raises(ClientError):
        ensure_uploads_bucket(_Client("AccessDenied"), "b")


def test_presigned_urls_use_public_endpoint_when_set(monkeypatch):
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", "https://files.example.org")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    internal = _Client()
    assert generate_presigned_get_url(internal, bucket="b", key="k").startswith(
        "https://files.example.org/b/k?"
    )
    put = generate_presigned_put_url(internal, bucket="b", key="k", content_type="text/csv")
    assert put.startswith("https://files.example.org/b/k?")
    assert internal.presigned == 0


def test_presigned_url_keeps_client_host_without_public_endpoint(monkeypatch):
    monkeypatch.delenv("S3_PUBLIC_ENDPOINT_URL", raising=False)
    assert generate_presigned_get_url(_Client(), bucket="b", key="k") == "http://minio:9000/x"


def test_real_minio_cors_bucket_and_presign_roundtrip(monkeypatch):
    endpoint = os.environ.get("CORE_TEST_S3_ENDPOINT")
    if not endpoint:
        pytest.skip("CORE_TEST_S3_ENDPOINT non défini — test MinIO réel skippé")
    key, secret = os.environ["CORE_TEST_S3_KEY"], os.environ["CORE_TEST_S3_SECRET"]
    monkeypatch.setenv("S3_PUBLIC_ENDPOINT_URL", endpoint)
    monkeypatch.setenv("S3_ACCESS_KEY", key)
    monkeypatch.setenv("S3_SECRET_KEY", secret)
    s3 = make_s3_client(endpoint_url=endpoint, access_key=key, secret_key=secret)
    ensure_uploads_bucket(s3, "p03-test")
    ensure_uploads_bucket(s3, "p03-test")  # idempotent
    put = generate_presigned_put_url(
        s3, bucket="p03-test", key="t/a.txt", content_type="text/plain"
    )
    headers = {"Content-Type": "text/plain", "Origin": "http://x.test"}
    req = urllib.request.Request(put, data=b"hello", method="PUT", headers=headers)
    with urllib.request.urlopen(req) as resp:  # noqa: S310
        assert resp.status == 200
        assert resp.headers.get("Access-Control-Allow-Origin") in ("*", "http://x.test")
        assert "etag" in resp.headers.get("Access-Control-Expose-Headers", "").lower()
    get = generate_presigned_get_url(s3, bucket="p03-test", key="t/a.txt")
    with urllib.request.urlopen(get) as resp:  # noqa: S310
        assert resp.read() == b"hello"
