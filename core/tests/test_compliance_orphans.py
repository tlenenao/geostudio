# SPDX-License-Identifier: Apache-2.0
"""Balayage des objets S3 orphelins d'export/appexport (suite de la migration 0043)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.appexport.models import AppExportJob
from app.compliance.orphans import sweep_orphan_job_objects
from app.db import init_db, make_engine, make_session_factory
from app.export.models import ExportJob

NOW = datetime(2026, 10, 2, tzinfo=UTC)
OLD = NOW - timedelta(hours=48)
FRESH = NOW - timedelta(hours=1)


class FakeS3:
    def __init__(self, buckets: dict[str, dict[str, datetime]]):
        self.buckets = buckets
        self.deleted: list[tuple[str, str]] = []

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        objs = self.buckets[Bucket]
        keys = sorted(k for k in objs if k.startswith(Prefix))
        keys = [k for k in keys if ContinuationToken is None or k > ContinuationToken]
        page = keys[:2]  # pages de 2 : exerce la pagination (jeton = dernière clé, stable)
        more = len(keys) > 2
        return {
            "Contents": [{"Key": k, "LastModified": objs[k]} for k in page],
            "IsTruncated": more,
            "NextContinuationToken": page[-1] if more else None,
        }

    def delete_objects(self, *, Bucket, Delete):
        for o in Delete["Objects"]:
            self.deleted.append((Bucket, o["Key"]))
            del self.buckets[Bucket][o["Key"]]


@pytest.fixture()
def session(tmp_path):
    engine = make_engine(f"sqlite+pysqlite:///{tmp_path / 'orphans.sqlite3'}")
    init_db(engine)
    with make_session_factory(engine)() as s:
        s.connection().exec_driver_sql("PRAGMA foreign_keys=OFF")  # ids factices
        yield s


def _job(model, jid, **kw):
    return model(id=jid, tenant_id="t", item_id="i", user_id="u", status="done", **kw)


def test_sweep_deletes_only_old_keys_without_a_job_row(session, monkeypatch):
    monkeypatch.delenv("S3_EXPORTS_BUCKET", raising=False)
    monkeypatch.delenv("S3_APPEXPORTS_BUCKET", raising=False)
    session.add(_job(ExportJob, "alive", format="png"))
    session.add(_job(AppExportJob, "alive-app", mode="static"))
    session.commit()
    s3 = FakeS3(
        {
            "geostudio-exports": {
                "renders/alive.png": OLD,  # job vivant : gardé
                "renders/gone.png": OLD,  # orphelin ancien : supprimé
                "renders/new-gone.pdf": FRESH,  # orphelin récent (grâce) : gardé
                "renders/gone2.pdf": OLD,  # 3e clé : pagination
                "t/pipelines/p1": OLD,  # clé de writer.export : jamais touchée
                "renders/sub/x.png": OLD,  # forme inattendue : jamais touchée
            },
            "geostudio-appexports": {
                "appexports/alive-app.zip": OLD,
                "appexports/gone-app.zip": OLD,
            },
        }
    )

    n = sweep_orphan_job_objects(session, s3, now=NOW)

    assert n == 3
    assert sorted(s3.deleted) == [
        ("geostudio-appexports", "appexports/gone-app.zip"),
        ("geostudio-exports", "renders/gone.png"),
        ("geostudio-exports", "renders/gone2.pdf"),
    ]
    assert "t/pipelines/p1" in s3.buckets["geostudio-exports"]


def test_sweep_respects_the_per_pass_cap(session):
    s3 = FakeS3(
        {
            "geostudio-exports": {f"renders/g{i}.png": OLD for i in range(5)},
            "geostudio-appexports": {},
        }
    )
    assert sweep_orphan_job_objects(session, s3, now=NOW, limit=3) == 3
    assert len(s3.buckets["geostudio-exports"]) == 2


def test_sweep_ignores_a_missing_bucket(session):
    from botocore.exceptions import ClientError

    class NoBucket(FakeS3):
        def list_objects_v2(self, **kw):
            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "ListObjectsV2")

    assert sweep_orphan_job_objects(session, NoBucket({}), now=NOW) == 0
