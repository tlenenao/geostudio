# SPDX-License-Identifier: Apache-2.0
"""Balayage des objets S3 orphelins d'export/appexport (suite de la migration 0043)."""

from datetime import UTC, datetime, timedelta

import pytest

from app.appexport.models import AppExportJob
from app.attachments.models import Attachment
from app.compliance.orphans import sweep_orphan_job_objects
from app.db import init_db, make_engine, make_session_factory
from app.export.models import ExportJob
from app.ingestion.models import IngestionJob

NOW = datetime(2026, 10, 2, tzinfo=UTC)
OLD = NOW - timedelta(hours=48)
FRESH = NOW - timedelta(hours=1)


class FakeS3:
    def __init__(self, buckets: dict[str, dict[str, datetime]]):
        self.buckets = buckets
        self.deleted: list[tuple[str, str]] = []

    def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
        if Bucket not in self.buckets:
            from botocore.exceptions import ClientError

            raise ClientError({"Error": {"Code": "NoSuchBucket"}}, "ListObjectsV2")
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


def _ingestion(jid, key, status):
    return IngestionJob(
        id=jid,
        tenant_id="t",
        created_by="u",
        status=status,
        source_key=key,
        filename="f.csv",
        collection_title="T",
    )


def test_sweep_uploads_keeps_sources_of_unfinished_jobs_and_deletes_the_rest(session, monkeypatch):
    monkeypatch.delenv("S3_UPLOADS_BUCKET", raising=False)
    session.add(_ingestion("j1", "t/pending.csv", "pending"))
    session.add(_ingestion("j2", "t/error.csv", "error"))  # source gardée (filet = lifecycle 7 j)
    session.add(_ingestion("j3", "t/done.csv", "done"))  # suppression S3 ratée après succès
    session.commit()
    s3 = FakeS3(
        {
            "geostudio-uploads": {
                "t/pending.csv": OLD,  # job vivant : gardé
                "t/error.csv": OLD,  # job en erreur : gardé
                "t/done.csv": OLD,  # job terminé, objet resté : supprimé
                "t/never-registered.csv": OLD,  # presign sans POST /uploads : supprimé
                "t/fresh.csv": FRESH,  # dans le délai de grâce : gardé
            },
        }
    )
    n = sweep_orphan_job_objects(session, s3, now=NOW)
    assert n == 2
    assert sorted(s3.deleted) == [
        ("geostudio-uploads", "t/done.csv"),
        ("geostudio-uploads", "t/never-registered.csv"),
    ]


def test_sweep_attachments_deletes_only_unreferenced_old_objects(session, monkeypatch):
    monkeypatch.delenv("S3_ATTACHMENTS_BUCKET", raising=False)
    session.add(
        Attachment(
            id="a1",
            tenant_id="t",
            collection_id="c",
            fid="1",
            field_key="f",
            filename="a.pdf",
            content_type="application/pdf",
            byte_size=1,
            s3_key="t/c/1/alive.pdf",
            created_by="u",
        )
    )
    session.commit()
    s3 = FakeS3(
        {
            "geostudio-attachments": {
                "t/c/1/alive.pdf": OLD,  # référencé : gardé
                "t/c/1/orphan.pdf": OLD,  # upload jamais finalisé : supprimé
                "t/c/1/new-orphan.pdf": FRESH,  # grâce : gardé
            },
        }
    )
    assert sweep_orphan_job_objects(session, s3, now=NOW) == 1
    assert s3.deleted == [("geostudio-attachments", "t/c/1/orphan.pdf")]


def test_sweep_skips_attachments_and_uploads_when_reference_table_is_empty(session, monkeypatch):
    monkeypatch.delenv("S3_ATTACHMENTS_BUCKET", raising=False)
    monkeypatch.delenv("S3_UPLOADS_BUCKET", raising=False)
    s3 = FakeS3(
        {
            "geostudio-attachments": {"t/c/1/a.pdf": OLD},
            "geostudio-uploads": {"t/a.csv": OLD},
        }
    )
    assert sweep_orphan_job_objects(session, s3, now=NOW) == 0
    assert s3.deleted == []


def test_sweep_aborts_when_a_full_page_is_entirely_condemned(session, monkeypatch):
    monkeypatch.delenv("S3_ATTACHMENTS_BUCKET", raising=False)
    session.add(
        Attachment(
            id="a1",
            tenant_id="t",
            collection_id="c",
            fid="1",
            field_key="f",
            filename="a.pdf",
            content_type="application/pdf",
            byte_size=1,
            s3_key="t/c/1/other.pdf",  # table non vide mais désynchronisée du bucket
            created_by="u",
        )
    )
    session.commit()
    objs = {f"t/c/1/o{i:03}.pdf": OLD for i in range(150)}

    class Big(FakeS3):
        def list_objects_v2(self, *, Bucket, Prefix="", ContinuationToken=None):
            if Bucket not in self.buckets:
                return super().list_objects_v2(Bucket=Bucket)
            keys = sorted(self.buckets[Bucket])
            return {
                "Contents": [{"Key": k, "LastModified": OLD} for k in keys[:100]],
                "IsTruncated": True,
                "NextContinuationToken": keys[99],
            }

    s3 = Big({"geostudio-attachments": objs})
    assert sweep_orphan_job_objects(session, s3, now=NOW) == 0
    assert s3.deleted == []
