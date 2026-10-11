# SPDX-License-Identifier: Apache-2.0
"""REV-322 : purge du lac CDC (suppression de collection : cf.
test_collections_routes ; purge_tenant : cf. test_compliance_purge)."""

import pytest
from botocore.exceptions import ClientError

from app.analytics.lake_purge import lake_prefix, purge_prefix


class _Store:
    """Magasin S3 en mémoire, pages de 1000 clés comme la vraie API."""

    def __init__(self, keys):
        self.keys = set(keys)

    def list_objects_v2(self, *, Bucket, Prefix=""):
        page = sorted(k for k in self.keys if k.startswith(Prefix))[:1000]
        return {"Contents": [{"Key": k} for k in page]}

    def delete_objects(self, *, Bucket, Delete):
        assert len(Delete["Objects"]) <= 1000
        self.keys -= {o["Key"] for o in Delete["Objects"]}


def test_purge_prefix_goes_past_1000_objects():
    mine = {f"{lake_prefix('t', 'c')}dt=d/p{i}.parquet" for i in range(2300)}
    other = {f"{lake_prefix('t', 'c2')}dt=d/p.parquet"}
    s = _Store(mine | other)
    assert purge_prefix(s, bucket="b", prefix=lake_prefix("t", "c")) == 2300
    assert s.keys == other


def test_purge_prefix_missing_bucket_is_a_noop():
    class _NoBucket:
        def list_objects_v2(self, **_):
            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "ListObjectsV2")

    assert purge_prefix(_NoBucket(), bucket="b", prefix="cdc/") == 0


def test_purge_prefix_reraises_other_errors():
    class _Denied:
        def list_objects_v2(self, **_):
            raise ClientError({"Error": {"Code": "AccessDenied"}}, "ListObjectsV2")

    with pytest.raises(ClientError):
        purge_prefix(_Denied(), bucket="b", prefix="cdc/")
