# SPDX-License-Identifier: Apache-2.0
"""AUD-090 : l'URL présignée fige la taille annoncée (S3 refuse tout autre Content-Length)."""

from urllib.parse import parse_qs, urlparse

from app.ingestion.storage import generate_presigned_put_url, make_s3_client


def test_presigned_put_signs_content_length():
    client = make_s3_client(endpoint_url="http://minio:9000", access_key="a", secret_key="b")
    url = generate_presigned_put_url(
        client, bucket="b", key="k", content_type="text/csv", content_length=123
    )
    signed = parse_qs(urlparse(url).query)["X-Amz-SignedHeaders"][0].split(";")
    assert "content-length" in signed
