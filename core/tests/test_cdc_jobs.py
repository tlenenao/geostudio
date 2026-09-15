# SPDX-License-Identifier: Apache-2.0
"""Câblage de `run_compaction_cycle_task` — le wrapper périodique lui-même
n'était exercé par aucun test (compaction.py/storage.py le sont
séparément)."""

from app.cdc import jobs as cdc_jobs


def test_run_compaction_cycle_task_wires_env_and_report(monkeypatch, caplog):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.setenv("S3_CDC_BUCKET", "custom-bucket")

    fake_client = object()
    make_s3_client_calls = []
    ensure_bucket_calls = []
    run_cycle_calls = []

    def fake_make_s3_client(*, endpoint_url, access_key, secret_key):
        make_s3_client_calls.append((endpoint_url, access_key, secret_key))
        return fake_client

    def fake_ensure_cdc_bucket(client, bucket):
        ensure_bucket_calls.append((client, bucket))

    def fake_run_compaction_cycle(client, *, bucket):
        run_cycle_calls.append((client, bucket))
        return cdc_jobs.compaction.CompactionReport(
            partitions_scanned=3, partitions_compacted=2, files_removed=5, partitions_failed=1
        )

    monkeypatch.setattr(cdc_jobs.storage, "make_s3_client", fake_make_s3_client)
    monkeypatch.setattr(cdc_jobs.storage, "ensure_cdc_bucket", fake_ensure_cdc_bucket)
    monkeypatch.setattr(cdc_jobs.compaction, "run_compaction_cycle", fake_run_compaction_cycle)

    with caplog.at_level("INFO"):
        cdc_jobs.run_compaction_cycle_task(timestamp=0)

    assert make_s3_client_calls == [("http://minio:9000", "ak", "sk")]
    assert ensure_bucket_calls == [(fake_client, "custom-bucket")]
    assert run_cycle_calls == [(fake_client, "custom-bucket")]
    assert "3 partitions scanned, 2 compacted, 5 files removed, 1 failed" in caplog.text


def test_run_compaction_cycle_task_defaults_bucket_when_unset(monkeypatch):
    monkeypatch.setenv("S3_ENDPOINT_URL", "http://minio:9000")
    monkeypatch.setenv("S3_ACCESS_KEY", "ak")
    monkeypatch.setenv("S3_SECRET_KEY", "sk")
    monkeypatch.delenv("S3_CDC_BUCKET", raising=False)

    monkeypatch.setattr(cdc_jobs.storage, "make_s3_client", lambda **_: object())
    seen_bucket = {}
    monkeypatch.setattr(
        cdc_jobs.storage,
        "ensure_cdc_bucket",
        lambda client, bucket: seen_bucket.setdefault("b", bucket),
    )
    monkeypatch.setattr(
        cdc_jobs.compaction,
        "run_compaction_cycle",
        lambda client, *, bucket: cdc_jobs.compaction.CompactionReport(0, 0, 0, 0),
    )

    cdc_jobs.run_compaction_cycle_task(timestamp=0)
    assert seen_bucket["b"] == "geostudio-cdc"
