# Hébergement de tilesets 3D Tiles uploadés Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author upload a zip containing a 3D Tiles tileset (`tileset.json` + tile binaries, up to several GB / tens of thousands of files), have GeoStudio store it and expose it as a searchable/shareable catalogue item, and let a map author pick it from `LayerPicker` — instead of typing an external URL — to add it to a `tiles3d` map layer.

**Architecture:** The zip is stored as a single S3 object, never extracted. A core module (`app.tileset3d`) provides multipart upload routes (client uploads directly to S3, core never sees the bytes — arbitrage A6), a procrastinate finalize task that validates the zip via a ranged-read (`S3RangeFile` + stdlib `zipfile`, reading only the EOCD + central directory — constant cost regardless of tileset size) and creates the resulting item (`resource_type="tileset3d"`) + `BuilderConfig` (`kind="tileset3d"`), and an authenticated proxy route (`GET /tileset3d/{item_id}/{path}`) that serves individual entries on demand through the same `can()` door as every other item — no public bucket, no CDN in v1. The shell attaches the current session's bearer token to every request deck.gl's `Tile3DLayer` makes for a hosted tileset (via `loadOptions.fetch.headers`), and offers hosted tilesets in `LayerPicker`'s existing searchable source list alongside external-URL entry.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, boto3, procrastinate (core); React, TypeScript, deck.gl, loaders.gl, Vitest, Testing Library, MSW, Playwright (shell).

**Spec:** `docs/superpowers/specs/2026-08-13-3d-tileset-hosting-design.md`

## Global Constraints

- **No server-side extraction.** The zip stays a single S3 object for its whole lifetime; every read (validation, tile serving) uses `S3RangeFile` (ranged GET) + stdlib `zipfile`, never a full download.
- **No public bucket, no CDN.** Every tile read goes through `GET /tileset3d/{item_id}/{path}`, authenticated (`Depends(get_current_user)`) and authorized (`can(session, user_id=..., action="read", item=facts)`) — the same single door as every other item. Accepted v1 cost: no anonymous/public access to hosted tilesets (mirrors `app.export`'s `_require_export_read_access`, which also requires a real bearer token — not a regression relative to existing precedent).
- **`tileset.json` must be at the zip root** (exact entry name `"tileset.json"`) — reject otherwise with a clear error, no "first match" ambiguity.
- **No new table for the resulting artefact's metadata.** It lives in the `BuilderConfig` payload (`Tileset3DPayload`), which the existing `configs` infrastructure already versions/stores. The only new table (`tileset3d_jobs`) tracks the transient multipart-upload lifecycle only.
- **`tenant_id` + `audit_log`** on `tileset3d_jobs` and on every write (job create, upload complete, item create) — non-negotiable per `CLAUDE.md`.
- **`CORE_TILESET3D_ENABLED`** (default `false`) gates the `app.tileset3d` router mount and the shell's upload entry point — same precedent as `CORE_ETL_ENABLED`/`CORE_EXPORT_ENABLED`. `BuilderConfig.kind="tileset3d"` itself is **not** gated (mirrors `pipeline`/`dataset`/etc. — the generic `/configs` route accepts any known `kind` regardless of capability flags).
- **`MapLayer` (shell) is unchanged.** `kind: "tiles3d"` already carries a generic `url` field (delivered by the prior, already-merged 3D spec) — a hosted tileset just produces a URL of the form `${coreUrl}/tileset3d/{itemId}/tileset.json` instead of an external one. No schema change, fully backward-compatible with existing external-URL tilesets.
- **Multipart upload throughout, even for tiny files.** S3's multipart API allows a single part of any size — the same client code path (create → presign-per-part → complete) serves a 50 KB test fixture and a multi-GB tileset. No separate "small file" branch.
- French in user-facing shell strings (labels, buttons, error messages) and commit messages; English in code identifiers — matches existing repo convention.
- TDD per task: write the failing test(s), confirm RED, implement, confirm GREEN, commit.
- **Never skip the OpenAPI/TS regeneration step (Task 7)** — CLAUDE.md flags this exact oversight as recurring across multiple past SPs; it breaks `api-types-drift` in CI silently if forgotten.
- Real-world proxy-route performance under many simultaneous tile requests from an actual city-scale tileset is a manual acceptance check, not a CI assertion (not reliably measurable in headless Chromium/pytest).

---

### Task 1: Core model, migration, repository — `tileset3d_jobs`

**Files:**
- Create: `core/app/tileset3d/__init__.py` (empty)
- Create: `core/app/tileset3d/models.py`
- Create: `core/app/tileset3d/repository.py`
- Create: `core/alembic/versions/0025_tileset3d_jobs.py`
- Test: `core/tests/test_tileset3d_repository.py`

**Interfaces:**
- Produces: `Tileset3DJob` (SQLAlchemy model, table `tileset3d_jobs`, columns `id, tenant_id, created_by, status, source_key, upload_id, filename, title, error_message, item_id, created_at, updated_at`); `repository.create_job(session, *, tenant_id, created_by, source_key, upload_id, filename, title) -> Tileset3DJob`; `repository.get_job(session, *, tenant_id, job_id) -> Tileset3DJob | None`; `repository.mark_finalizing(session, *, job_id) -> None`; `repository.mark_done(session, *, job_id, item_id) -> None`; `repository.mark_error(session, *, job_id, error_message) -> None`. Status values: `"pending" | "finalizing" | "done" | "error"`. Consumed by Task 4 (routes) and Task 5 (finalize task).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_tileset3d_repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import repository as repo
from app.users.repository import get_or_create_user


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    return Session, tenant, alice


def test_create_job_defaults_to_pending(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key=f"{tenant.id}/x/city.zip",
            upload_id="mpu-1", filename="city.zip", title="Ville",
        )
        s.commit()
        assert job.status == "pending"
        assert job.item_id is None
        assert job.error_message is None


def test_get_job_scopes_by_tenant(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id) is not None
        assert repo.get_job(s, tenant_id="other-tenant", job_id=job_id) is None


def test_mark_finalizing_then_done_transitions_status_and_sets_item_id(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_finalizing(s, job_id=job_id)
        s.commit()
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id).status == "finalizing"
    with Session() as s:
        repo.mark_done(s, job_id=job_id, item_id="item-42")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id == "item-42"


def test_mark_error_sets_status_and_message(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k", upload_id="u",
            filename="f.zip", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_error(s, job_id=job_id, error_message="archive zip invalide")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.error_message == "archive zip invalide"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tileset3d'`.

- [ ] **Step 3: Implement the model, repository, and migration**

Create `core/app/tileset3d/__init__.py` (empty file).

Create `core/app/tileset3d/models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Tileset3DJob(Base):
    __tablename__ = "tileset3d_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="pending")
    # "pending" | "finalizing" | "done" | "error"
    source_key: Mapped[str] = mapped_column(String, nullable=False)
    upload_id: Mapped[str] = mapped_column(String, nullable=False)
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

Create `core/app/tileset3d/repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.tileset3d.models import Tileset3DJob


def create_job(
    session: Session, *, tenant_id: str, created_by: str, source_key: str,
    upload_id: str, filename: str, title: str,
) -> Tileset3DJob:
    job = Tileset3DJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, created_by=created_by,
        status="pending", source_key=source_key, upload_id=upload_id,
        filename=filename, title=title,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> Tileset3DJob | None:
    return session.scalar(
        select(Tileset3DJob).where(
            Tileset3DJob.id == job_id, Tileset3DJob.tenant_id == tenant_id
        )
    )


# mark_finalizing/mark_done/mark_error sont appelées uniquement depuis une
# route déjà tenant-scopée (get_job en amont) ou depuis le worker (qui a
# déjà validé le job via get_job(tenant_id=...) en tout début de tâche) —
# pas de re-filtrage par tenant ici, même discipline qu'app.ingestion.repository.
def mark_finalizing(session: Session, *, job_id: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "finalizing"
    session.flush()


def mark_done(session: Session, *, job_id: str, item_id: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.item_id = item_id
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(Tileset3DJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
```

Create `core/alembic/versions/0025_tileset3d_jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""app.tileset3d — tileset3d_jobs

Revision ID: 0025
Revises: 0024
Create Date: 2026-08-13
"""
import sqlalchemy as sa
from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "tileset3d_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="pending"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("upload_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(
        "ix_tileset3d_jobs_tenant_id",
        "tileset3d_jobs",
        ["tenant_id", "id"],
    )


def downgrade() -> None:
    op.drop_index("ix_tileset3d_jobs_tenant_id", table_name="tileset3d_jobs")
    op.drop_table("tileset3d_jobs")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_repository.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd core && git add app/tileset3d/__init__.py app/tileset3d/models.py app/tileset3d/repository.py alembic/versions/0025_tileset3d_jobs.py tests/test_tileset3d_repository.py
git commit -m "feat(core): tileset3d_jobs model, repository, and migration"
```

---

### Task 2: Core config schema — `Tileset3DPayload` + `BuilderConfig.kind="tileset3d"`

**Files:**
- Modify: `core/app/configs/schemas.py` (add `Tileset3DPayload`, extend `BuilderConfig`)
- Test: `core/tests/test_tileset3d_schema.py`

**Interfaces:**
- Consumes: none from Task 1.
- Produces: `Tileset3DPayload(sourceKey: str, tilesetJsonPath: str, totalBytes: int, entryCount: int)`; `BuilderConfig.kind` Literal gains `"tileset3d"`; `BuilderConfig.tileset3d: Tileset3DPayload | None = None`. Consumed by Task 5 (finalize task builds this payload) and Task 6 (read route reads it back via `configs_repo.get_config_by_item`).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_tileset3d_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
def test_tileset3d_config_round_trips(client):
    created = client.post(
        "/configs",
        json={
            "title": "Bâtiments du centre-ville",
            "config": {
                "kind": "tileset3d",
                "tileset3d": {
                    "sourceKey": "tenant-1/abc/city.zip",
                    "tilesetJsonPath": "tileset.json",
                    "totalBytes": 123456789,
                    "entryCount": 4200,
                },
            },
        },
    )
    assert created.status_code == 201, created.text
    item_id = created.json()["itemId"]

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]
    assert body["kind"] == "tileset3d"
    assert body["tileset3d"] == {
        "sourceKey": "tenant-1/abc/city.zip",
        "tilesetJsonPath": "tileset.json",
        "totalBytes": 123456789,
        "entryCount": 4200,
    }


def test_tileset3d_config_requires_tileset3d_payload(client):
    created = client.post(
        "/configs",
        json={"title": "Cassé", "config": {"kind": "tileset3d"}},
    )
    assert created.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_schema.py -v`
Expected: FAIL — `kind` rejects `"tileset3d"` as an invalid Pydantic literal value.

- [ ] **Step 3: Implement the schema changes**

In `core/app/configs/schemas.py`, add the `Tileset3DPayload` class right before `class PrintLayout(BaseModel):`:

```python
class Tileset3DPayload(BaseModel):
    sourceKey: str
    tilesetJsonPath: str
    totalBytes: int
    entryCount: int
```

Then update `BuilderConfig` (replace the `kind` Literal and add the field + validator branch):

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert", "report", "tileset3d"]
```

```python
    report: ReportSchedulePayload | None = None
    tileset3d: Tileset3DPayload | None = None
    printLayout: PrintLayout | None = None
```

```python
        if self.kind == "report" and self.report is None:
            raise ValueError("report config requires a report payload")
        if self.kind == "tileset3d" and self.tileset3d is None:
            raise ValueError("tileset3d config requires a tileset3d payload")
        return self
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_schema.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: all previously-passing tests still pass (a `Literal` extension and an additive optional field are backward-compatible).

- [ ] **Step 6: Commit**

```bash
cd core && git add app/configs/schemas.py tests/test_tileset3d_schema.py
git commit -m "feat(core): Tileset3DPayload and BuilderConfig kind=tileset3d"
```

---

### Task 3: Core storage — `S3RangeFile` + zip validation

**Files:**
- Create: `core/app/tileset3d/storage.py`
- Test: `core/tests/test_tileset3d_storage.py`

**Interfaces:**
- Consumes: none.
- Produces: `S3RangeFile(client, *, bucket: str, key: str)` — file-like object (`read`/`seek`/`tell`/`seekable`) backed by ranged S3 GETs; `Tileset3DValidationError(ValueError)`; `ValidationResult(entry_count: int, total_bytes: int)`; `validate_tileset_zip(range_file, *, max_entries: int, max_total_bytes: int, max_entry_bytes: int) -> ValidationResult`. Consumed by Task 5 (finalize task) and Task 6 (read route).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_tileset3d_storage.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from botocore.exceptions import ClientError

from app.tileset3d.storage import S3RangeFile, Tileset3DValidationError, validate_tileset_zip


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        data = self.objects[Key]
        if Range is None:
            body = data
        else:
            start, end = Range.removeprefix("bytes=").split("-")
            body = data[int(start):int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(body)}


def _zip_bytes(entries: dict[str, bytes]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        for name, content in entries.items():
            zf.writestr(name, content)
    return buf.getvalue()


def _valid_tileset_entries() -> dict[str, bytes]:
    tileset_json = json.dumps({"asset": {"version": "1.0"}, "root": {}}).encode()
    return {"tileset.json": tileset_json, "tiles/0.b3dm": b"\x00" * 32}


def test_s3rangefile_reads_full_content_via_ranged_gets():
    data = b"0123456789" * 100
    client = _FakeS3Client({"k": data})
    f = S3RangeFile(client, bucket="b", key="k")
    assert f.read(10) == data[:10]
    assert f.tell() == 10
    f.seek(0)
    assert f.read() == data


def test_s3rangefile_supports_zipfile_random_access():
    zip_bytes = _zip_bytes(_valid_tileset_entries())
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with zipfile.ZipFile(f) as zf:
        assert zf.read("tileset.json") == _valid_tileset_entries()["tileset.json"]


def test_validate_tileset_zip_accepts_a_valid_archive():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    result = validate_tileset_zip(
        f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000,
    )
    assert result.entry_count == 2
    assert result.total_bytes == len(entries["tileset.json"]) + len(entries["tiles/0.b3dm"])


def test_validate_tileset_zip_rejects_missing_tileset_json():
    zip_bytes = _zip_bytes({"other.txt": b"x"})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="tileset.json"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_invalid_tileset_json_content():
    zip_bytes = _zip_bytes({"tileset.json": b"not json"})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="JSON"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_tileset_json_missing_asset_version():
    zip_bytes = _zip_bytes({"tileset.json": json.dumps({"root": {}}).encode()})
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="asset.version"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_too_many_entries():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="entrées"):
        validate_tileset_zip(f, max_entries=1, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_total_size_over_cap():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="totale"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=1, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_single_entry_over_cap():
    entries = _valid_tileset_entries()
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="volumineuse"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=1)


def test_validate_tileset_zip_rejects_path_traversal_entry_name():
    entries = _valid_tileset_entries()
    entries["../../etc/passwd"] = b"x"
    zip_bytes = _zip_bytes(entries)
    client = _FakeS3Client({"k": zip_bytes})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="non sûr"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)


def test_validate_tileset_zip_rejects_a_non_zip_object():
    client = _FakeS3Client({"k": b"not a zip file at all"})
    f = S3RangeFile(client, bucket="b", key="k")
    with pytest.raises(Tileset3DValidationError, match="zip invalide"):
        validate_tileset_zip(f, max_entries=100, max_total_bytes=10_000, max_entry_bytes=10_000)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tileset3d.storage'`.

- [ ] **Step 3: Implement `S3RangeFile` and `validate_tileset_zip`**

Create `core/app/tileset3d/storage.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Lecture d'un tileset 3D Tiles hébergé sans jamais l'extraire ni le
télécharger en entier (design §3) : S3RangeFile expose une interface
fichier (read/seek/tell) à zipfile.ZipFile, chaque accès se traduisant en
GET S3 avec un en-tête Range. zipfile ne lit ainsi que l'EOCD + la table
centrale à l'ouverture — coût constant, indépendant du volume de données du
tileset."""
import json
import zipfile
from dataclasses import dataclass


class Tileset3DValidationError(ValueError):
    pass


@dataclass(frozen=True)
class ValidationResult:
    entry_count: int
    total_bytes: int


class S3RangeFile:
    def __init__(self, client, *, bucket: str, key: str):
        self._client = client
        self._bucket = bucket
        self._key = key
        self._pos = 0
        self._size = client.head_object(Bucket=bucket, Key=key)["ContentLength"]

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = 0) -> int:
        if whence == 0:
            self._pos = offset
        elif whence == 1:
            self._pos += offset
        elif whence == 2:
            self._pos = self._size + offset
        else:
            raise ValueError(f"unsupported whence: {whence}")
        return self._pos

    def read(self, size: int | None = -1) -> bytes:
        if self._pos >= self._size:
            return b""
        end = self._size - 1 if size is None or size < 0 else min(self._pos + size, self._size) - 1
        obj = self._client.get_object(
            Bucket=self._bucket, Key=self._key, Range=f"bytes={self._pos}-{end}",
        )
        data = obj["Body"].read()
        self._pos += len(data)
        return data


def _is_unsafe_entry_name(name: str) -> bool:
    return name.startswith("/") or ".." in name.split("/")


def validate_tileset_zip(
    range_file: S3RangeFile, *, max_entries: int, max_total_bytes: int, max_entry_bytes: int,
) -> ValidationResult:
    try:
        zf = zipfile.ZipFile(range_file)
    except zipfile.BadZipFile as exc:
        raise Tileset3DValidationError(f"archive zip invalide : {exc}") from exc

    infos = zf.infolist()
    if len(infos) > max_entries:
        raise Tileset3DValidationError(
            f"trop d'entrées dans l'archive ({len(infos)} > {max_entries})"
        )

    total_bytes = 0
    for info in infos:
        if _is_unsafe_entry_name(info.filename):
            raise Tileset3DValidationError(f"nom d'entrée non sûr : {info.filename!r}")
        if info.file_size > max_entry_bytes:
            raise Tileset3DValidationError(
                f"entrée trop volumineuse une fois décompressée : {info.filename!r} "
                f"({info.file_size} > {max_entry_bytes})"
            )
        total_bytes += info.file_size

    if total_bytes > max_total_bytes:
        raise Tileset3DValidationError(
            f"taille décompressée totale trop grande ({total_bytes} > {max_total_bytes})"
        )

    if "tileset.json" not in zf.namelist():
        raise Tileset3DValidationError("aucun tileset.json à la racine de l'archive")

    raw = zf.read("tileset.json")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise Tileset3DValidationError(f"tileset.json n'est pas un JSON valide : {exc}") from exc
    if not isinstance(parsed, dict) or "version" not in parsed.get("asset", {}):
        raise Tileset3DValidationError(
            "tileset.json ne respecte pas le schéma 3D Tiles (asset.version manquant)"
        )

    return ValidationResult(entry_count=len(infos), total_bytes=total_bytes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_storage.py -v`
Expected: PASS (11 tests).

- [ ] **Step 5: Commit**

```bash
cd core && git add app/tileset3d/storage.py tests/test_tileset3d_storage.py
git commit -m "feat(core): S3RangeFile and tileset zip validation"
```

---

### Task 4: Core upload routes + capability flag + app wiring

**Files:**
- Create: `core/app/tileset3d/schemas.py`
- Create: `core/app/tileset3d/routes.py` (upload endpoints only — the read/proxy endpoint is added in Task 6)
- Modify: `core/app/auth/dependency.py` (add `is_tileset3d_enabled`)
- Modify: `core/app/main.py` (mount router behind flag, S3 client/bucket overrides)
- Modify: `core/app/jobs.py` (register `app.tileset3d.jobs` import path — module created in Task 5, safe to list now)
- Modify: `core/app/instance/routes.py` (expose `tileset3dEnabled`)
- Modify: `core/pyproject.toml` (import-linter layers)
- Test: `core/tests/test_tileset3d_enabled_flag.py`
- Test: `core/tests/test_tileset3d_routes.py`

**Interfaces:**
- Consumes: `repository.create_job`/`get_job`/`mark_finalizing` (Task 1); reuses `app.ingestion.storage.ensure_uploads_bucket` and `app.ingestion.routes.get_s3_client` verbatim (same reuse pattern as `app.export`).
- Produces: `POST /tileset3d/uploads` → `{jobId}`; `POST /tileset3d/uploads/{job_id}/parts/{part_number}/presign` → `{uploadUrl}`; `POST /tileset3d/uploads/{job_id}/complete` (204); `GET /tileset3d/uploads/{job_id}` → `{status, errorMessage, itemId}`; `is_tileset3d_enabled() -> bool`; `InstanceInfo` gains `tileset3dEnabled`. `routes.get_task_deferrer` defers a task named `finalize_tileset3d_task` (implemented Task 5 — deferring an as-yet-unimplemented but already-registered task name is safe with procrastinate, and this task's tests override the deferrer so the real task is never invoked).

- [ ] **Step 1: Write the failing capability-flag test**

Create `core/tests/test_tileset3d_enabled_flag.py` (mirrors `test_export_enabled_flag.py`):

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_tileset3d_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_tileset3d_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_TILESET3D_ENABLED", raising=False)
    assert is_tileset3d_enabled() is False


def test_is_tileset3d_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
    assert is_tileset3d_enabled() is True
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "false")
    assert is_tileset3d_enabled() is False


@pytest.fixture()
def env():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        admin = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="admin",
            email=None, first_name="", last_name="", bootstrap_admin=True,
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: admin
    app.dependency_overrides[get_current_user_optional] = lambda: admin
    return TestClient(app)


def test_instance_reports_tileset3d_disabled_by_default(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["tileset3dEnabled"] is False


def test_instance_reports_tileset3d_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["tileset3dEnabled"] is True


def test_upload_routes_absent_when_disabled(monkeypatch):
    monkeypatch.delenv("CORE_TILESET3D_ENABLED", raising=False)
    app = create_app()
    client = TestClient(app)
    response = client.post("/tileset3d/uploads", json={"filename": "x.zip", "title": "X"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_tileset3d_enabled'`.

- [ ] **Step 3: Add the capability flag**

In `core/app/auth/dependency.py`, add after `is_export_enabled`:

```python
def is_tileset3d_enabled() -> bool:
    """CORE_TILESET3D_ENABLED — capacité instance-wide optionnelle, même
    convention que is_export_enabled : lue à chaque appel, sans cache.
    Défaut false : une instance qui monte en version ne provisionne rien de
    nouveau (bucket S3 dédié, route proxy) tant qu'elle n'a pas explicitement
    activé la capacité (design hébergement tileset3d §6)."""
    return os.environ.get("CORE_TILESET3D_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Write the failing upload-routes test**

Create `core/tests/test_tileset3d_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from botocore.exceptions import ClientError
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import routes as tileset3d_routes
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}
        self._next_upload_id = 0

    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def create_multipart_upload(self, Bucket, Key):  # noqa: N803
        self._next_upload_id += 1
        return {"UploadId": f"mpu-{self._next_upload_id}"}

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}?part={Params.get('PartNumber')}"

    def complete_multipart_upload(self, Bucket, Key, UploadId, MultipartUpload):  # noqa: N803
        self.objects[Key] = b"".join(b"part" for _ in MultipartUpload["Parts"])

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "NoSuchKey", "Message": "not found"}}, "GetObject")
        data = self.objects[Key]
        if Range is not None:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start):int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(data)}


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    fake_s3 = _FakeS3Client()
    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: fake_s3
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[tileset3d_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred, fake_s3


def test_create_upload_returns_job_id(env):
    client, *_ = env
    r = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"})
    assert r.status_code == 201, r.text
    assert "jobId" in r.json()


def test_presign_part_returns_upload_url(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/parts/1/presign")
    assert r.status_code == 200, r.text
    assert "uploadUrl" in r.json()


def test_presign_part_404_for_unknown_job(env):
    client, *_ = env
    r = client.post("/tileset3d/uploads/does-not-exist/parts/1/presign")
    assert r.status_code == 404


def test_presign_part_rejects_part_number_below_one(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/parts/0/presign")
    assert r.status_code == 422


def test_complete_upload_marks_finalizing_and_defers_task(env):
    client, Session, tenant, alice, deferred, _fake_s3 = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(
        f"/tileset3d/uploads/{job_id}/complete",
        json={"parts": [{"partNumber": 1, "etag": "\"abc\""}]},
    )
    assert r.status_code == 204, r.text
    assert deferred == [(job_id, tenant.id)]
    status = client.get(f"/tileset3d/uploads/{job_id}").json()
    assert status["status"] == "finalizing"


def test_complete_upload_rejects_empty_parts_list(env):
    client, *_ = env
    job_id = client.post("/tileset3d/uploads", json={"filename": "city.zip", "title": "Ville"}).json()["jobId"]
    r = client.post(f"/tileset3d/uploads/{job_id}/complete", json={"parts": []})
    assert r.status_code == 422


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    r = client.get("/tileset3d/uploads/does-not-exist")
    assert r.status_code == 404
```

Cross-tenant scoping for `get_job` itself is already covered at the repository layer by `test_get_job_scopes_by_tenant` in Task 1 — the route does nothing beyond call `repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)`, so an HTTP-level duplicate would only re-test the same repository behavior through more moving parts, not add real coverage.

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_enabled_flag.py tests/test_tileset3d_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tileset3d.routes'`, `/instance` doesn't report `tileset3dEnabled`.

- [ ] **Step 6: Implement schemas, routes, and wiring**

Create `core/app/tileset3d/schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class Tileset3DUploadCreate(BaseModel):
    filename: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)


class Tileset3DUploadCreated(BaseModel):
    jobId: str


class Tileset3DPartPresignResponse(BaseModel):
    uploadUrl: str


class Tileset3DPartInput(BaseModel):
    partNumber: int = Field(ge=1)
    etag: str = Field(min_length=1)


class Tileset3DCompleteRequest(BaseModel):
    parts: list[Tileset3DPartInput] = Field(min_length=1)


class Tileset3DJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    itemId: str | None
```

Create `core/app/tileset3d/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de tilesets 3D Tiles — montées uniquement
quand CORE_TILESET3D_ENABLED est actif (app.main, à la construction de
l'app, même patron que app.pipelines/app.export). Le proxy de lecture
(GET /tileset3d/{item_id}/{path}) est ajouté dans ce même module en Task 6."""
import os
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket
from app.tileset3d import repository as repo
from app.tileset3d.schemas import (
    Tileset3DCompleteRequest, Tileset3DJobStatus, Tileset3DPartPresignResponse,
    Tileset3DUploadCreate, Tileset3DUploadCreated,
)
from app.users.models import User

router = APIRouter()


def get_tileset3d_bucket() -> str:
    return os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.tileset3d.jobs import finalize_tileset3d_task

        finalize_tileset3d_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/tileset3d/uploads", response_model=Tileset3DUploadCreated, status_code=201)
def create_tileset3d_upload(
    body: Tileset3DUploadCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Tileset3DUploadCreated:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    mp = s3.create_multipart_upload(Bucket=bucket, Key=key)
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id, source_key=key,
        upload_id=mp["UploadId"], filename=body.filename, title=body.title,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="tileset3d.job_create", object_type="tileset3d_job", object_id=job.id,
        payload={"filename": body.filename, "title": body.title},
    )
    session.commit()
    return Tileset3DUploadCreated(jobId=job.id)


@router.post("/tileset3d/uploads/{job_id}/parts/{part_number}/presign", response_model=Tileset3DPartPresignResponse)
def presign_tileset3d_part(
    job_id: str, part_number: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Tileset3DPartPresignResponse:
    if part_number < 1:
        raise HTTPException(status_code=422, detail="partNumber must be >= 1")
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    url = s3.generate_presigned_url(
        "upload_part",
        Params={"Bucket": bucket, "Key": job.source_key, "PartNumber": part_number, "UploadId": job.upload_id},
        ExpiresIn=900,
    )
    return Tileset3DPartPresignResponse(uploadUrl=url)


@router.post("/tileset3d/uploads/{job_id}/complete", status_code=204)
def complete_tileset3d_upload(
    job_id: str, body: Tileset3DCompleteRequest,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> None:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    s3.complete_multipart_upload(
        Bucket=bucket, Key=job.source_key, UploadId=job.upload_id,
        MultipartUpload={"Parts": [{"PartNumber": p.partNumber, "ETag": p.etag} for p in body.parts]},
    )
    repo.mark_finalizing(session, job_id=job.id)
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="tileset3d.upload_complete", object_type="tileset3d_job", object_id=job.id, payload={},
    )
    # Commit avant de déférer : même raison que app.ingestion.routes.create_upload_job.
    session.commit()
    defer_task(job.id, user.tenant_id)


@router.get("/tileset3d/uploads/{job_id}", response_model=Tileset3DJobStatus)
def get_tileset3d_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Tileset3DJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Tileset3DJobStatus(status=job.status, errorMessage=job.error_message, itemId=job.item_id)
```

In `core/app/main.py`:

Add the import near the other route imports (alphabetical, after `from app.stac import routes as stac_routes`):

```python
from app.tileset3d import routes as tileset3d_routes
```

Add to the `is_etl_enabled`/`is_export_enabled` import line:

```python
from app.auth.dependency import is_etl_enabled, is_export_enabled, is_read_only_mode, is_tileset3d_enabled
```

Add the router mount next to the other capability-gated mounts:

```python
    if is_export_enabled():
        app.include_router(export_routes.router)
    if is_tileset3d_enabled():
        app.include_router(tileset3d_routes.router)
```

Add the S3 client/bucket overrides in the same `if s3_endpoint and s3_access_key and s3_secret_key:` block that already wires `ingestion_routes`/`export_routes` (reuses `ingestion_routes.get_s3_client`, same key, per the existing comment convention):

```python
        s3_tileset3d_bucket = os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")
        app.dependency_overrides[tileset3d_routes.get_tileset3d_bucket] = lambda: s3_tileset3d_bucket
```

(Insert this right after the existing `app.dependency_overrides[export_routes.get_exports_bucket] = ...` line, inside the same `if` block — no new `if` needed since it reuses the exact same S3 credentials.)

In `core/app/instance/routes.py`, add the flag:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import is_etl_enabled, is_export_enabled, is_read_only_mode, is_tileset3d_enabled

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
    }
```

In `core/app/jobs.py`, add `"app.tileset3d.jobs"` to `import_paths` (the module is implemented in Task 5 — listing it now is safe, `perform_import_paths()` only runs when the worker actually starts):

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs", "app.reports.jobs", "app.tileset3d.jobs",
    ],
```

In `core/pyproject.toml`, insert `"app.tileset3d"` into the `layers` list right after `"app.export"` (it depends on `app.ingestion.storage`/`app.ingestion.routes`, same as `app.export`, so it must sit above `app.ingestion`):

```toml
    "app.export",
    "app.tileset3d",
    "app.secrets",
    "app.ingestion",
```

And add the matching `app.db -> app.tileset3d.models` line to `ignore_imports`, next to the other `app.db -> app.X.models` lines:

```toml
    "app.db -> app.export.models",
    "app.db -> app.tileset3d.models",
    "app.db -> app.reports.models",
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_enabled_flag.py tests/test_tileset3d_routes.py -v`
Expected: PASS (all tests). Note: `test_complete_upload_marks_finalizing_and_defers_task` will only pass once Task 1's `mark_finalizing` and this task's route wiring are both in place — it does not require Task 5's real `finalize_tileset3d_task` body, because the test overrides `get_task_deferrer`.

- [ ] **Step 8: Run the layered-architecture check**

Run: `cd core && uv run lint-imports`
Expected: PASS — no contract violation (`app.tileset3d` sits above `app.ingestion`, matching its one real dependency).

- [ ] **Step 9: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: all tests pass.

- [ ] **Step 10: Commit**

```bash
cd core && git add app/tileset3d/schemas.py app/tileset3d/routes.py app/auth/dependency.py app/main.py app/instance/routes.py app/jobs.py pyproject.toml tests/test_tileset3d_enabled_flag.py tests/test_tileset3d_routes.py
git commit -m "feat(core): tileset3d upload routes, capability flag, and app wiring"
```

---

### Task 5: Core finalize task

**Files:**
- Create: `core/app/tileset3d/jobs.py`
- Test: `core/tests/test_tileset3d_jobs.py`

**Interfaces:**
- Consumes: `repository.get_job`/`mark_done`/`mark_error` (Task 1); `Tileset3DPayload`/`BuilderConfig` (Task 2); `S3RangeFile`/`validate_tileset_zip`/`Tileset3DValidationError` (Task 3); `app.items.repository.create_item`; `app.configs.repository.create_config`.
- Produces: `finalize_tileset3d_task(job_id: str, tenant_id: str) -> None` (procrastinate task, queue `"tileset3d"`), registered in `app.jobs` import paths (already added Task 4). On success: job `status="done"`, `item_id` set, a new `Item(resource_type="tileset3d")` + `BuilderConfig(kind="tileset3d")` exist. On any failure: job `status="error"` with a message, no item/config created.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_tileset3d_jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from botocore.exceptions import ClientError

from app.configs import repository as configs_repo
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.tileset3d import jobs as tileset3d_jobs
from app.tileset3d import repository as tileset3d_repo
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects

    def head_object(self, Bucket, Key):  # noqa: N803
        if Key not in self.objects:
            raise ClientError({"Error": {"Code": "404", "Message": "not found"}}, "HeadObject")
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key, Range=None):  # noqa: N803
        data = self.objects[Key]
        if Range is not None:
            start, end = Range.removeprefix("bytes=").split("-")
            data = data[int(start):int(end) + 1]

        class _Body:
            def __init__(self, chunk: bytes):
                self._chunk = chunk

            def read(self) -> bytes:
                return self._chunk

        return {"Body": _Body(data)}


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TILESET3D_MAX_ENTRIES", "1000")
    monkeypatch.setenv("CORE_TILESET3D_MAX_TOTAL_BYTES", "10000000")
    monkeypatch.setenv("CORE_TILESET3D_MAX_ENTRY_BYTES", "10000000")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    return Session, tenant, alice


def _make_engine_conn_env(monkeypatch, tmp_path):
    db_path = tmp_path / "t.db"
    monkeypatch.setenv("DATABASE_URL", f"sqlite+pysqlite:///{db_path}")
    return db_path


def test_finalize_task_creates_item_and_config_on_success(env, monkeypatch, tmp_path):
    Session, tenant, alice = env
    db_path = _make_engine_conn_env(monkeypatch, tmp_path)
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    real_session_factory = make_session_factory(engine)
    with request_scoped_session(real_session_factory) as s:
        get_or_create_default_tenant(s)
        get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        job = tileset3d_repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k",
            upload_id="mpu-1", filename="city.zip", title="Ville",
        )
        s.commit()
        job_id = job.id

    fake_s3 = _FakeS3Client({"k": _valid_zip_bytes()})
    monkeypatch.setattr(tileset3d_jobs, "s3_client_from_env", lambda: fake_s3)

    tileset3d_jobs.finalize_tileset3d_task(job_id=job_id, tenant_id=tenant.id)

    with request_scoped_session(real_session_factory) as s:
        job = tileset3d_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id is not None
        item = items_repo.get_item(s, tenant_id=tenant.id, item_id=job.item_id)
        assert item.resourceType == "tileset3d"
        assert item.title == "Ville"
        config = configs_repo.get_config_by_item(s, job.item_id)
        assert config.config.kind == "tileset3d"
        assert config.config.tileset3d.sourceKey == "k"
        assert config.config.tileset3d.tilesetJsonPath == "tileset.json"
        assert config.config.tileset3d.entryCount == 2


def test_finalize_task_marks_error_on_invalid_zip_without_creating_an_item(env, monkeypatch, tmp_path):
    Session, tenant, alice = env
    db_path = _make_engine_conn_env(monkeypatch, tmp_path)
    engine = make_engine(f"sqlite+pysqlite:///{db_path}")
    init_db(engine)
    real_session_factory = make_session_factory(engine)
    with request_scoped_session(real_session_factory) as s:
        get_or_create_default_tenant(s)
        get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        job = tileset3d_repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id, source_key="k",
            upload_id="mpu-1", filename="bad.zip", title="Cassé",
        )
        s.commit()
        job_id = job.id

    fake_s3 = _FakeS3Client({"k": b"not a zip"})
    monkeypatch.setattr(tileset3d_jobs, "s3_client_from_env", lambda: fake_s3)

    tileset3d_jobs.finalize_tileset3d_task(job_id=job_id, tenant_id=tenant.id)

    with request_scoped_session(real_session_factory) as s:
        job = tileset3d_repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert "zip invalide" in job.error_message
        assert job.item_id is None


def test_finalize_task_is_a_noop_for_an_unknown_job(env, caplog):
    Session, tenant, alice = env
    tileset3d_jobs.finalize_tileset3d_task(job_id="does-not-exist", tenant_id=tenant.id)
    # No exception — mirrors app.ingestion.tasks.run_ingestion_task's behavior
    # for a job that vanished (should never happen, but must not crash the worker).
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.tileset3d.jobs'`.

- [ ] **Step 3: Implement the finalize task**

Create `core/app/tileset3d/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate : valide le zip complété (S3RangeFile, jamais un
téléchargement complet) et, si valide, crée l'item + le BuilderConfig
résultants. Toute erreur (validation ou inattendue) marque le job "error",
jamais de job bloqué en pending/finalizing ("zombie") — même critère que
app.ingestion.tasks/app.export.jobs."""
import logging
import os

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.tileset3d import repository as tileset3d_repo
from app.tileset3d.storage import S3RangeFile, Tileset3DValidationError, validate_tileset_zip
from app.audit.writer import write_audit

logger = logging.getLogger(__name__)


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _tileset3d_bucket() -> str:
    return os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")


def _max_entries() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_ENTRIES", "200000"))


def _max_total_bytes() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_TOTAL_BYTES", str(20 * 1024 * 1024 * 1024)))


def _max_entry_bytes() -> int:
    return int(os.environ.get("CORE_TILESET3D_MAX_ENTRY_BYTES", str(2 * 1024 * 1024 * 1024)))


@app.task(queue="tileset3d")
def finalize_tileset3d_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    with request_scoped_session(session_factory) as session:
        job = tileset3d_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("tileset3d job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        source_key, filename, title, created_by = job.source_key, job.filename, job.title, job.created_by

    try:
        s3 = s3_client_from_env()
        range_file = S3RangeFile(s3, bucket=_tileset3d_bucket(), key=source_key)
        result = validate_tileset_zip(
            range_file, max_entries=_max_entries(),
            max_total_bytes=_max_total_bytes(), max_entry_bytes=_max_entry_bytes(),
        )
        with request_scoped_session(session_factory) as session:
            item = items_repo.create_item(
                session, tenant_id=tenant_id, owner_id=created_by,
                resource_type="tileset3d", title=title,
            )
            write_audit(
                session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title, "filename": filename},
            )
            config = BuilderConfig(
                kind="tileset3d",
                tileset3d=Tileset3DPayload(
                    sourceKey=source_key, tilesetJsonPath="tileset.json",
                    totalBytes=result.total_bytes, entryCount=result.entry_count,
                ),
            )
            configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
            tileset3d_repo.mark_done(session, job_id=job_id, item_id=item.id)
    except Tileset3DValidationError as exc:
        with request_scoped_session(session_factory) as session:
            tileset3d_repo.mark_error(session, job_id=job_id, error_message=str(exc))
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("tileset3d job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            tileset3d_repo.mark_error(session, job_id=job_id, error_message=f"erreur interne : {exc}")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_jobs.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the layered-architecture check and full suite**

Run: `cd core && uv run lint-imports && uv run pytest -q`
Expected: both PASS.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/tileset3d/jobs.py tests/test_tileset3d_jobs.py
git commit -m "feat(core): tileset3d finalize task (validate, create item+config)"
```

---

### Task 6: Core read/proxy route

**Files:**
- Modify: `core/app/tileset3d/routes.py` (add the read endpoint)
- Test: `core/tests/test_tileset3d_routes.py` (extend)

**Interfaces:**
- Consumes: `app.items.repository.get_access_facts`; `app.sharing.authorization.can`; `app.configs.repository.get_config_by_item`; `S3RangeFile` (Task 3).
- Produces: `GET /tileset3d/{item_id}/{path:path}` → entry bytes with a guessed `Content-Type`, `404` if the item doesn't exist/isn't readable by the caller or the entry doesn't exist in the zip.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_tileset3d_routes.py` (reuses the `env` fixture and `_FakeS3Client` already defined in that file):

```python
import io
import json
import zipfile

from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Tileset3DPayload
from app.items import repository as items_repo


def _valid_zip_bytes() -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("tileset.json", json.dumps({"asset": {"version": "1.0"}, "root": {}}))
        zf.writestr("tiles/0.b3dm", b"\x00" * 16)
    return buf.getvalue()


def _seed_hosted_tileset_item(session, *, tenant_id, owner_id, fake_s3, key="tenant/x/city.zip"):
    fake_s3.objects[key] = _valid_zip_bytes()
    item = items_repo.create_item(
        session, tenant_id=tenant_id, owner_id=owner_id, resource_type="tileset3d", title="Ville",
    )
    config = BuilderConfig(
        kind="tileset3d",
        tileset3d=Tileset3DPayload(sourceKey=key, tilesetJsonPath="tileset.json", totalBytes=100, entryCount=2),
    )
    configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
    return item.id


def test_read_tileset3d_entry_returns_tileset_json(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 200, r.text
    assert r.headers["content-type"].startswith("application/json")
    assert json.loads(r.content)["asset"]["version"] == "1.0"


def test_read_tileset3d_entry_returns_tile_binary(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tiles/0.b3dm")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/octet-stream"
    assert r.content == b"\x00" * 16


def test_read_tileset3d_entry_404_for_missing_entry(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=alice.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/does-not-exist.b3dm")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/tileset3d/does-not-exist/tileset.json")
    assert r.status_code == 404


def test_read_tileset3d_entry_404_for_a_private_item_owned_by_another_user(env):
    client, Session, tenant, alice, _deferred, fake_s3 = env
    with Session() as s:
        bob = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="b", username="bob",
            email=None, first_name="", last_name="",
        )
        item_id = _seed_hosted_tileset_item(s, tenant_id=tenant.id, owner_id=bob.id, fake_s3=fake_s3)
        s.commit()
    r = client.get(f"/tileset3d/{item_id}/tileset.json")
    assert r.status_code == 404
```

No new import is needed for this test — `core/tests/test_tileset3d_routes.py` already imports `get_or_create_user` (Task 4, used by its `env` fixture to create `alice`); this test's `bob = get_or_create_user(...)` reuses that same import.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_tileset3d_routes.py -k read_tileset3d_entry -v`
Expected: FAIL — 404 on every request (no `/tileset3d/{item_id}/{path}` route registered yet).

- [ ] **Step 3: Implement the read route**

Add to `core/app/tileset3d/routes.py` — new imports at the top:

```python
from fastapi import Response

from app.configs import repository as configs_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.tileset3d.storage import S3RangeFile
```

New module-level constant and helper, placed above the route functions:

```python
_CONTENT_TYPES = {
    ".json": "application/json",
    ".gltf": "application/json",
    ".b3dm": "application/octet-stream",
    ".i3dm": "application/octet-stream",
    ".pnts": "application/octet-stream",
    ".cmpt": "application/octet-stream",
    ".glb": "application/octet-stream",
}


def _content_type_for(path: str) -> str:
    for ext, content_type in _CONTENT_TYPES.items():
        if path.endswith(ext):
            return content_type
    return "application/octet-stream"
```

New route, appended at the end of the file:

```python
@router.get("/tileset3d/{item_id}/{path:path}")
def read_tileset3d_entry(
    item_id: str, path: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_tileset3d_bucket),
) -> Response:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.tileset3d is None:
        raise HTTPException(status_code=404, detail="tileset not found")
    payload = config.config.tileset3d

    import zipfile

    range_file = S3RangeFile(s3, bucket=bucket, key=payload.sourceKey)
    try:
        with zipfile.ZipFile(range_file) as zf:
            data = zf.read(path)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="entry not found") from exc

    return Response(
        content=data, media_type=_content_type_for(path),
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

(The `import zipfile` is placed inline in the function rather than at module top only to keep the diff local to this step — move it to the top-level imports alongside the others added in this step; either placement is fine, top-level is the repo's usual convention, so put it there in the final file.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_tileset3d_routes.py -v`
Expected: PASS (all tests, including the ones from Task 4).

- [ ] **Step 5: Run the full core suite**

Run: `cd core && uv run pytest -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/tileset3d/routes.py tests/test_tileset3d_routes.py
git commit -m "feat(core): tileset3d read/proxy route"
```

---

### Task 7: Regenerate OpenAPI spec and shell generated types

**Files:**
- Modify: `core/openapi.json` (regenerated, not hand-edited)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)

**Interfaces:** none (mechanical regeneration — CLAUDE.md flags forgetting this step as a recurring, multi-occurrence mistake on this repo).

- [ ] **Step 1: Enable the capability flag and regenerate `openapi.json`**

Run:

```bash
cd core && CORE_TILESET3D_ENABLED=true CORE_EXPORT_ENABLED=false CORE_ETL_ENABLED=false uv run python scripts/export_openapi.py openapi.json
```

Expected: `core/openapi.json` changes, purely additively (new `/tileset3d/...` paths and `Tileset3DPayload`/`Tileset3DUploadCreate`/etc. schemas appear; nothing existing is removed or changed in an incompatible way).

- [ ] **Step 2: Verify the diff is additive**

Run: `cd core && git diff --stat openapi.json`
Expected: only additions (new lines), review with `git diff openapi.json` that no existing path/schema was modified or removed.

**Important:** this repo's CI generates `openapi.json` with `CORE_TILESET3D_ENABLED` (and `CORE_ETL_ENABLED`/`CORE_EXPORT_ENABLED`) **unset** (matching the established precedent documented in CLAUDE.md for `app.pipelines`/`app.export` — the committed `openapi.json` reflects the default-disabled surface, not every capability flag turned on at once). Re-run Step 1 **without** setting `CORE_TILESET3D_ENABLED=true` before committing, so the checked-in file matches what CI regenerates:

```bash
cd core && uv run python scripts/export_openapi.py openapi.json
git diff --stat openapi.json
```

Expected: this second run shows **no diff** relative to the pre-Task-7 committed file — the new `/tileset3d/...` routes are gated behind the flag and CI never enables it, exactly like `/pipelines/...` and `/export/...` already aren't in the committed spec today. Confirm with `grep -c tileset3d openapi.json` — expect `0`.

- [ ] **Step 3: Regenerate the shell's generated TypeScript types**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` is unchanged (since `openapi.json` itself is unchanged after Step 2 — the flag-gated routes never reach the committed spec). Confirm with `git status --short shell/src/api/generated/core-schema.d.ts` — expect no output.

- [ ] **Step 4: Confirm nothing needs committing**

Run: `git status --short core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: no output — this task is a verification step (proving the capability-flag discipline holds) rather than a code change. If either file *does* show a diff at this point, stop and investigate before continuing to Task 8 — it means something in Task 4–6 leaked into the always-on route surface.

- [ ] **Step 5: No commit needed**

This task intentionally produces no diff to commit — it exists to catch the exact class of mistake CLAUDE.md flags repeatedly on this repo (forgetting to regenerate, or regenerating with the wrong flags on). If Step 4 found a diff and you fixed the root cause, commit that fix under its own message; otherwise move on to Task 8.

---

### Task 8: Shell types — `ResourceType`, `LayerSource`, `InstanceInfo`, `ItemClient`

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `ResourceType` gains `"tileset3d"`; `LayerSource.service` gains `"tileset3d"`, `.kind` gains `"tiles3d"`; `InstanceInfo` gains `tileset3dEnabled: boolean`; `ItemClient` gains `createTileset3DUpload`, `presignTileset3DUploadPart`, `completeTileset3DUpload`, `getTileset3DUploadJob`, `getAuthToken?`. Consumed by Task 9 (`itemClient.ts` implementation), Task 10 (`LayerPicker`), Task 11 (`MapView`), Task 12 (`Tileset3DUploadButton`).

This task is a type-only change with no runtime behavior — `tsc --noEmit` is the verification, no new test file.

- [ ] **Step 1: Verify the baseline compiles**

Run: `cd shell && npm run build`
Expected: PASS (establishes the pre-change baseline before editing).

- [ ] **Step 2: Extend `ResourceType`**

In `shell/src/api/types.ts`, line 2:

```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert" | "report" | "tileset3d";
```

- [ ] **Step 3: Extend `LayerSource`**

Replace the `LayerSource` type (currently lines 84-93):

```ts
export type LayerSource = {
  id: string;
  title: string;
  service: "martin" | "core" | "external" | "tileset3d";
  kind: "vector" | "feature" | "raster" | "tiles3d";
  tilesUrl?: string;
  sourceLayer?: string;
  url?: string;
  featureCount?: number | null;
};
```

- [ ] **Step 4: Extend `InstanceInfo`**

Line 35:

```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; tileset3dEnabled: boolean };
```

- [ ] **Step 5: Extend `ItemClient`**

In the `ItemClient` interface, insert before the closing `}` (currently line 216, right after `getExportJob(jobId: string): Promise<ExportJob>;`):

```ts
  createTileset3DUpload(input: { filename: string; title: string }): Promise<{ jobId: string }>;
  presignTileset3DUploadPart(jobId: string, partNumber: number): Promise<{ uploadUrl: string }>;
  completeTileset3DUpload(jobId: string, parts: { partNumber: number; etag: string }[]): Promise<void>;
  getTileset3DUploadJob(jobId: string): Promise<{
    status: "pending" | "finalizing" | "done" | "error";
    errorMessage: string | null;
    itemId: string | null;
  }>;
  // Optional: absent on any ItemClient that doesn't need it (e.g. test mocks
  // cast via `as unknown as ItemClient`). Used by MapView to authenticate
  // Tile3DLayer requests against a hosted tileset's proxy route (design §4).
  getAuthToken?(): string | undefined;
```

- [ ] **Step 6: Verify it still compiles**

Run: `cd shell && npm run build`
Expected: FAIL — `createItemClient`'s returned object (in `itemClient.ts`) doesn't yet implement the four new required `ItemClient` methods (`getAuthToken` is optional, so it alone wouldn't fail the build, but the four upload/job methods are required).

This confirms the type change is wired correctly; Task 9 implements the missing methods.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/api/types.ts
git commit -m "feat(shell): types for hosted tileset3d items and upload client"
```

---

### Task 9: Shell `itemClient.ts` implementation

**Files:**
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `ItemClient` interface (Task 8); core routes from Task 4/6 (`POST /tileset3d/uploads`, `POST /tileset3d/uploads/{id}/parts/{n}/presign`, `POST /tileset3d/uploads/{id}/complete`, `GET /tileset3d/uploads/{id}`); existing `/items?type=...` route (already implemented, unrelated to this feature).
- Produces: the four `ItemClient` methods implemented; `fetchHostedTileset3dSources(q?: string): Promise<LayerSource[]>` (private helper, mirrors `fetchCoreCollections`) wired into `listLayerSources`; `getAuthToken: getToken` exposed on the returned client object.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("createTileset3DUpload posts filename/title and returns jobId", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
  );
  const result = await makeClient("abc").createTileset3DUpload({ filename: "city.zip", title: "Ville" });
  expect(result).toEqual({ jobId: "job-1" });
  expect(body).toEqual({ filename: "city.zip", title: "Ville" });
});

test("presignTileset3DUploadPart posts to the job/part route and returns an upload URL", async () => {
  server.use(
    http.post("https://core.test/tileset3d/uploads/job-1/parts/2/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-2" })),
  );
  const result = await makeClient("abc").presignTileset3DUploadPart("job-1", 2);
  expect(result).toEqual({ uploadUrl: "https://minio.test/part-2" });
});

test("completeTileset3DUpload posts the parts list", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads/job-1/complete", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient("abc").completeTileset3DUpload("job-1", [{ partNumber: 1, etag: "\"abc\"" }]);
  expect(body).toEqual({ parts: [{ partNumber: 1, etag: "\"abc\"" }] });
});

test("getTileset3DUploadJob returns the job status", async () => {
  server.use(
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" })),
  );
  const result = await makeClient("abc").getTileset3DUploadJob("job-1");
  expect(result).toEqual({ status: "done", errorMessage: null, itemId: "item-1" });
});

test("listLayerSources includes hosted tileset3d items", async () => {
  server.use(
    http.get("https://martin.test/catalog", () => HttpResponse.json({ tiles: {} })),
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/harvest/layers", () => HttpResponse.json({ layers: [] })),
    http.get("https://core.test/items", ({ request }) => {
      expect(new URL(request.url).searchParams.get("type")).toBe("tileset3d");
      return HttpResponse.json({
        items: [{ pk: "t1", resourceType: "tileset3d", title: "Ville", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false }],
        total: 1, page: 1, pageSize: 200,
      });
    }),
  );
  const sources = await makeClient("abc").listLayerSources();
  const hosted = sources.find((s) => s.id === "t1");
  expect(hosted).toMatchObject({
    title: "Ville", service: "tileset3d", kind: "tiles3d",
    url: "https://core.test/tileset3d/t1/tileset.json",
  });
});

test("getAuthToken exposes the client's current token", () => {
  const client = makeClient("secret-token");
  expect(client.getAuthToken?.()).toBe("secret-token");
});
```

Check whether `shell/src/api/itemClient.ts` already calls `fetchExternalRasterSources` inside `listLayerSources` and whether that call hits `/harvest/layers` unconditionally — the new test above adds an MSW handler for it defensively; if `Promise.allSettled` already tolerates a missing handler (it does, per the existing `listLayerSources still returns one service when the other fails` test), this handler is optional but keeps the test's intent explicit.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t "Tileset3D|listLayerSources includes hosted|getAuthToken exposes"`
Expected: FAIL — `client.createTileset3DUpload is not a function`, etc.

- [ ] **Step 3: Implement the client methods**

In `shell/src/api/itemClient.ts`, add the new private fetch helper near `fetchExternalRasterSources` (after it, before the closing of that group of helper functions):

```ts
async function fetchHostedTileset3dSources(
  coreUrl: string, getToken: () => string | undefined, q?: string,
): Promise<LayerSource[]> {
  const query = new URLSearchParams({ type: "tileset3d", pageSize: "200" });
  if (q) query.set("q", q);
  const token = getToken();
  const res = await fetch(`${coreUrl}/items?${query.toString()}`, {
    headers: token ? { Authorization: `Bearer ${token}` } : {},
  });
  if (!res.ok) throw new Error(`Request failed: ${res.status} /items`);
  const data = (await res.json()) as { items?: { pk: string; title: string }[] };
  return (data.items ?? []).map((item) => ({
    id: item.pk, title: item.title, service: "tileset3d" as const, kind: "tiles3d" as const,
    url: `${coreUrl}/tileset3d/${item.pk}/tileset.json`,
  }));
}
```

Note: this is defined as a free function (taking `coreUrl`/`getToken` as parameters, like `fetchMartinSources`/`fetchCoreCollections`/`fetchExternalRasterSources` already do) — it is called from inside `createItemClient` where those two values are in scope.

Update `listLayerSources` (inside `createItemClient`'s returned object) to include the new source:

```ts
    async listLayerSources(params?: { q?: string }): Promise<LayerSource[]> {
      const results = await Promise.allSettled([
        fetchMartinSources(params?.q),
        fetchCoreCollections(params?.q),
        fetchExternalRasterSources(params?.q),
        fetchHostedTileset3dSources(coreUrl, getToken, params?.q),
      ]);
      const fulfilled = results.filter(
        (r): r is PromiseFulfilledResult<LayerSource[]> => r.status === "fulfilled",
      );
      if (fulfilled.length === 0) {
        throw new Error("listLayerSources: all layer services failed");
      }
      return fulfilled.flatMap((r) => r.value);
    },
```

Add the four new methods at the end of the returned object literal, right after `runAnalyticsSql` (before the closing `};`):

```ts
    async createTileset3DUpload(input: { filename: string; title: string }) {
      return request<{ jobId: string }>("POST", "/tileset3d/uploads", input);
    },

    async presignTileset3DUploadPart(jobId: string, partNumber: number) {
      return request<{ uploadUrl: string }>(
        "POST", `/tileset3d/uploads/${jobId}/parts/${partNumber}/presign`,
      );
    },

    async completeTileset3DUpload(jobId: string, parts: { partNumber: number; etag: string }[]) {
      await request<void>("POST", `/tileset3d/uploads/${jobId}/complete`, { parts });
    },

    async getTileset3DUploadJob(jobId: string) {
      return request<{
        status: "pending" | "finalizing" | "done" | "error";
        errorMessage: string | null;
        itemId: string | null;
      }>("GET", `/tileset3d/uploads/${jobId}`);
    },

    getAuthToken: getToken,
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests in the file).

- [ ] **Step 5: Run the full shell test suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: both PASS — `npm run build` now succeeds since `createItemClient`'s returned object satisfies the extended `ItemClient` interface from Task 8.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): itemClient tileset3d upload methods and hosted source listing"
```

---

### Task 10: Shell `LayerPicker` — hosted tileset3d source branch

**Files:**
- Modify: `shell/src/map/LayerPicker.tsx`
- Test: `shell/src/map/LayerPicker.test.tsx`

**Interfaces:**
- Consumes: `LayerSource` (Task 8), `client.listLayerSources` (Task 9, already returns `tiles3d`-kind entries).
- Produces: `toMapLayer` correctly maps a `source.kind === "tiles3d"` entry to a `{ kind: "tiles3d", url }` `MapLayer` (previously it fell through to the `feature` catch-all branch — a real bug that Task 9's new source kind would otherwise trigger silently).

- [ ] **Step 1: Write the failing test**

`shell/src/map/LayerPicker.test.tsx` has a module-level `sources: LayerSource[]` fixture array (consumed by the file's `renderPicker(onAdd)` helper, which builds a `listLayerSources` mock returning it) and existing tests like `lists sources and emits a vector MapLayer on click` that click a source by its title and assert on the `MapLayer` passed to `onAdd`. Add a hosted-tileset3d entry to that same array, and a test following the exact same shape:

```ts
const sources: LayerSource[] = [
  { id: "communes", title: "Communes", service: "martin", kind: "vector",
    tilesUrl: "https://martin.test/communes/{z}/{x}/{y}", sourceLayer: "communes" },
  { id: "public.parcs", title: "Parcs", service: "core", kind: "feature",
    url: "https://core.test/collections/public.parcs/items", featureCount: 128 },
  { id: "public.legacy", title: "Legacy", service: "core", kind: "feature",
    url: "https://core.test/collections/public.legacy/items", featureCount: null },
  { id: "ext-ortho", title: "Orthophoto (WMS)", service: "external", kind: "raster",
    tilesUrl: "https://ows.example.com/wms?...&bbox={bbox-epsg-3857}" },
  { id: "t1", title: "Ville hébergée", service: "tileset3d", kind: "tiles3d",
    url: "https://core.test/tileset3d/t1/tileset.json" },
];
```

```tsx
test("clicking a hosted tileset3d source emits a tiles3d MapLayer with its proxy url", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Ville hébergée/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "tiles3d", url: "https://core.test/tileset3d/t1/tileset.json", visible: true,
  });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx -t "hosted tileset3d"`
Expected: FAIL — `onAdd` is called with `kind: "feature"` (the catch-all branch) instead of `kind: "tiles3d"`.

- [ ] **Step 3: Fix `toMapLayer`**

In `shell/src/map/LayerPicker.tsx`, insert a new branch in `toMapLayer` before the final `return { ..., kind: "feature", ... }`:

```ts
  if (source.kind === "raster") {
    return {
      id,
      title: source.title,
      visible: true,
      kind: "raster",
      tilesUrl: source.tilesUrl ?? "",
      opacity: 1,
    };
  }
  if (source.kind === "tiles3d") {
    return { id, title: source.title, visible: true, kind: "tiles3d", url: source.url ?? "" };
  }
  return { id, title: source.title, visible: true, kind: "feature", url: source.url ?? "" };
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/LayerPicker.test.tsx`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 5: Commit**

```bash
cd shell && git add src/map/LayerPicker.tsx src/map/LayerPicker.test.tsx
git commit -m "fix(shell): LayerPicker maps a tiles3d source to a tiles3d layer, not feature"
```

---

### Task 11: Shell `MapView` — authenticated requests for hosted tilesets

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Modify: `shell/src/pages/MapEditorPage.tsx`
- Modify: `shell/src/builder/widgets/mapWidget.tsx`
- Modify: `shell/src/builder/ExplorerDrawer.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `client.getAuthToken` (Task 9).
- Produces: `MapView` gains an optional `getAuthToken?: () => string | undefined` prop; a `tiles3d` layer whose `url` contains `/tileset3d/` gets `loadOptions: { fetch: { headers: { Authorization: "Bearer <token>" } } }` on its `Tile3DLayer`; an external-URL `tiles3d` layer (or any layer when `getAuthToken` is absent/returns `undefined`) is unaffected — no `loadOptions` at all, preserving current behavior exactly.

- [ ] **Step 1: Write the failing tests**

The file already mocks `@deck.gl/geo-layers`/`@loaders.gl/3d-tiles` at module level (top of file) and resets `overlayInstances.length = 0` in a `beforeEach`, and has a shared base `config: MapConfig` fixture (`{ basemap: { style: "https://demotiles.maplibre.org/style.json" }, view: { center: [2.35, 48.85], zoom: 5 }, layers: [] }`) that existing `tiles3d` tests extend via `{...config, layers: [...]}`, then read `overlayInstances[0].props.layers`. Add new tests in that exact style, near the existing `tiles3d` tests:

```tsx
test("attaches a bearer token to a hosted (/tileset3d/) tiles3d layer's requests", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://core.test/tileset3d/item-1/tileset.json" }],
  };
  render(<MapView config={cfg} getAuthToken={() => "secret-token"} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toEqual({ fetch: { headers: { Authorization: "Bearer secret-token" } } });
});

test("does not attach a bearer token to an external tiles3d layer even when getAuthToken is provided", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://example.test/tileset.json" }],
  };
  render(<MapView config={cfg} getAuthToken={() => "secret-token"} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});

test("does not attach a header for a hosted tileset when getAuthToken is absent", () => {
  const cfg: MapConfig = {
    ...config,
    layers: [{ id: "bldg", title: "Bâtiments", visible: true, kind: "tiles3d", url: "https://core.test/tileset3d/item-1/tileset.json" }],
  };
  render(<MapView config={cfg} />);
  const layers = overlayInstances[0].props.layers;
  expect(layers[0].props.loadOptions).toBeUndefined();
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx -t "bearer token"`
Expected: FAIL — `getAuthToken` prop doesn't exist / `loadOptions` is always `undefined`.

- [ ] **Step 3: Implement the prop and header injection**

In `shell/src/map/MapView.tsx`:

Add a module-level constant right after the existing `const TERRAIN_SOURCE_ID = "__terrain__";`:

```ts
// Path segment distinguishing a hosted tileset (served by our authenticated
// proxy, design §4) from an externally-hosted tileset.json — the latter
// must never receive our session's bearer token.
const HOSTED_TILESET3D_PATH = "/tileset3d/";
```

Update `buildTiles3DLayer` (currently lines 118-128) to accept and use an auth-token getter:

```ts
function buildTiles3DLayer(
  layer: Tiles3DMapLayer,
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
) {
  const token = layer.url.includes(HOSTED_TILESET3D_PATH) ? getAuthToken?.() : undefined;
  return new Tile3DLayer({
    id: layer.id,
    data: layer.url,
    loader: Tiles3DLoader,
    loadOptions: token ? { fetch: { headers: { Authorization: `Bearer ${token}` } } } : undefined,
    // Fired once the root tileset has loaded. Deck.gl loads 3D Tiles entirely
    // outside MapLibre's knowledge, so this is the only signal that tells the
    // export worker the tileset is actually on screen (see onReady below).
    onTilesetLoad: () => onTilesetLoad?.(tilesetKey(layer)),
  });
}
```

Update `applyDeckLayers` (currently lines 130-142) to thread the getter through:

```ts
function applyDeckLayers(
  overlay: MapboxOverlay,
  layers: MapConfig["layers"],
  onTilesetLoad?: (key: string) => void,
  getAuthToken?: () => string | undefined,
) {
  const deckLayers = layers
    .filter((l): l is DeckLayer => l.visible && l.kind === "deck")
    .map(buildDeckLayer);
  const tiles3dLayers = layers
    .filter((l): l is Tiles3DMapLayer => l.visible && l.kind === "tiles3d")
    .map((l) => buildTiles3DLayer(l, onTilesetLoad, getAuthToken));
  overlay.setProps({ layers: [...deckLayers, ...tiles3dLayers] });
}
```

Add the prop to the `forwardRef` props type (currently lines 164-183), right after `hideLegend?: boolean;`:

```ts
    // Authenticates Tile3DLayer requests against a hosted (design
    // /tileset3d/) tileset's proxy route — never sent for external tileset
    // URLs (see HOSTED_TILESET3D_PATH check in buildTiles3DLayer). Absent by
    // default: a MapView with no hosted tiles3d layer needs no auth plumbing.
    getAuthToken?: () => string | undefined;
```

Destructure it in the function signature (currently line 184):

```ts
>(function MapView({ config, onViewChange, onFeatureClick, onReady, hideLegend, getAuthToken }, ref) {
```

Add a ref for it, mirroring the existing `onFeatureClickRef` pattern (near the other ref declarations around lines 204-217):

```ts
  const getAuthTokenRef = useRef(getAuthToken);
```

```ts
  useEffect(() => {
    getAuthTokenRef.current = getAuthToken;
  }, [getAuthToken]);
```

Update both `applyDeckLayers` call sites to pass the ref's current value — line 265:

```ts
      applyDeckLayers(overlay, layersRef.current, handleTilesetLoad, getAuthTokenRef.current);
```

and line 298:

```ts
    applyDeckLayers(overlay, config.layers, handleTilesetLoad, getAuthTokenRef.current);
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/map/MapView.test.tsx`
Expected: PASS (all tests in the file, including the three new ones and every pre-existing `tiles3d` test unaffected).

- [ ] **Step 5: Thread `getAuthToken` through the three call sites**

In `shell/src/pages/MapEditorPage.tsx`, add the import and hook call, and pass the prop on both `<MapView>` usages:

```ts
import { useItemClient } from "../api/ItemClientProvider";
```

```ts
export function MapEditorPage({ pk }: { pk: string }) {
  const client = useItemClient();
  const query = useMapConfig(pk);
```

Line 65 (export-render branch — also correct: `exportAwareToken` already prefers the Playwright worker's `exportToken` query param over the normal session token, so a captured export of a map with a hosted tileset authenticates as the exporting user automatically):

```tsx
        <MapView config={draft} onReady={markExportReady} hideLegend getAuthToken={client.getAuthToken} />
```

Line 104:

```tsx
        <MapView ref={mapViewRef} config={draft} onViewChange={setView} getAuthToken={client.getAuthToken} />
```

In `shell/src/builder/widgets/mapWidget.tsx` (already has `const client = useItemClient();` in scope at line 120), add the prop to the `<MapView` at line 175:

```tsx
            <MapView
              ref={handle}
              config={config}
              getAuthToken={client.getAuthToken}
              onViewChange={(v) => {
```

In `shell/src/builder/ExplorerDrawer.tsx` (already has `const client = useItemClient();` in scope at line 24), update line 93:

```tsx
          <MapView ref={mapHandle} config={mapConfig} getAuthToken={client.getAuthToken} />
```

- [ ] **Step 6: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 7: Commit**

```bash
cd shell && git add src/map/MapView.tsx src/map/MapView.test.tsx src/pages/MapEditorPage.tsx src/builder/widgets/mapWidget.tsx src/builder/ExplorerDrawer.tsx
git commit -m "feat(shell): authenticate Tile3DLayer requests for hosted tilesets"
```

---

### Task 12: Shell upload UI — `Tileset3DUploadButton` + entry points

**Files:**
- Create: `shell/src/shell/Tileset3DUploadButton.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/routes.tsx` (`useOpenItem` — route a `tileset3d` item to its detail page instead of falling into the `/apps/{pk}/edit` default)
- Test: `shell/src/shell/Tileset3DUploadButton.test.tsx`

**Interfaces:**
- Consumes: `client.createTileset3DUpload`/`presignTileset3DUploadPart`/`completeTileset3DUpload`/`getTileset3DUploadJob` (Task 9); `instanceQuery.data?.tileset3dEnabled` (Task 4/8).
- Produces: a header button (visible only when `tileset3dEnabled`) opening a dialog: file (zip) + title inputs → chunked multipart upload with a progress indicator → poll until `done`/`error` → close dialog (no navigation — a hosted tileset has no dedicated editor, unlike `ImportFileButton`'s map). `useOpenItem` no longer mis-routes a `tileset3d` item into `/apps/{pk}/edit`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/shell/Tileset3DUploadButton.test.tsx` (mirrors `shell/src/shell/ImportFileButton.test.tsx`):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { Tileset3DUploadButton } from "./Tileset3DUploadButton";

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function zipFile() {
  return new File(["PK\x03\x04fake-zip-content"], "city.zip", { type: "application/zip" });
}

test("uploads a small (single-part) tileset and closes on success", async () => {
  let completedParts: unknown;
  server.use(
    http.post("https://core.test/tileset3d/uploads", () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" })),
    http.put("https://minio.test/part-1", () =>
      new HttpResponse(null, { status: 200, headers: { ETag: "\"etag-1\"" } })),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", async ({ request }) => {
      completedParts = await request.json();
      return new HttpResponse(null, { status: 204 });
    }),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "item-1" })),
  );

  render(<Harness><Tileset3DUploadButton /></Harness>);
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  await waitFor(() => expect(screen.queryByText("Nouveau tileset 3D", { selector: "h2" })).not.toBeInTheDocument());
  expect(completedParts).toEqual({ parts: [{ partNumber: 1, etag: "\"etag-1\"" }] });
});

test("surfaces a job error instead of closing", async () => {
  server.use(
    http.post("https://core.test/tileset3d/uploads", () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.post("https://core.test/tileset3d/uploads/job-1/parts/1/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/part-1" })),
    http.put("https://minio.test/part-1", () =>
      new HttpResponse(null, { status: 200, headers: { ETag: "\"etag-1\"" } })),
    http.post("https://core.test/tileset3d/uploads/job-1/complete", () => new HttpResponse(null, { status: 204 })),
    http.get("https://core.test/tileset3d/uploads/job-1", () =>
      HttpResponse.json({ status: "error", errorMessage: "aucun tileset.json à la racine de l'archive", itemId: null })),
  );

  render(<Harness><Tileset3DUploadButton /></Harness>);
  await userEvent.click(screen.getByText("Nouveau tileset 3D"));
  await userEvent.upload(screen.getByLabelText("Archive du tileset (.zip)"), zipFile());
  await userEvent.type(screen.getByLabelText("Titre"), "Ville");
  await userEvent.click(screen.getByText("Importer"));

  expect(await screen.findByRole("alert")).toHaveTextContent("aucun tileset.json à la racine de l'archive");
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx`
Expected: FAIL — module doesn't exist.

- [ ] **Step 3: Implement the component**

Create `shell/src/shell/Tileset3DUploadButton.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

// S3 multipart accepts a single part of any size — the same chunking code
// path serves a tiny test fixture and a multi-GB tileset (design §4,
// Global Constraints). 100 MB keeps individual PUTs reasonable over a
// typical connection without adding meaningful per-part overhead.
const PART_SIZE_BYTES = 100 * 1024 * 1024;

type Phase = "form" | "uploading" | "finalizing" | "error";

export function Tileset3DUploadButton() {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const [progress, setProgress] = useState<{ done: number; total: number } | null>(null);
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
    setProgress(null);
  }

  async function poll(jobId: string) {
    for (;;) {
      const job = await client.getTileset3DUploadJob(jobId);
      if (job.status === "done") {
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la validation du tileset.");
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      const { jobId } = await client.createTileset3DUpload({ filename: file.name, title: title.trim() });
      const partCount = Math.max(1, Math.ceil(file.size / PART_SIZE_BYTES));
      setProgress({ done: 0, total: partCount });
      const parts: { partNumber: number; etag: string }[] = [];
      for (let i = 0; i < partCount; i++) {
        const partNumber = i + 1;
        const chunk = file.slice(i * PART_SIZE_BYTES, (i + 1) * PART_SIZE_BYTES);
        const { uploadUrl } = await client.presignTileset3DUploadPart(jobId, partNumber);
        const res = await fetch(uploadUrl, { method: "PUT", body: chunk });
        if (!res.ok) throw new Error(`Échec de l'envoi de la partie ${partNumber}.`);
        const etag = res.headers.get("ETag") ?? "";
        parts.push({ partNumber, etag });
        setProgress({ done: partNumber, total: partCount });
      }
      setPhase("finalizing");
      await client.completeTileset3DUpload(jobId, parts);
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du tileset.");
    }
  }

  const busy = phase === "uploading" || phase === "finalizing";

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Nouveau tileset 3D
      </Button>
      <Dialog open={open} onClose={close} title="Nouveau tileset 3D">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Archive du tileset (.zip)
            <input
              aria-label="Archive du tileset (.zip)"
              type="file"
              accept=".zip"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {progress && (
            <p className="text-sm text-slate-500">
              Envoi de la partie {progress.done}/{progress.total}…
            </p>
          )}
          {phase === "finalizing" && (
            <p className="text-sm text-slate-500">Validation du tileset…</p>
          )}
          {phase === "error" && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={busy || !file || !title.trim()}>
              {busy ? "Envoi…" : "Importer"}
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/Tileset3DUploadButton.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Wire the button into `AppLayout` behind the capability flag**

In `shell/src/shell/AppLayout.tsx`, add the import:

```tsx
import { Tileset3DUploadButton } from "./Tileset3DUploadButton";
```

Add `tileset3dEnabled` next to the existing `readOnly` derivation:

```tsx
  const tileset3dEnabled = instanceQuery.data?.tileset3dEnabled === true;
```

Render the button next to `ImportFileButton`, gated:

```tsx
          <NewItemButton />
          <ImportFileButton />
          {tileset3dEnabled && <Tileset3DUploadButton />}
          <span>{username}</span>
```

- [ ] **Step 6: Fix `useOpenItem` for `tileset3d` items**

In `shell/src/shell/routes.tsx`, add a branch to `useOpenItem`'s `onOpenItem` (before the final catch-all `navigate(type === "map" ? ... )` line) — a hosted tileset has no dedicated editor (`ItemDetailPage` already only shows "Ouvrir dans l'éditeur" for `["map","app","dashboard","dataset","pipeline"]`, so this just needs to land somewhere sane rather than the wrong default):

```ts
    if (type === "tileset3d") {
      navigate(`/items/${pk}`);
      return;
    }
```

- [ ] **Step 7: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: both PASS.

- [ ] **Step 8: Commit**

```bash
cd shell && git add src/shell/Tileset3DUploadButton.tsx src/shell/Tileset3DUploadButton.test.tsx src/shell/AppLayout.tsx src/shell/routes.tsx
git commit -m "feat(shell): tileset3d upload button, gated by tileset3dEnabled"
```

---

### Task 13: E2E — upload, add to map, tiles load

**Files:**
- Create: `shell/e2e/tileset3d.spec.ts`

**Interfaces:**
- Consumes: `shell/e2e/mocks.ts::mockCore` (existing helper — every shell E2E spec runs against `VITE_AUTH_MODE=mock` with the core API fully intercepted via Playwright `page.route(...)`, never a real core/MinIO stack; `shell/e2e/ingestion.spec.ts` is the exact template for this spec's shape — a route-mocked multi-step upload flow ending in a job-status poll).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/tileset3d.spec.ts`, modeled directly on `shell/e2e/ingestion.spec.ts`'s `mockIngestionFlow`/test pair, and on `shell/e2e/map-editor.spec.ts`'s "create a Map" flow (`Nouveau` → dialog → `Type=map` → `Titre` → `Créer`) for getting into a blank map editor:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockTileset3DUploadFlow(page: Page) {
  let jobPolls = 0;
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, tileset3dEnabled: true } });
  });
  await page.route("**/tileset3d/uploads/job-1/parts/1/presign", async (route) => {
    await route.fulfill({ json: { uploadUrl: "https://minio.test/tileset3d-part-1" } });
  });
  await page.route("https://minio.test/tileset3d-part-1", async (route) => {
    await route.fulfill({ status: 200, headers: { ETag: "\"etag-1\"" }, body: "" });
  });
  await page.route("**/tileset3d/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" } });
  });
  await page.route("**/tileset3d/uploads/job-1/complete", async (route) => {
    await route.fulfill({ status: 204, body: "" });
  });
  await page.route("**/tileset3d/uploads/job-1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({ json: { status: "finalizing", errorMessage: null, itemId: null } });
    } else {
      await route.fulfill({ json: { status: "done", errorMessage: null, itemId: "t1" } });
    }
  });
  await page.route("https://core.test/items?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "tileset3d") return route.fallback();
    await route.fulfill({
      json: {
        items: [{
          pk: "t1", resourceType: "tileset3d", title: "Ville de test E2E", abstract: "",
          owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false,
        }],
        total: 1, page: 1, pageSize: 200,
      },
    });
  });
  await page.route("https://core.test/tileset3d/t1/tileset.json", async (route) => {
    await route.fulfill({
      json: {
        asset: { version: "1.0" }, geometricError: 500,
        root: { boundingVolume: { region: [0, 0, 0, 0, 0, 0] }, geometricError: 500, refine: "ADD", children: [] },
      },
    });
  });
}

test("upload a tileset, add it to a map via LayerPicker, the proxy request succeeds", async ({ page }) => {
  await mockCore(page);
  await mockTileset3DUploadFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau tileset 3D" }).click();
  await page.getByLabel("Archive du tileset (.zip)").setInputFiles({
    name: "city.zip", mimeType: "application/zip", buffer: Buffer.from("PK\x03\x04fake"),
  });
  await page.getByLabel("Titre").fill("Ville de test E2E");
  await page.getByRole("button", { name: "Importer" }).click();
  await expect(page.getByRole("dialog", { name: "Nouveau tileset 3D" })).toHaveCount(0, { timeout: 10_000 });

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("map");
  await dialog.getByLabel("Titre").fill("Carte avec tileset hébergé");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByRole("searchbox", { name: "Rechercher une source de couche" }).fill("Ville de test E2E");
  const tilesetRequest = page.waitForResponse("https://core.test/tileset3d/t1/tileset.json");
  await page.getByRole("button", { name: /Ville de test E2E/ }).click();
  const response = await tilesetRequest;
  expect(response.status()).toBe(200);
});
```

Note: per `mockIngestionFlow`'s established convention, the `/items?type=xxx&pk` create-map route (`https://core.test/items/77` or similar returned by the `Créer` button) is already covered generically by `mockCore`'s default map-creation handling — confirm this by running the existing `map-editor.spec.ts` "create a Map" test first if unsure; do not duplicate that route mock here.

- [ ] **Step 2: Run the spec**

Run: `cd shell && npx playwright test e2e/tileset3d.spec.ts`
Expected: PASS.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: all specs pass, including every pre-existing one (no regression — this task adds a new spec file and touches no shared code).

- [ ] **Step 4: Commit**

```bash
cd shell && git add e2e/tileset3d.spec.ts
git commit -m "test(e2e): upload a 3D tileset and add it to a map via LayerPicker"
```

---

## Post-plan: update `CLAUDE.md`

Once all 13 tasks are merged and verified, add a `### Fait` entry documenting this increment (non-numbered, "reste de la vision post-v0.1" — same convention as the "3D (rendu)" entry it follows), and remove "hébergement de tilesets 3D Tiles uploadés (zip→S3→item)" from the "reste non planifié" bullet, leaving the three still-open items (TiTiler terrain, `mapbox` encoding, conversion). This is a documentation step, not a plan task — follow the `finishing-a-development-branch` skill for the actual merge/branch decision.
