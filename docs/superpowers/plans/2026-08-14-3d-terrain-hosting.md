# Terrain hébergé — DEM converti et servi par TiTiler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let an author upload a raw DEM GeoTIFF, have GeoStudio convert it server-side to a Cloud-Optimized GeoTIFF (COG), store it, expose it as a searchable/shareable catalogue item, and let a map author pick it from `TerrainPanel` — instead of typing an external terrain-RGB URL — to drive MapLibre's 3D terrain from our own TiTiler instance.

**Architecture:** A core module (`app.terrain3d`) provides a single presigned-PUT upload route (browser uploads directly to S3, core never sees the bytes — arbitrage A6), a procrastinate conversion task that downloads the raw upload to worker scratch disk, runs `rio_cogeo.cog_translate` to produce a COG, validates it, uploads the COG back to S3, and creates the resulting item (`resource_type="terrain3d"`) + `BuilderConfig` (`kind="terrain3d"`) — and an authenticated proxy route (`GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png`) that resolves the item's own stored COG key and forwards the request to TiTiler's built-in `algorithm=terrarium` tile endpoint, streaming the PNG back through the same `can()` door as every other item. The shell's `MapView` attaches the session's bearer token to hosted terrain tile requests via a new `transformRequest` on the MapLibre `Map` instance (generalizing the existing origin-check helper built for hosted 3D Tiles), and `TerrainPanel` offers hosted DEMs alongside the existing external-URL field.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Alembic, boto3, httpx, rasterio, rio-cogeo, procrastinate (core); React, TypeScript, MapLibre GL JS, Vitest, Testing Library, MSW, Playwright (shell).

**Spec:** `docs/superpowers/specs/2026-08-14-3d-terrain-hosting-design.md`

## Global Constraints

- **`sourceKey` in `Terrain3DPayload` is always the converted COG's S3 key, never the raw upload's key.** The raw upload is deleted from S3 once conversion succeeds (mirrors tileset3d's "purge whatever isn't referenced by anything" discipline) or once it's rejected.
- **No `kind="terrain3d"` payload from the client, ever.** Copy the exact `app/configs/tileset3d_validation.py` pattern (`core/app/configs/terrain3d_validation.py`, unconditional 422) and wire it into the same 3 call sites in `core/app/configs/routes.py` from Task 2 — this is the tileset3d I1 lesson baked in from the start, not found in a later review.
- **`tenant_id` + `audit_log`** on `terrain3d_jobs` and on every write (job create, item create, raw-upload purge on rejection) — non-negotiable per `CLAUDE.md`.
- **`CORE_TERRAIN3D_ENABLED`** (default `false`) gates the `app.terrain3d` router mount (upload routes AND the tile-serving proxy — both live on the same router). `BuilderConfig.kind="terrain3d"` itself is **not** gated (mirrors `tileset3d`/`pipeline`/etc.).
- **Wired into `docker-compose.yml`/`.env.example` for BOTH `core` and `worker` in Task 4/Task 5, not left for a final-review fix.** This exact class of bug (a capability flag or its dependent env var missing from one of the two services) has recurred 3 times on this repo (SP-17a, SP-17b, tileset3d-hosting) — CLAUDE.md flags it explicitly. Every task that adds an env var updates both files in the same commit as the code that reads it.
- **No `download_object`-style full-memory reads for the raw upload or the converted COG.** Both can be hundreds of MB; Task 3's S3 helpers stream to/from local scratch files (`/scratch`, the same procrastinate-worker volume `qgis-worker`/pipelines already use), never load a whole raster into process memory.
- **Elevation data requires a lossless COG compression profile.** `rio_cogeo.cog_profiles.get("deflate")` — never `"webp"`/`"jpeg"` (lossy compression would corrupt elevation values, unlike ordinary imagery where it's an acceptable tradeoff).
- **Scratch files are always cleaned up**, including on every failure path (conversion error, S3 upload error, unexpected exception) — `try/finally`, same invariant as `qgis-worker`/pipelines scratch handling.
- **`MapTerrainConfig` (shell) is unchanged.** It already carries `{ tilesUrl, encoding: "terrarium", exaggeration? }` — a hosted DEM just produces a `tilesUrl` of the form `${coreUrl}/terrain3d/{itemId}/tiles/{z}/{x}/{y}.png`. No schema change, fully backward-compatible with existing external terrain URLs.
- **Bearer-token attachment reuses one generalized origin-check helper**, not a copy-pasted one. `isHostedTilesetUrl` becomes `isHostedCoreUrl(url, coreUrl, pathPrefix)`; both the tileset3d and terrain3d call sites use it. A bare substring match on the URL is never acceptable — it's the exact bug fixed in tileset3d hosting Task 11 (a forged external URL like `https://attacker.example/x/terrain3d/y/tiles/0/0/0.png` must never receive the token).
- **No new dependency on `dlt`/harvest egress guards.** The only outbound HTTP call this feature makes is core → TiTiler, over the internal docker network (`http://titiler:8000`), never a user-supplied URL — no SSRF surface, no egress allowlist needed.
- French in user-facing shell strings (labels, buttons, error messages) and commit messages; English in code identifiers — matches existing repo convention.
- TDD per task: write the failing test(s), confirm RED, implement, confirm GREEN, commit.
- **Never skip the OpenAPI/TS regeneration step (Task 7)** — CLAUDE.md flags this exact oversight as recurring across multiple past SPs; it breaks `api-types-drift` in CI silently if forgotten.
- Real-world conversion cost (CPU/memory/time for a large real-world DEM) and proxy-route performance under many simultaneous tile requests are manual acceptance checks, not CI assertions (not reliably measurable in headless CI).

---

### Task 1: Core model, migration, repository — `terrain3d_jobs`

**Files:**
- Create: `core/app/terrain3d/__init__.py` (empty)
- Create: `core/app/terrain3d/models.py`
- Create: `core/app/terrain3d/repository.py`
- Create: `core/alembic/versions/0026_terrain3d_jobs.py`
- Test: `core/tests/test_terrain3d_repository.py`

**Interfaces:**
- Produces: `Terrain3DJob` (SQLAlchemy model, table `terrain3d_jobs`, columns `id, tenant_id, created_by, status, source_key, converted_key, filename, title, error_message, item_id, created_at, updated_at`); `repository.create_job(session, *, tenant_id, created_by, source_key, filename, title) -> Terrain3DJob`; `repository.get_job(session, *, tenant_id, job_id) -> Terrain3DJob | None`; `repository.mark_converting(session, *, job_id) -> None`; `repository.mark_done(session, *, job_id, item_id, converted_key) -> None`; `repository.mark_error(session, *, job_id, error_message) -> None`. Status values: `"uploaded" | "converting" | "done" | "error"`. Consumed by Task 4 (routes) and Task 5 (conversion task).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_terrain3d_repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest

from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import repository as repo
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


def test_create_job_defaults_to_uploaded(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key=f"{tenant.id}/x/dem.tif", filename="dem.tif", title="Relief du massif",
        )
        s.commit()
        assert job.status == "uploaded"
        assert job.item_id is None
        assert job.converted_key is None
        assert job.error_message is None


def test_get_job_scopes_by_tenant(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key="k", filename="dem.tif", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id) is not None
        assert repo.get_job(s, tenant_id="other-tenant", job_id=job_id) is None


def test_mark_converting_then_done_transitions_status_and_sets_item_id(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key="k", filename="dem.tif", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_converting(s, job_id=job_id)
        s.commit()
        assert repo.get_job(s, tenant_id=tenant.id, job_id=job_id).status == "converting"
    with Session() as s:
        repo.mark_done(s, job_id=job_id, item_id="item-42", converted_key="k/cog.tif")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id == "item-42"
        assert job.converted_key == "k/cog.tif"


def test_mark_error_sets_status_and_message(env):
    Session, tenant, alice = env
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key="k", filename="dem.tif", title="T",
        )
        s.commit()
        job_id = job.id
    with Session() as s:
        repo.mark_error(s, job_id=job_id, error_message="GeoTIFF illisible")
        s.commit()
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.error_message == "GeoTIFF illisible"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.terrain3d'`.

- [ ] **Step 3: Implement the model, repository, and migration**

Create `core/app/terrain3d/__init__.py` (empty file).

Create `core/app/terrain3d/models.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Terrain3DJob(Base):
    __tablename__ = "terrain3d_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(ForeignKey("tenants.id"), nullable=False)
    created_by: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False, default="uploaded")
    # "uploaded" | "converting" | "done" | "error"
    source_key: Mapped[str] = mapped_column(String, nullable=False)  # raw upload, purged after conversion
    converted_key: Mapped[str | None] = mapped_column(String, nullable=True)  # set once the COG is uploaded
    filename: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String, nullable=False)
    error_message: Mapped[str | None] = mapped_column(String, nullable=True)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)
```

Create `core/app/terrain3d/repository.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.terrain3d.models import Terrain3DJob


def create_job(
    session: Session, *, tenant_id: str, created_by: str, source_key: str, filename: str, title: str,
) -> Terrain3DJob:
    job = Terrain3DJob(
        id=uuid.uuid4().hex, tenant_id=tenant_id, created_by=created_by,
        status="uploaded", source_key=source_key, filename=filename, title=title,
    )
    session.add(job)
    session.flush()
    session.refresh(job)
    return job


def get_job(session: Session, *, tenant_id: str, job_id: str) -> Terrain3DJob | None:
    return session.scalar(
        select(Terrain3DJob).where(Terrain3DJob.id == job_id, Terrain3DJob.tenant_id == tenant_id)
    )


# mark_converting/mark_done/mark_error sont appelées depuis une route déjà
# tenant-scopée (get_job en amont) ou depuis le worker (qui a déjà validé le
# job via get_job(tenant_id=...) en tout début de tâche) — pas de
# re-filtrage par tenant ici, même discipline qu'app.tileset3d.repository.
def mark_converting(session: Session, *, job_id: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "converting"
    session.flush()


def mark_done(session: Session, *, job_id: str, item_id: str, converted_key: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "done"
    job.item_id = item_id
    job.converted_key = converted_key
    session.flush()


def mark_error(session: Session, *, job_id: str, error_message: str) -> None:
    job = session.get(Terrain3DJob, job_id)
    if job is None:
        return
    job.status = "error"
    job.error_message = error_message
    session.flush()
```

Create `core/alembic/versions/0026_terrain3d_jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""app.terrain3d — terrain3d_jobs

Revision ID: 0026
Revises: 0025
Create Date: 2026-08-14
"""
import sqlalchemy as sa
from alembic import op

revision = "0026"
down_revision = "0025"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "terrain3d_jobs",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("tenant_id", sa.String(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("created_by", sa.String(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(), nullable=False, server_default="uploaded"),
        sa.Column("source_key", sa.String(), nullable=False),
        sa.Column("converted_key", sa.String(), nullable=True),
        sa.Column("filename", sa.String(), nullable=False),
        sa.Column("title", sa.String(), nullable=False),
        sa.Column("error_message", sa.String(), nullable=True),
        sa.Column("item_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index("ix_terrain3d_jobs_tenant_id", "terrain3d_jobs", ["tenant_id", "id"])


def downgrade() -> None:
    op.drop_index("ix_terrain3d_jobs_tenant_id", table_name="terrain3d_jobs")
    op.drop_table("terrain3d_jobs")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_repository.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
cd core && git add app/terrain3d/__init__.py app/terrain3d/models.py app/terrain3d/repository.py alembic/versions/0026_terrain3d_jobs.py tests/test_terrain3d_repository.py
git commit -m "feat(core): terrain3d_jobs model, repository, and migration"
```

---

### Task 2: Core config schema — `Terrain3DPayload` + `BuilderConfig.kind="terrain3d"` + write-route validator

**Files:**
- Modify: `core/app/configs/schemas.py` (add `Terrain3DPayload`, extend `BuilderConfig`)
- Create: `core/app/configs/terrain3d_validation.py`
- Modify: `core/app/configs/routes.py` (wire the validator into the 3 write call sites)
- Test: `core/tests/test_terrain3d_schema.py`
- Test: `core/tests/test_terrain3d_config_validation.py`

**Interfaces:**
- Consumes: none from Task 1.
- Produces: `Terrain3DPayload(sourceKey: str, originalFilename: str)`; `BuilderConfig.kind` Literal gains `"terrain3d"`; `BuilderConfig.terrain3d: Terrain3DPayload | None = None`; `validate_terrain3d_payload(session, config, *, user) -> None` (raises `HTTPException(422)` unconditionally when `config.kind == "terrain3d"`). Consumed by Task 5 (conversion task builds this payload) and Task 6 (read route reads it back via `configs_repo.get_config_by_item`).

- [ ] **Step 1: Write the failing schema test**

Create `core/tests/test_terrain3d_schema.py` (mirrors `core/tests/test_tileset3d_schema.py` exactly — same `_make_client`/`client`/`client_env` fixture shape, confirmed against that file):

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app import db
from app.auth.dependency import get_current_user
from app.db import make_engine, make_session_factory, init_db, request_scoped_session
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _make_client(*, username: str, oidc_sub: str):
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub=oidc_sub,
            username=username, email=f"{username}@example.com",
            first_name="Alice", last_name="Doe",
        )
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    return TestClient(app), Session, tenant, user


@pytest.fixture()
def client():
    return _make_client(username="alice", oidc_sub="sub-1")[0]


@pytest.fixture()
def client_env():
    return _make_client(username="alice", oidc_sub="sub-1")


def test_terrain3d_config_round_trips(client_env):
    # kind="terrain3d" n'est pas créable via POST /configs (Step 7 de cette
    # tâche + test_terrain3d_config_validation.py) — son unique producteur
    # légitime est convert_terrain3d_task, qui appelle
    # configs_repo.create_config en direct : c'est donc ce chemin qu'on
    # emprunte ici, la lecture restant vérifiée via l'API REST.
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, Terrain3DPayload
    from app.items import repository as items_repo

    client, Session, tenant, user = client_env
    with Session() as s:
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id,
            resource_type="terrain3d", title="Relief du massif",
        )
        configs_repo.create_config(
            s,
            BuilderConfig(
                kind="terrain3d",
                terrain3d=Terrain3DPayload(sourceKey="tenant-1/abc/dem-cog.tif", originalFilename="dem.tif"),
            ),
            item_id=item.id, tenant_id=tenant.id,
        )
        s.commit()
        item_id = item.id

    by_item = client.get(f"/configs/by-item/{item_id}")
    assert by_item.status_code == 200
    body = by_item.json()["config"]
    assert body["kind"] == "terrain3d"
    assert body["terrain3d"] == {"sourceKey": "tenant-1/abc/dem-cog.tif", "originalFilename": "dem.tif"}


def test_terrain3d_config_requires_terrain3d_payload(client):
    created = client.post(
        "/configs",
        json={"title": "Cassé", "config": {"kind": "terrain3d"}},
    )
    assert created.status_code == 422
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_schema.py -v`
Expected: FAIL — `kind` rejects `"terrain3d"` as an invalid Pydantic literal value; `ImportError: cannot import name 'Terrain3DPayload'`.

- [ ] **Step 3: Implement the schema changes**

In `core/app/configs/schemas.py`, add `Terrain3DPayload` right before `class BuilderConfig(BaseModel):`:

```python
class Terrain3DPayload(BaseModel):
    sourceKey: str  # clé S3 du COG converti — jamais celle de l'upload brut
    originalFilename: str
```

Update the `kind` Literal:

```python
    kind: Literal["app", "dashboard", "map", "site", "dataset", "bookmark", "pipeline", "alert", "report", "tileset3d", "terrain3d"]
```

Add the field after `tileset3d`:

```python
    tileset3d: Tileset3DPayload | None = None
    terrain3d: Terrain3DPayload | None = None
    printLayout: PrintLayout | None = None
```

Add the validator branch after the `tileset3d` check:

```python
        if self.kind == "tileset3d" and self.tileset3d is None:
            raise ValueError("tileset3d config requires a tileset3d payload")
        if self.kind == "terrain3d" and self.terrain3d is None:
            raise ValueError("terrain3d config requires a terrain3d payload")
        return self
```

- [ ] **Step 4: Run the schema tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_schema.py -v`
Expected: PASS.

- [ ] **Step 5: Write the failing write-route validation test**

Create `core/tests/test_terrain3d_config_validation.py` (mirrors `core/tests/test_tileset3d_config_validation.py` exactly — same `_session_and_user`/`_client` helper shape, confirmed against that file):

```python
# SPDX-License-Identifier: Apache-2.0
"""Même raisonnement que test_tileset3d_config_validation.py (I1, revue
finale de branche tileset3d hosting) : kind="terrain3d" n'a aucune voie de
création/mise à jour légitime par les routes /configs publiques."""
import pytest
from fastapi import HTTPException

from app.configs.schemas import BuilderConfig
from app.configs.terrain3d_validation import validate_terrain3d_payload
from app.db import init_db, make_engine, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _terrain3d_config(source_key: str = "other-tenant/abc/dem-cog.tif") -> BuilderConfig:
    return BuilderConfig.model_validate({
        "kind": "terrain3d",
        "terrain3d": {"sourceKey": source_key, "originalFilename": "dem.tif"},
    })


def _session_and_user():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    s = Session()
    tenant = get_or_create_default_tenant(s)
    user = get_or_create_user(
        s, tenant_id=tenant.id, oidc_sub="a", username="alice",
        email=None, first_name="", last_name="",
    )
    s.commit()
    return s, user


def test_ignores_non_terrain3d_kind():
    s, user = _session_and_user()
    with s:
        config = BuilderConfig.model_validate({
            "kind": "map",
            "map": {
                "basemap": {"style": "mapbox://styles/mapbox/streets-v12"},
                "view": {"center": [0, 0], "zoom": 1},
            },
        })
        validate_terrain3d_payload(s, config, user=user)  # no raise


def test_rejects_any_terrain3d_payload():
    s, user = _session_and_user()
    with s:
        with pytest.raises(HTTPException) as exc:
            validate_terrain3d_payload(s, _terrain3d_config(), user=user)
        assert exc.value.status_code == 422


def _client(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient

    from app.main import create_app

    db_url = f"sqlite+pysqlite:///{tmp_path / 'terrain3d_config_validation.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="mock-sub", username="mockuser",
            email=None, first_name="Mock", last_name="User",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client


def _body() -> dict:
    return {"title": "DEM volé", "config": _terrain3d_config().model_dump(mode="json")}


def test_post_configs_with_kind_terrain3d_is_rejected(monkeypatch, tmp_path):
    client = _client(monkeypatch, tmp_path)

    resp = client.post("/configs", json=_body())

    assert resp.status_code == 422
    assert resp.json()["detail"] == "terrain3d configs can only be created by the conversion task"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_config_validation.py -v`
Expected: FAIL — `terrain3d` kind currently accepted (only the `Terrain3DPayload` shape is validated, not the "who may create it" rule).

- [ ] **Step 7: Implement the validator and wire it in**

Create `core/app/configs/terrain3d_validation.py` (verbatim structure of `core/app/configs/tileset3d_validation.py`):

```python
# SPDX-License-Identifier: Apache-2.0
"""Validation directe du kind="terrain3d" pour app.configs : ce kind n'a
aucune voie de création/mise à jour légitime via les routes publiques —
seule convert_terrain3d_task (app.terrain3d.jobs) le produit, via un appel
direct à app.configs.repository.create_config qui ne passe jamais par ces
routes REST. Un POST/PUT/PATCH authentifié quelconque avec kind="terrain3d"
serait sinon un moyen de s'approprier un sourceKey S3 arbitraire (item créé
par l'appelant, mais pointant vers les octets d'un autre DEM converti) et de
le lire via le proxy authentifié GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png
— le proxy vérifie can() sur l'item appelant, jamais sur la provenance du
sourceKey qu'il désigne. Même raisonnement que app.configs.tileset3d_validation,
copié verbatim pour ce second kind à source S3 opaque.

`_session`/`user` sont inutilisés (le refus est inconditionnel) mais
conservés : les autres validateurs de ce paquet partagent la même signature
et les trois points d'appel de app.configs.routes les invoquent uniformément.
"""
from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.users.models import User


def validate_terrain3d_payload(_session: Session, config: BuilderConfig, *, user: User) -> None:  # noqa: ARG001
    if config.kind != "terrain3d":
        return
    raise HTTPException(
        status_code=422,
        detail="terrain3d configs can only be created by the conversion task",
    )
```

In `core/app/configs/routes.py`, add the import right after the tileset3d one:

```python
from app.configs.terrain3d_validation import validate_terrain3d_payload as _validate_terrain3d_payload
from app.configs.tileset3d_validation import validate_tileset3d_payload as _validate_tileset3d_payload
```

Add a call right after each of the 3 existing `_validate_tileset3d_payload(session, ..., user=user)` call sites (lines ~102, ~159, ~265 before this edit):

```python
    _validate_tileset3d_payload(session, request.config, user=user)
    _validate_terrain3d_payload(session, request.config, user=user)
```

(and the corresponding two sites using `config` instead of `request.config` — match each site's existing local variable name exactly, same as the tileset3d call it sits next to.)

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_config_validation.py tests/test_terrain3d_schema.py -v`
Expected: PASS.

- [ ] **Step 9: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: all previously-passing tests still pass (a `Literal` extension, an additive optional field, and an additive validator call are backward-compatible).

- [ ] **Step 10: Commit**

```bash
cd core && git add app/configs/schemas.py app/configs/terrain3d_validation.py app/configs/routes.py tests/test_terrain3d_schema.py tests/test_terrain3d_config_validation.py
git commit -m "feat(core): Terrain3DPayload, BuilderConfig kind=terrain3d, write-route validator"
```

---

### Task 3: Core S3 scratch streaming + COG conversion

**Files:**
- Create: `core/app/terrain3d/storage.py`
- Create: `core/app/terrain3d/conversion.py`
- Modify: `core/pyproject.toml` (add `rasterio`, `rio-cogeo`)
- Test: `core/tests/test_terrain3d_storage.py`
- Test: `core/tests/test_terrain3d_conversion.py`

**Interfaces:**
- Consumes: none.
- Produces: `storage.download_to_file(client, *, bucket: str, key: str, dest_path: str) -> None`; `storage.upload_file(client, *, bucket: str, key: str, src_path: str) -> None`; `conversion.Terrain3DConversionError(ValueError)`; `conversion.convert_to_cog(src_path: str, dest_path: str, *, timeout_seconds: int | None = None) -> None` (raises `Terrain3DConversionError` on any unreadable/invalid input, a timeout, or failed COG validation). Consumed by Task 5 (conversion task).

- [ ] **Step 1: Write the failing storage test**

Create `core/tests/test_terrain3d_storage.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import io
import os

from app.terrain3d.storage import download_to_file, upload_file


class _FakeBody:
    def __init__(self, data: bytes):
        self._buf = io.BytesIO(data)

    def iter_chunks(self, chunk_size: int):
        while True:
            chunk = self._buf.read(chunk_size)
            if not chunk:
                return
            yield chunk


class _FakeS3Client:
    def __init__(self):
        self.objects: dict[str, bytes] = {}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": _FakeBody(self.objects[Key])}

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        with open(Filename, "rb") as f:
            self.objects[Key] = f.read()


def test_download_to_file_streams_object_to_local_path(tmp_path):
    client = _FakeS3Client()
    client.objects["k"] = b"0123456789" * 1000
    dest = tmp_path / "raw.tif"
    download_to_file(client, bucket="b", key="k", dest_path=str(dest))
    assert dest.read_bytes() == client.objects["k"]


def test_upload_file_puts_local_path_to_object(tmp_path):
    client = _FakeS3Client()
    src = tmp_path / "cog.tif"
    src.write_bytes(b"fake cog bytes")
    upload_file(client, bucket="b", key="k", src_path=str(src))
    assert client.objects["k"] == b"fake cog bytes"


def test_download_to_file_never_loads_whole_object_in_one_read(tmp_path, monkeypatch):
    # Régression : garantit que download_to_file lit par tranches (iter_chunks),
    # pas via Body.read() sans argument (le piège de app.ingestion.storage.download_object,
    # inadapté à un DEM de plusieurs centaines de Mo — cf. Global Constraints).
    client = _FakeS3Client()
    client.objects["k"] = b"x" * (5 * 1024 * 1024)
    dest = tmp_path / "raw.tif"
    seen_chunk_sizes = []
    original_iter_chunks = _FakeBody.iter_chunks

    def spy_iter_chunks(self, chunk_size):
        seen_chunk_sizes.append(chunk_size)
        yield from original_iter_chunks(self, chunk_size)

    monkeypatch.setattr(_FakeBody, "iter_chunks", spy_iter_chunks)
    download_to_file(client, bucket="b", key="k", dest_path=str(dest))
    assert seen_chunk_sizes and all(0 < c <= 8 * 1024 * 1024 for c in seen_chunk_sizes)
    assert os.path.getsize(dest) == 5 * 1024 * 1024
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_storage.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.terrain3d.storage'`.

- [ ] **Step 3: Implement `storage.py`**

Create `core/app/terrain3d/storage.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Lecture/écriture S3 en flux vers/depuis un fichier scratch local — jamais
une charge complète en mémoire (design §3 : un DEM peut faire plusieurs
centaines de Mo, contrairement aux petits objets que
app.ingestion.storage.download_object charge entièrement). rio_cogeo a de
toute façon besoin d'un chemin de fichier local (GDAL), pas d'un flux."""
_CHUNK_BYTES = 8 * 1024 * 1024  # 8 MiB


def download_to_file(client, *, bucket: str, key: str, dest_path: str) -> None:
    obj = client.get_object(Bucket=bucket, Key=key)
    with open(dest_path, "wb") as f:
        for chunk in obj["Body"].iter_chunks(_CHUNK_BYTES):
            f.write(chunk)


def upload_file(client, *, bucket: str, key: str, src_path: str) -> None:
    client.upload_file(Filename=src_path, Bucket=bucket, Key=key)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_storage.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Add rasterio/rio-cogeo dependencies**

In `core/pyproject.toml`, add after the `pyproj` line:

```toml
    "pyproj>=3.6",
    "rasterio>=1.3",  # terrain3d : lecture/écriture GeoTIFF (GDAL embarqué
                      # dans la wheel, pas de dépendance système séparée à
                      # installer) ; wheel comparable en poids à pyogrio,
                      # déjà présent — pas un sidecar comme qgis-worker.
    "rio-cogeo>=5.3",  # terrain3d : cog_translate/cog_validate — conversion
                       # d'un GeoTIFF brut en Cloud Optimized GeoTIFF et
                       # validation structurelle du résultat.
```

Run `cd core && uv sync` to update `uv.lock`.

- [ ] **Step 6: Write the failing conversion test**

Create `core/tests/test_terrain3d_conversion.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.terrain3d.conversion import Terrain3DConversionError, convert_to_cog


def _write_test_geotiff(path: str, *, width: int = 64, height: int = 64) -> None:
    data = np.linspace(0, 1000, width * height, dtype="float32").reshape(height, width)
    transform = from_origin(0, 0, 1, 1)
    with rasterio.open(
        path, "w", driver="GTiff", width=width, height=height, count=1,
        dtype="float32", crs="EPSG:4326", transform=transform,
    ) as dst:
        dst.write(data, 1)


def test_convert_to_cog_produces_a_valid_cog(tmp_path):
    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    _write_test_geotiff(str(src))

    convert_to_cog(str(src), str(dst))

    assert dst.exists()
    with rasterio.open(str(dst)) as ds:
        assert ds.driver == "GTiff"
        assert ds.overviews(1) != []  # COG requires overviews
        assert ds.profile.get("tiled") is True


def test_convert_to_cog_rejects_a_non_raster_file(tmp_path):
    src = tmp_path / "raw.tif"
    src.write_bytes(b"not a geotiff at all")
    dst = tmp_path / "cog.tif"
    with pytest.raises(Terrain3DConversionError, match="lisible"):
        convert_to_cog(str(src), str(dst))


def test_convert_to_cog_rejects_a_raster_without_a_crs(tmp_path):
    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    data = np.zeros((8, 8), dtype="float32")
    with rasterio.open(
        src, "w", driver="GTiff", width=8, height=8, count=1, dtype="float32",
    ) as ds:  # no crs=, no transform=
        ds.write(data, 1)
    with pytest.raises(Terrain3DConversionError, match="CRS"):
        convert_to_cog(str(src), str(dst))


def test_convert_to_cog_raises_on_timeout(tmp_path, monkeypatch):
    import time

    from app.terrain3d import conversion

    src = tmp_path / "raw.tif"
    dst = tmp_path / "cog.tif"
    _write_test_geotiff(str(src))

    def _slow_cog_translate(*args, **kwargs):
        time.sleep(2)

    monkeypatch.setattr(conversion, "cog_translate", _slow_cog_translate)
    with pytest.raises(Terrain3DConversionError, match="interrompue"):
        convert_to_cog(str(src), str(dst), timeout_seconds=1)
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_conversion.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.terrain3d.conversion'`.

- [ ] **Step 8: Implement `conversion.py`**

Create `core/app/terrain3d/conversion.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Conversion d'un GeoTIFF brut en Cloud Optimized GeoTIFF, requise pour que
TiTiler serve des tuiles à coût constant (design §3). Le profil "deflate"
est sans perte : un profil "webp"/"jpeg" (courant pour de l'imagerie
classique) corromprait les valeurs d'élévation, contrairement à une image
RGB où une perte de qualité visuelle est acceptable — cf. Global
Constraints.

`timeout_seconds` borne uniquement l'appel GDAL potentiellement long
(cog_translate) via signal.alarm — un worker procrastinate exécute ses
tâches de façon synchrone dans le thread principal du process, donc
SIGALRM est sûr ici (Linux uniquement, comme tout ce conteneur)."""
import signal

import rasterio
from rasterio.errors import RasterioIOError
from rio_cogeo.cogeo import cog_translate, cog_validate
from rio_cogeo.profiles import cog_profiles


class Terrain3DConversionError(ValueError):
    pass


class _ConversionTimeout(Exception):
    pass


def _raise_timeout(signum, frame):  # noqa: ARG001
    raise _ConversionTimeout()


def convert_to_cog(src_path: str, dest_path: str, *, timeout_seconds: int | None = None) -> None:
    try:
        with rasterio.open(src_path) as src:
            if src.crs is None:
                raise Terrain3DConversionError("le raster n'a pas de CRS défini")
    except RasterioIOError as exc:
        raise Terrain3DConversionError(f"fichier non lisible comme raster : {exc}") from exc

    profile = cog_profiles.get("deflate")
    previous_handler = None
    if timeout_seconds is not None:
        previous_handler = signal.signal(signal.SIGALRM, _raise_timeout)
        signal.alarm(timeout_seconds)
    try:
        cog_translate(
            src_path, dest_path, profile,
            in_memory=False, quiet=True,
            config={"GDAL_NUM_THREADS": "ALL_CPUS", "GDAL_TIFF_INTERNAL_MASK": True},
        )
    except _ConversionTimeout as exc:
        raise Terrain3DConversionError(f"conversion COG interrompue après {timeout_seconds}s") from exc
    except Exception as exc:  # rio_cogeo/GDAL peuvent lever divers types selon la cause
        raise Terrain3DConversionError(f"échec de la conversion COG : {exc}") from exc
    finally:
        if timeout_seconds is not None:
            signal.alarm(0)
            signal.signal(signal.SIGALRM, previous_handler)

    is_valid, errors, _warnings = cog_validate(dest_path, strict=True)
    if not is_valid:
        raise Terrain3DConversionError(f"COG produit invalide : {'; '.join(errors)}")
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_conversion.py -v`
Expected: PASS (4 tests).

- [ ] **Step 10: Commit**

```bash
cd core && git add app/terrain3d/storage.py app/terrain3d/conversion.py pyproject.toml uv.lock tests/test_terrain3d_storage.py tests/test_terrain3d_conversion.py
git commit -m "feat(core): terrain3d S3 scratch streaming and COG conversion"
```

---

### Task 4: Core upload routes + capability flag + app wiring + compose (core service)

**Files:**
- Create: `core/app/terrain3d/schemas.py`
- Create: `core/app/terrain3d/routes.py` (upload endpoints only — the tile-serving proxy is added in Task 6)
- Modify: `core/app/auth/dependency.py` (add `is_terrain3d_enabled`)
- Modify: `core/app/main.py` (mount router behind flag, S3 client/bucket overrides)
- Modify: `core/app/jobs.py` (register `app.terrain3d.jobs` import path — module created in Task 5, safe to list now)
- Modify: `core/app/instance/routes.py` (expose `terrain3dEnabled`)
- Modify: `core/pyproject.toml` (import-linter layers)
- Modify: `docker-compose.yml` (`core` service: `CORE_TERRAIN3D_ENABLED`, `S3_TERRAIN3D_BUCKET`, `TITILER_URL`)
- Modify: `.env.example` (same 3 vars, documented)
- Test: `core/tests/test_terrain3d_enabled_flag.py`
- Test: `core/tests/test_terrain3d_routes.py`

**Interfaces:**
- Consumes: `repository.create_job`/`get_job`/`mark_converting` (Task 1); reuses `app.ingestion.storage.ensure_uploads_bucket`/`generate_presigned_put_url` and `app.ingestion.routes.get_s3_client` verbatim (same reuse pattern as `app.tileset3d`).
- Produces: `POST /terrain3d/uploads/presign` → `{uploadUrl, key}`; `POST /terrain3d/uploads` → `{jobId}`; `GET /terrain3d/uploads/{job_id}` → `{status, errorMessage, itemId}`; `is_terrain3d_enabled() -> bool`; `InstanceInfo` gains `terrain3dEnabled`. `routes.get_task_deferrer` defers a task named `convert_terrain3d_task` (implemented Task 5 — deferring an as-yet-unimplemented but already-registered task name is safe with procrastinate, and this task's tests override the deferrer so the real task is never invoked).

- [ ] **Step 1: Write the failing capability-flag test**

Create `core/tests/test_terrain3d_enabled_flag.py` (mirrors `test_tileset3d_enabled_flag.py`):

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional, is_terrain3d_enabled
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def test_is_terrain3d_enabled_defaults_to_false(monkeypatch):
    monkeypatch.delenv("CORE_TERRAIN3D_ENABLED", raising=False)
    assert is_terrain3d_enabled() is False


def test_is_terrain3d_enabled_reads_env_var(monkeypatch):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    assert is_terrain3d_enabled() is True
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "false")
    assert is_terrain3d_enabled() is False


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


def test_instance_reports_terrain3d_disabled_by_default(env):
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["terrain3dEnabled"] is False


def test_instance_reports_terrain3d_enabled(env, monkeypatch):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    response = env.get("/instance")
    assert response.status_code == 200
    assert response.json()["terrain3dEnabled"] is True


def test_upload_routes_absent_when_disabled(monkeypatch):
    monkeypatch.delenv("CORE_TERRAIN3D_ENABLED", raising=False)
    app = create_app()
    client = TestClient(app)
    response = client.post("/terrain3d/uploads", json={"key": "x", "filename": "dem.tif", "title": "X"})
    assert response.status_code == 404
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_enabled_flag.py -v`
Expected: FAIL — `ImportError: cannot import name 'is_terrain3d_enabled'`.

- [ ] **Step 3: Add the capability flag**

In `core/app/auth/dependency.py`, add after `is_tileset3d_enabled`:

```python
def is_terrain3d_enabled() -> bool:
    """CORE_TERRAIN3D_ENABLED — capacité instance-wide optionnelle, même
    convention que is_tileset3d_enabled : lue à chaque appel, sans cache.
    Défaut false : une instance qui monte en version ne provisionne rien de
    nouveau (bucket S3 dédié, dépendances rasterio/rio-cogeo côté worker,
    route proxy) tant qu'elle n'a pas explicitement activé la capacité
    (design terrain hébergé §6)."""
    return os.environ.get("CORE_TERRAIN3D_ENABLED", "false").lower() == "true"
```

- [ ] **Step 4: Write the failing upload-routes test**

Create `core/tests/test_terrain3d_routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.ingestion import routes as ingestion_routes
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user


class _FakeS3Client:
    def create_bucket(self, Bucket):  # noqa: N803
        pass

    def put_bucket_cors(self, Bucket, CORSConfiguration):  # noqa: N803
        pass

    def generate_presigned_url(self, operation, Params, ExpiresIn):  # noqa: N803
        return f"https://minio.test/{Params['Bucket']}/{Params['Key']}"


@pytest.fixture()
def env(monkeypatch):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
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

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[ingestion_routes.get_s3_client] = lambda: _FakeS3Client()
    deferred: list[tuple[str, str]] = []
    app.dependency_overrides[terrain3d_routes.get_task_deferrer] = (
        lambda: (lambda job_id, tenant_id: deferred.append((job_id, tenant_id)))
    )
    client = TestClient(app)
    return client, Session, tenant, alice, deferred


def test_presign_returns_upload_url_and_tenant_scoped_key(env):
    client, _, tenant, *_ = env
    r = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert "uploadUrl" in body
    assert body["key"].startswith(f"{tenant.id}/")


def test_create_upload_job_defers_conversion_task(env):
    client, _, tenant, _, deferred = env
    presigned = client.post("/terrain3d/uploads/presign", json={"filename": "dem.tif"}).json()
    r = client.post(
        "/terrain3d/uploads",
        json={"key": presigned["key"], "filename": "dem.tif", "title": "Relief du massif"},
    )
    assert r.status_code == 201, r.text
    job_id = r.json()["jobId"]
    assert deferred == [(job_id, tenant.id)]
    status = client.get(f"/terrain3d/uploads/{job_id}").json()
    assert status["status"] == "uploaded"


def test_create_upload_job_rejects_key_outside_caller_tenant(env):
    client, *_ = env
    r = client.post(
        "/terrain3d/uploads",
        json={"key": "some-other-tenant/x/dem.tif", "filename": "dem.tif", "title": "T"},
    )
    assert r.status_code == 400


def test_get_upload_job_404_for_unknown_job(env):
    client, *_ = env
    r = client.get("/terrain3d/uploads/does-not-exist")
    assert r.status_code == 404
```

- [ ] **Step 5: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_enabled_flag.py tests/test_terrain3d_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.terrain3d.routes'`, `/instance` doesn't report `terrain3dEnabled`.

- [ ] **Step 6: Implement schemas, routes, and wiring**

Create `core/app/terrain3d/schemas.py`:

```python
# SPDX-License-Identifier: Apache-2.0
from pydantic import BaseModel, Field


class Terrain3DPresignRequest(BaseModel):
    filename: str = Field(min_length=1, max_length=255)


class Terrain3DPresignResponse(BaseModel):
    uploadUrl: str
    key: str


class Terrain3DUploadCreate(BaseModel):
    key: str = Field(min_length=1)
    filename: str = Field(min_length=1, max_length=255)
    title: str = Field(min_length=1)


class Terrain3DUploadCreated(BaseModel):
    jobId: str


class Terrain3DJobStatus(BaseModel):
    status: str
    errorMessage: str | None
    itemId: str | None
```

Create `core/app/terrain3d/routes.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Routes REST de l'hébergement de terrain DEM — montées uniquement quand
CORE_TERRAIN3D_ENABLED est actif (app.main, même patron que
app.pipelines/app.tileset3d). Le proxy de lecture
(GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png) est ajouté dans ce même
module en Task 6."""
import os
import uuid
from collections.abc import Callable

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.auth.dependency import get_current_user
from app.db import get_session
from app.ingestion.routes import get_s3_client
from app.ingestion.storage import ensure_uploads_bucket, generate_presigned_put_url
from app.terrain3d import repository as repo
from app.terrain3d.schemas import (
    Terrain3DJobStatus, Terrain3DPresignRequest, Terrain3DPresignResponse,
    Terrain3DUploadCreate, Terrain3DUploadCreated,
)
from app.users.models import User

router = APIRouter()


def get_terrain3d_bucket() -> str:
    return os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")


def get_task_deferrer() -> Callable[[str, str], None]:  # overridden in tests
    def deferrer(job_id: str, tenant_id: str) -> None:
        from app.terrain3d.jobs import convert_terrain3d_task

        convert_terrain3d_task.defer(job_id=job_id, tenant_id=tenant_id)
    return deferrer


@router.post("/terrain3d/uploads/presign", response_model=Terrain3DPresignResponse)
def presign_terrain3d_upload(
    body: Terrain3DPresignRequest,
    user: User = Depends(get_current_user),
    s3=Depends(get_s3_client),
    bucket: str = Depends(get_terrain3d_bucket),
) -> Terrain3DPresignResponse:
    ensure_uploads_bucket(s3, bucket)
    key = f"{user.tenant_id}/{uuid.uuid4().hex}/{body.filename}"
    url = generate_presigned_put_url(s3, bucket=bucket, key=key, content_type="application/octet-stream")
    return Terrain3DPresignResponse(uploadUrl=url, key=key)


@router.post("/terrain3d/uploads", response_model=Terrain3DUploadCreated, status_code=201)
def create_terrain3d_upload(
    body: Terrain3DUploadCreate,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    defer_task: Callable[[str, str], None] = Depends(get_task_deferrer),
) -> Terrain3DUploadCreated:
    # Même garde confused-deputy que app.ingestion.routes.create_upload_job :
    # la clé est censée venir du présigné ci-dessus, toujours préfixée par le
    # tenant de l'appelant.
    if not body.key.startswith(f"{user.tenant_id}/"):
        raise HTTPException(status_code=400, detail="invalid upload key")
    job = repo.create_job(
        session, tenant_id=user.tenant_id, created_by=user.id,
        source_key=body.key, filename=body.filename, title=body.title,
    )
    write_audit(
        session, tenant_id=user.tenant_id, actor_id=user.id, actor_kind="user",
        action="terrain3d.job_create", object_type="terrain3d_job", object_id=job.id,
        payload={"filename": body.filename, "title": body.title},
    )
    # Commit avant de déférer : même raison que app.ingestion.routes.create_upload_job.
    session.commit()
    defer_task(job.id, user.tenant_id)
    return Terrain3DUploadCreated(jobId=job.id)


@router.get("/terrain3d/uploads/{job_id}", response_model=Terrain3DJobStatus)
def get_terrain3d_upload_job(
    job_id: str,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
) -> Terrain3DJobStatus:
    job = repo.get_job(session, tenant_id=user.tenant_id, job_id=job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return Terrain3DJobStatus(status=job.status, errorMessage=job.error_message, itemId=job.item_id)
```

In `core/app/main.py`:

Add the import, alphabetically after `from app.tileset3d import routes as tileset3d_routes`:

```python
from app.terrain3d import routes as terrain3d_routes
from app.tileset3d import routes as tileset3d_routes
```

Update the capability-flag import line:

```python
from app.auth.dependency import (
    is_etl_enabled, is_export_enabled, is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)
```

Add the router mount next to the tileset3d one:

```python
    if is_tileset3d_enabled():
        app.include_router(tileset3d_routes.router)
    if is_terrain3d_enabled():
        app.include_router(terrain3d_routes.router)
```

Add the S3 bucket override in the same `if s3_endpoint and s3_access_key and s3_secret_key:` block that already wires `tileset3d_routes`, right after the `s3_tileset3d_bucket` line:

```python
        s3_tileset3d_bucket = os.environ.get("S3_TILESET3D_BUCKET", "geostudio-tileset3d")
        app.dependency_overrides[tileset3d_routes.get_tileset3d_bucket] = lambda: s3_tileset3d_bucket
        s3_terrain3d_bucket = os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
        app.dependency_overrides[terrain3d_routes.get_terrain3d_bucket] = lambda: s3_terrain3d_bucket
```

In `core/app/instance/routes.py`, add the flag:

```python
# SPDX-License-Identifier: Apache-2.0
from fastapi import APIRouter

from app.auth.dependency import (
    is_etl_enabled, is_export_enabled, is_read_only_mode, is_terrain3d_enabled, is_tileset3d_enabled,
)

router = APIRouter()


@router.get("/instance")
def get_instance_info() -> dict:
    return {
        "readOnly": is_read_only_mode(),
        "etlEnabled": is_etl_enabled(),
        "exportEnabled": is_export_enabled(),
        "tileset3dEnabled": is_tileset3d_enabled(),
        "terrain3dEnabled": is_terrain3d_enabled(),
    }
```

In `core/app/jobs.py`, add `"app.terrain3d.jobs"` to `import_paths` (module implemented in Task 5 — listing it now is safe, `perform_import_paths()` only runs when the worker actually starts):

```python
    import_paths=[
        "app.ingestion.tasks", "app.items.jobs", "app.collections.jobs",
        "app.cdc.jobs", "app.harvest.jobs", "app.pipelines.jobs", "app.alerts.jobs",
        "app.export.jobs", "app.reports.jobs", "app.tileset3d.jobs", "app.terrain3d.jobs",
    ],
```

In `core/pyproject.toml`, insert `"app.terrain3d"` into the `layers` list right after `"app.tileset3d"` (same tier: depends on `app.ingestion.storage`/`app.ingestion.routes`, so it must sit above `app.ingestion`):

```toml
    "app.export",
    "app.tileset3d",
    "app.terrain3d",
    "app.secrets",
    "app.ingestion",
```

Add the matching `app.db -> app.terrain3d.models` line to `ignore_imports`, next to the `app.tileset3d` one:

```toml
    "app.db -> app.tileset3d.models",
    "app.db -> app.terrain3d.models",
```

- [ ] **Step 7: Wire the compose stack — `core` service**

In `docker-compose.yml`, in the `core` service's `environment:` block, add right after `CORE_TILESET3D_MAX_PROXY_READ_BYTES`:

```yaml
      CORE_TERRAIN3D_ENABLED: ${CORE_TERRAIN3D_ENABLED:-false}
      S3_TERRAIN3D_BUCKET: geostudio-terrain3d
      # Titiler sert les tuiles terrain-RGB depuis le COG hébergé (proxy
      # read_terrain3d_tile, app/terrain3d/routes.py) — appel interne, jamais
      # exposé au navigateur.
      TITILER_URL: ${TITILER_URL:-http://titiler:8000}
```

(`S3_TERRAIN3D_BUCKET` is already set above, next to `CORE_TERRAIN3D_ENABLED` — don't add it a second time next to `S3_TILESET3D_BUCKET` in the pre-existing bucket list further up the block.)

Add `depends_on: [pgbouncer, minio, titiler]` in place of the `core` service's existing `depends_on: [pgbouncer, minio]` — core now makes runtime calls to `titiler`, not just to the database/object store.

In `.env.example`, add right after the `CORE_TILESET3D_MAX_PROXY_READ_BYTES` line:

```
# Terrain DEM hébergé (upload GeoTIFF brut → conversion COG côté worker →
# proxy de tuiles terrarium via notre TiTiler) — "false" (défaut) ne monte
# pas le routeur app.terrain3d ; le sélecteur de DEM hébergé du shell
# disparaît aussi.
CORE_TERRAIN3D_ENABLED=false
S3_TERRAIN3D_BUCKET=geostudio-terrain3d
# URL interne (réseau docker) du service TiTiler — inchangée dans la
# plupart des déploiements, seule une topologie non standard la fait varier.
#TITILER_URL=http://titiler:8000
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_enabled_flag.py tests/test_terrain3d_routes.py -v`
Expected: PASS (7 tests).

- [ ] **Step 9: Run the full core suite and import-linter to check for regressions**

Run: `cd core && uv run pytest -q && uv run lint-imports`
Expected: all previously-passing tests still pass; import-linter reports `Kept: N+1, Broken: 0` (or the repo's exact phrasing — match whatever the tileset3d Task 4 commit's CI output showed).

- [ ] **Step 10: Commit**

```bash
cd core && git add app/terrain3d/schemas.py app/terrain3d/routes.py app/auth/dependency.py app/main.py app/jobs.py app/instance/routes.py pyproject.toml uv.lock tests/test_terrain3d_enabled_flag.py tests/test_terrain3d_routes.py
git add ../docker-compose.yml ../.env.example
git commit -m "feat(core): terrain3d upload routes, capability flag, compose wiring"
```

---

### Task 5: Conversion task (worker) + compose (worker service)

**Files:**
- Create: `core/app/terrain3d/jobs.py`
- Modify: `docker-compose.yml` (`worker` service: `terrain3d` queue, `S3_TERRAIN3D_BUCKET`, `CORE_TERRAIN3D_MAX_UPLOAD_BYTES`, `CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS`)
- Modify: `.env.example` (same tuning vars, documented)
- Test: `core/tests/test_terrain3d_jobs.py`

**Interfaces:**
- Consumes: `repository.get_job`/`mark_converting`/`mark_done`/`mark_error` (Task 1); `Terrain3DPayload`/`BuilderConfig` (Task 2); `storage.download_to_file`/`upload_file`, `conversion.convert_to_cog`/`Terrain3DConversionError` (Task 3); `terrain3d_routes.get_task_deferrer` defers this task by name (Task 4).
- Produces: `convert_terrain3d_task(job_id: str, tenant_id: str) -> None`, registered on procrastinate queue `"terrain3d"`.

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_terrain3d_jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import os

import numpy as np
import pytest
import rasterio
from rasterio.transform import from_origin

from app.configs import repository as configs_repo
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import jobs as terrain3d_jobs
from app.terrain3d import repository as repo
from app.users.repository import get_or_create_user


def _write_test_geotiff_bytes() -> bytes:
    import io

    buf = io.BytesIO()
    data = np.linspace(0, 1000, 64 * 64, dtype="float32").reshape(64, 64)
    transform = from_origin(0, 0, 1, 1)
    with rasterio.io.MemoryFile() as mem:
        with mem.open(
            driver="GTiff", width=64, height=64, count=1, dtype="float32",
            crs="EPSG:4326", transform=transform,
        ) as dst:
            dst.write(data, 1)
        buf.write(mem.read())
    return buf.getvalue()


class _FakeBody:
    def __init__(self, data: bytes):
        import io

        self._buf = io.BytesIO(data)

    def iter_chunks(self, chunk_size: int):
        while True:
            chunk = self._buf.read(chunk_size)
            if not chunk:
                return
            yield chunk


class _FakeS3Client:
    def __init__(self, objects: dict[str, bytes]):
        self.objects = objects
        self.deleted: list[str] = []

    def head_object(self, Bucket, Key):  # noqa: N803
        return {"ContentLength": len(self.objects[Key])}

    def get_object(self, Bucket, Key):  # noqa: N803
        return {"Body": _FakeBody(self.objects[Key])}

    def upload_file(self, Filename, Bucket, Key):  # noqa: N803
        with open(Filename, "rb") as f:
            self.objects[Key] = f.read()

    def delete_object(self, Bucket, Key):  # noqa: N803
        self.deleted.append(Key)
        self.objects.pop(Key, None)


@pytest.fixture()
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")
    monkeypatch.setattr(terrain3d_jobs, "_TERRAIN3D_SCRATCH_ROOT", str(tmp_path))
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


def _make_job(Session, tenant, alice, *, source_key: str, title: str = "Relief"):
    with Session() as s:
        job = repo.create_job(
            s, tenant_id=tenant.id, created_by=alice.id,
            source_key=source_key, filename="dem.tif", title=title,
        )
        s.commit()
        return job.id


def test_convert_success_creates_item_and_config_and_purges_raw_upload(env, monkeypatch):
    Session, tenant, alice = env
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": _write_test_geotiff_bytes()})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "done"
        assert job.item_id is not None
        assert job.converted_key is not None

        item = items_repo.get_access_facts(s, tenant_id=tenant.id, item_id=job.item_id)
        assert item is not None

        config = configs_repo.get_config_by_item(s, job.item_id)
        assert config.config.kind == "terrain3d"
        assert config.config.terrain3d.sourceKey == job.converted_key
        assert config.config.terrain3d.originalFilename == "dem.tif"

    assert f"{tenant.id}/x/dem.tif" not in fake_s3.objects  # raw upload purged
    assert job.converted_key in fake_s3.objects  # converted COG present


def test_convert_failure_marks_error_and_purges_raw_upload_never_creates_item(env, monkeypatch):
    Session, tenant, alice = env
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": b"not a geotiff at all"})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert job.item_id is None
        assert job.error_message

    assert f"{tenant.id}/x/dem.tif" not in fake_s3.objects  # purged even on rejection
    assert fake_s3.deleted == [f"{tenant.id}/x/dem.tif"]


def test_convert_cleans_up_scratch_files_on_success_and_failure(env, monkeypatch, tmp_path):
    Session, tenant, alice = env

    def assert_scratch_empty_after():
        assert list(tmp_path.iterdir()) == [] or all(
            not any(p.iterdir()) for p in tmp_path.iterdir() if p.is_dir()
        )

    fake_s3_ok = _FakeS3Client({f"{tenant.id}/x/dem.tif": _write_test_geotiff_bytes()})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3_ok)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif", title="OK")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)
    assert_scratch_empty_after()

    fake_s3_bad = _FakeS3Client({f"{tenant.id}/y/dem.tif": b"garbage"})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3_bad)
    job_id_2 = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/y/dem.tif", title="Bad")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id_2, tenant_id=tenant.id)
    assert_scratch_empty_after()


def test_convert_missing_job_is_a_noop(env, monkeypatch):
    Session, tenant, _alice = env
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    terrain3d_jobs.convert_terrain3d_task(job_id="does-not-exist", tenant_id=tenant.id)  # must not raise


def test_convert_rejects_upload_over_max_bytes_without_downloading(env, monkeypatch):
    Session, tenant, alice = env
    oversized = _write_test_geotiff_bytes() * 1000  # comfortably over the 1-byte cap set below
    fake_s3 = _FakeS3Client({f"{tenant.id}/x/dem.tif": oversized})
    monkeypatch.setattr(terrain3d_jobs, "s3_client_from_env", lambda: fake_s3)
    monkeypatch.setattr(terrain3d_jobs, "_session_factory", lambda: Session)
    monkeypatch.setattr(terrain3d_jobs, "_max_upload_bytes", lambda: 1)
    download_calls = []
    monkeypatch.setattr(
        terrain3d_jobs, "download_to_file",
        lambda *a, **k: download_calls.append((a, k)),
    )

    job_id = _make_job(Session, tenant, alice, source_key=f"{tenant.id}/x/dem.tif")
    terrain3d_jobs.convert_terrain3d_task(job_id=job_id, tenant_id=tenant.id)

    with Session() as s:
        job = repo.get_job(s, tenant_id=tenant.id, job_id=job_id)
        assert job.status == "error"
        assert "volumineux" in job.error_message
    assert download_calls == []  # rejected before streaming a single byte
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_jobs.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.terrain3d.jobs'`.

- [ ] **Step 3: Implement `jobs.py`**

Create `core/app/terrain3d/jobs.py`:

```python
# SPDX-License-Identifier: Apache-2.0
"""Tâche procrastinate : télécharge l'upload brut en scratch local, le
convertit en COG (app.terrain3d.conversion), l'uploade sur S3, et — si tout
réussit — crée l'item + le BuilderConfig résultants. Toute erreur
(conversion ou inattendue) marque le job "error", jamais de job bloqué en
uploaded/converting ("zombie") — même critère que
app.tileset3d.jobs/app.ingestion.tasks. L'upload brut est purgé du bucket
dans tous les cas (succès ou échec) : rien ne le référence plus une fois la
tâche terminée."""
import logging
import os
import shutil
import tempfile

from app.audit.writer import write_audit
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Terrain3DPayload
from app.db import make_engine, make_session_factory, request_scoped_session
from app.ingestion.storage import make_s3_client
from app.items import repository as items_repo
from app.jobs import app
from app.terrain3d import repository as terrain3d_repo
from app.terrain3d.conversion import Terrain3DConversionError, convert_to_cog
from app.terrain3d.storage import download_to_file, upload_file

logger = logging.getLogger(__name__)

_TERRAIN3D_SCRATCH_ROOT = "/scratch"  # même volume que qgis-worker/pipelines ; monkeypatché en test


def s3_client_from_env():
    return make_s3_client(
        endpoint_url=os.environ["S3_ENDPOINT_URL"],
        access_key=os.environ["S3_ACCESS_KEY"],
        secret_key=os.environ["S3_SECRET_KEY"],
    )


def _session_factory():
    engine = make_engine(os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:"))
    return make_session_factory(engine)


def _terrain3d_bucket() -> str:
    return os.environ.get("S3_TERRAIN3D_BUCKET", "geostudio-terrain3d")


def _max_upload_bytes() -> int:
    return int(os.environ.get("CORE_TERRAIN3D_MAX_UPLOAD_BYTES", str(2 * 1024 * 1024 * 1024)))


def _conversion_timeout_seconds() -> int:
    return int(os.environ.get("CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS", "900"))


@app.task(queue="terrain3d")
def convert_terrain3d_task(job_id: str, tenant_id: str) -> None:
    session_factory = _session_factory()

    with request_scoped_session(session_factory) as session:
        job = terrain3d_repo.get_job(session, tenant_id=tenant_id, job_id=job_id)
        if job is None:
            logger.error("terrain3d job %s introuvable (tenant %s)", job_id, tenant_id)
            return
        source_key, filename, title, created_by = job.source_key, job.filename, job.title, job.created_by
        terrain3d_repo.mark_converting(session, job_id=job_id)
        session.commit()

    os.makedirs(_TERRAIN3D_SCRATCH_ROOT, exist_ok=True)
    scratch_dir = tempfile.mkdtemp(dir=_TERRAIN3D_SCRATCH_ROOT, prefix=f"terrain3d-{job_id}-")
    raw_path = os.path.join(scratch_dir, "raw")
    cog_path = os.path.join(scratch_dir, "cog.tif")
    s3 = s3_client_from_env()
    bucket = _terrain3d_bucket()

    try:
        content_length = s3.head_object(Bucket=bucket, Key=source_key)["ContentLength"]
        if content_length > _max_upload_bytes():
            raise Terrain3DConversionError(
                f"fichier trop volumineux ({content_length} > {_max_upload_bytes()} octets)"
            )
        download_to_file(s3, bucket=bucket, key=source_key, dest_path=raw_path)
        convert_to_cog(raw_path, cog_path, timeout_seconds=_conversion_timeout_seconds())

        converted_key = f"{tenant_id}/{job_id}/dem-cog.tif"
        upload_file(s3, bucket=bucket, key=converted_key, src_path=cog_path)

        with request_scoped_session(session_factory) as session:
            item = items_repo.create_item(
                session, tenant_id=tenant_id, owner_id=created_by,
                resource_type="terrain3d", title=title,
            )
            write_audit(
                session, tenant_id=tenant_id, actor_id=created_by, actor_kind="user",
                action="item.create", object_type="item", object_id=item.id,
                payload={"title": title, "filename": filename},
            )
            config = BuilderConfig(
                kind="terrain3d",
                terrain3d=Terrain3DPayload(sourceKey=converted_key, originalFilename=filename),
            )
            configs_repo.create_config(session, config, item_id=item.id, tenant_id=tenant_id)
            terrain3d_repo.mark_done(session, job_id=job_id, item_id=item.id, converted_key=converted_key)
        _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    except Terrain3DConversionError as exc:
        with request_scoped_session(session_factory) as session:
            terrain3d_repo.mark_error(session, job_id=job_id, error_message=str(exc))
        _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    except Exception as exc:  # toute erreur inattendue finit "error", jamais zombie
        logger.exception("terrain3d job %s : erreur inattendue", job_id)
        with request_scoped_session(session_factory) as session:
            terrain3d_repo.mark_error(session, job_id=job_id, error_message=f"erreur interne : {exc}")
        _purge_raw_upload(s3, bucket=bucket, source_key=source_key, tenant_id=tenant_id, job_id=job_id, session_factory=session_factory)
    finally:
        shutil.rmtree(scratch_dir, ignore_errors=True)


def _purge_raw_upload(s3, *, bucket: str, source_key: str, tenant_id: str, job_id: str, session_factory) -> None:
    # Un échec de purge ne doit jamais masquer l'issue réelle du job (succès
    # ou erreur) : try/except large, audit_log seulement quand la suppression
    # réussit vraiment — même discipline que app.tileset3d.jobs (précédent
    # SP-14o, purge du mode "replace").
    purged = False
    try:
        s3.delete_object(Bucket=bucket, Key=source_key)
        purged = True
    except Exception:
        logger.exception("terrain3d job %s : échec de la purge de l'upload brut (%s)", job_id, source_key)
    if purged:
        with request_scoped_session(session_factory) as session:
            write_audit(
                session, tenant_id=tenant_id, actor_id=None, actor_kind="agent",
                action="terrain3d.purge_raw_upload", object_type="terrain3d_job", object_id=job_id,
                payload={"sourceKey": source_key},
            )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_jobs.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Wire the compose stack — `worker` service**

In `docker-compose.yml`, update the `worker` service's `command:` to add the `terrain3d` queue:

```yaml
    command: >
      sh -c "python -m scripts.ensure_procrastinate_schema &&
             python -m procrastinate --app app.jobs.app worker -q ingestion,search,cdc,etl,tileset3d,terrain3d"
```

Add to the `worker` service's `environment:` block, right after `S3_TILESET3D_BUCKET`:

```yaml
      S3_TERRAIN3D_BUCKET: geostudio-terrain3d
      # Plafonds terrain3d (convert_terrain3d_task, app/terrain3d/jobs.py) —
      # s'exécutent dans ce process (`worker`).
      CORE_TERRAIN3D_MAX_UPLOAD_BYTES: ${CORE_TERRAIN3D_MAX_UPLOAD_BYTES:-2147483648}
      CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS: ${CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS:-900}
```

In `.env.example`, add right after the `TITILER_URL` line added in Task 4:

```
# Taille max de l'upload GeoTIFF brut, en octets (défaut 2 Gio), vérifiée
# côté worker avant de lancer la conversion (convert_terrain3d_task).
#CORE_TERRAIN3D_MAX_UPLOAD_BYTES=2147483648
# Délai max de la conversion GDAL elle-même, en secondes (défaut 15 min) —
# passé ce délai, le job passe "error" plutôt que de bloquer la file
# terrain3d indéfiniment (conversion.convert_to_cog, signal.alarm).
#CORE_TERRAIN3D_CONVERSION_TIMEOUT_SECONDS=900
```

- [ ] **Step 6: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: all previously-passing tests still pass.

- [ ] **Step 7: Commit**

```bash
cd core && git add app/terrain3d/jobs.py tests/test_terrain3d_jobs.py
git add ../docker-compose.yml ../.env.example
git commit -m "feat(core): terrain3d conversion task, worker queue wiring"
```

---

### Task 6: Core tile-serving proxy (TiTiler)

**Files:**
- Modify: `core/app/terrain3d/routes.py` (add the proxy route to the same router)
- Test: `core/tests/test_terrain3d_tile_proxy.py`

**Interfaces:**
- Consumes: `configs_repo.get_config_by_item`, `items_repo.get_access_facts`, `sharing.authorization.can` (all pre-existing, same as `app.tileset3d`'s read route); `get_terrain3d_bucket` (Task 4).
- Produces: `GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png` on the same router mounted in Task 4 (so it's gated by the same `CORE_TERRAIN3D_ENABLED` flag automatically — no separate wiring needed).

- [ ] **Step 1: Write the failing test**

Create `core/tests/test_terrain3d_tile_proxy.py`. Uses `pytest-httpserver` (already a dev dependency, `core/pyproject.toml`) as a real local stand-in for TiTiler — no httpx mocking library needed:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from pytest_httpserver import HTTPServer

from app import db
from app.auth.dependency import get_current_user
from app.configs import repository as configs_repo
from app.configs.schemas import BuilderConfig, Terrain3DPayload
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.terrain3d import routes as terrain3d_routes
from app.users.repository import get_or_create_user


@pytest.fixture()
def env(monkeypatch, httpserver: HTTPServer):
    monkeypatch.setenv("CORE_TERRAIN3D_ENABLED", "true")
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        alice = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=alice.id, resource_type="terrain3d", title="Relief",
        )
        config = BuilderConfig(
            kind="terrain3d",
            terrain3d=Terrain3DPayload(sourceKey=f"{tenant.id}/x/dem-cog.tif", originalFilename="dem.tif"),
        )
        configs_repo.create_config(s, config, item_id=item.id, tenant_id=tenant.id)
        s.commit()
        item_id = item.id
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: alice
    app.dependency_overrides[terrain3d_routes.get_titiler_url] = lambda: httpserver.url_for("")
    client = TestClient(app)
    return client, item_id, tenant, httpserver


def test_read_tile_proxies_titiler_with_terrarium_algorithm_and_source_key(env):
    client, item_id, tenant, httpserver = env
    httpserver.expect_request(
        "/cog/tiles/5/10/12.png",
        query_string=f"url=s3%3A%2F%2Fgeostudio-terrain3d%2F{tenant.id}%2Fx%2Fdem-cog.tif&algorithm=terrarium",
    ).respond_with_data(b"\x89PNG-fake-tile-bytes", content_type="image/png")

    r = client.get(f"/terrain3d/{item_id}/tiles/5/10/12.png")

    assert r.status_code == 200
    assert r.content == b"\x89PNG-fake-tile-bytes"
    assert r.headers["content-type"] == "image/png"


def test_read_tile_404_for_unknown_item(env):
    client, *_ = env
    r = client.get("/terrain3d/does-not-exist/tiles/0/0/0.png")
    assert r.status_code == 404


def test_read_tile_502_when_titiler_unreachable(env):
    client, item_id, *_ = env
    # Aucun handler enregistré sur httpserver pour cette route -> 404 côté
    # TiTiler simulé, que le proxy doit traduire en 502 (pas un 500 opaque).
    r = client.get(f"/terrain3d/{item_id}/tiles/99/99/99.png")
    assert r.status_code == 502
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_terrain3d_tile_proxy.py -v`
Expected: FAIL — `ImportError: cannot import name 'get_titiler_url'` (route doesn't exist yet).

- [ ] **Step 3: Implement the proxy route**

Add to `core/app/terrain3d/routes.py` (new imports at top, new function at the bottom):

```python
import httpx
from fastapi import Response

from app.configs import repository as configs_repo
from app.items import repository as items_repo
from app.sharing.authorization import can
```

```python
def get_titiler_url() -> str:
    return os.environ.get("TITILER_URL", "http://titiler:8000")


@router.get("/terrain3d/{item_id}/tiles/{z}/{x}/{y}.png")
def read_terrain3d_tile(
    item_id: str, z: int, x: int, y: int,
    session: Session = Depends(get_session),
    user: User = Depends(get_current_user),
    bucket: str = Depends(get_terrain3d_bucket),
    titiler_url: str = Depends(get_titiler_url),
) -> Response:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=item_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=404, detail="item not found")
    config = configs_repo.get_config_by_item(session, item_id)
    if config is None or config.config.terrain3d is None:
        raise HTTPException(status_code=404, detail="terrain not found")
    source_key = config.config.terrain3d.sourceKey

    try:
        resp = httpx.get(
            f"{titiler_url.rstrip('/')}/cog/tiles/{z}/{x}/{y}.png",
            params={"url": f"s3://{bucket}/{source_key}", "algorithm": "terrarium"},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status_code=502, detail="terrain tile service unavailable") from exc

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail="terrain tile service error")

    return Response(
        content=resp.content, media_type="image/png",
        headers={"Cache-Control": "private, max-age=3600"},
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_terrain3d_tile_proxy.py -v`
Expected: PASS (3 tests).

- [ ] **Step 5: Run the full core suite to check for regressions**

Run: `cd core && uv run pytest -q`
Expected: all previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd core && git add app/terrain3d/routes.py tests/test_terrain3d_tile_proxy.py
git commit -m "feat(core): terrain3d tile-serving proxy to TiTiler"
```

---

### Task 7: Regenerate OpenAPI spec and shell TS types

**Files:**
- Modify: `core/openapi.json` (regenerated, not hand-edited)
- Modify: `shell/src/api/generated/core-schema.d.ts` (regenerated, not hand-edited)

**Interfaces:**
- Consumes: every route/schema added in Tasks 2, 4, 6.
- Produces: up-to-date generated types consumed by Task 8's manual `ItemClient`/`types.ts` additions (the generated file is a drift-detection reference, not directly imported by hand-written client code — matches the existing `tileset3d` precedent).

- [ ] **Step 1: Enable the capability flag and regenerate `openapi.json`**

Run:
```bash
cd core && CORE_TERRAIN3D_ENABLED=true CORE_TILESET3D_ENABLED=false CORE_EXPORT_ENABLED=false CORE_ETL_ENABLED=false uv run python scripts/export_openapi.py openapi.json
```
Expected: `core/openapi.json` changes, purely additively (new `/terrain3d/...` paths and `Terrain3DPayload`/`Terrain3DUploadCreate`/etc. schemas appear; nothing existing is removed or changed in an incompatible way). Check `git diff core/openapi.json` to confirm no unrelated removals — if unrelated capability-gated paths (e.g. `tileset3d`/`etl`/`export`) disappear from the diff, that's expected (this repo's convention, confirmed by the tileset3d hosting plan Task 7 and its own committed fix: CI regenerates with every capability flag off, so the checked-in `openapi.json` never varies by which flags happen to be set locally) — regenerate a second time with **all** capability flags at their CI defaults (`false`) and use that as what actually gets committed:

```bash
cd core && uv run python scripts/export_openapi.py openapi.json
```

Confirm `git diff core/openapi.json` now shows **zero** `/terrain3d/...` paths (flag off) but the `Terrain3DPayload`/`BuilderConfig` schema additions still present (unconditional, `kind="terrain3d"` is not gated) — matches the tileset3d precedent noted in `docs/superpowers/plans/2026-08-13-3d-tileset-hosting.md` Task 7's own documented deviation.

- [ ] **Step 2: Regenerate the shell's TS types**

Run: `cd shell && npm run gen:api-types`
Expected: `shell/src/api/generated/core-schema.d.ts` changes, adding the new schemas/paths.

- [ ] **Step 3: Verify the shell still typechecks**

Run: `cd shell && npm run build`
Expected: PASS — the generated file isn't imported directly by hand-written code yet (Task 8 adds the manual `types.ts` additions), so this should be a no-op typecheck-wise; it only guards against an unrelated regeneration surprise.

- [ ] **Step 4: Commit**

```bash
git add core/openapi.json shell/src/api/generated/core-schema.d.ts
git commit -m "chore: regenerate OpenAPI spec and TS types for terrain3d"
```

---

### Task 8: Shell types — `ResourceType`, `InstanceInfo`, `ItemClient` interface

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `ResourceType` gains `"terrain3d"`; `InstanceInfo` gains `terrain3dEnabled: boolean`; `ItemClient` gains `listHostedTerrain3DSources(q?: string): Promise<{ id: string; title: string }[]>`, `createTerrain3DUpload(input: { key: string; filename: string; title: string }): Promise<{ jobId: string }>`, `getTerrain3DUploadJob(jobId: string): Promise<{ status: "uploaded" | "converting" | "done" | "error"; errorMessage: string | null; itemId: string | null }>`. Consumed by Task 9 (implementation), Task 11 (`TerrainPanel`).

- [ ] **Step 1: Make the additive type changes**

In `shell/src/api/types.ts`, update `ResourceType`:

```typescript
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline" | "alert" | "report" | "tileset3d" | "terrain3d";
```

Update `InstanceInfo`:

```typescript
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean; exportEnabled: boolean; tileset3dEnabled: boolean; terrain3dEnabled: boolean };
```

In the `ItemClient` interface, add right after the 4 `Tileset3D*` method signatures:

```typescript
  listHostedTerrain3DSources(q?: string): Promise<{ id: string; title: string }[]>;
  createTerrain3DUpload(input: { key: string; filename: string; title: string }): Promise<{ jobId: string }>;
  getTerrain3DUploadJob(jobId: string): Promise<{
    status: "uploaded" | "converting" | "done" | "error";
    errorMessage: string | null;
    itemId: string | null;
  }>;
```

- [ ] **Step 2: Verify the build fails as expected (interface not yet implemented)**

Run: `cd shell && npm run build`
Expected: FAIL — `itemClient.ts`'s object literal returned from `createItemClient` no longer satisfies the `ItemClient` interface (missing `listHostedTerrain3DSources`/`createTerrain3DUpload`/`getTerrain3DUploadJob`). This is the same intentional sequencing as the tileset3d hosting plan's Task 8 → Task 9 (types first, implementation next task).

- [ ] **Step 3: Commit**

```bash
cd shell && git add src/api/types.ts
git commit -m "feat(shell): terrain3d types on ResourceType/InstanceInfo/ItemClient"
```

---

### Task 9: Shell `itemClient` implementation

**Files:**
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (or the existing itemClient test file — check `ls shell/src/api/*.test.ts` first and add to whichever file already covers `createTileset3DUpload`/`fetchHostedTileset3dSources`, matching that file's existing MSW handler setup rather than creating a parallel one).

**Interfaces:**
- Consumes: `listHostedTerrain3DSources`/`createTerrain3DUpload`/`getTerrain3DUploadJob` signatures (Task 8); reuses the existing `presignUpload`/`uploadToPresignedUrl` methods verbatim (already implemented, ingestion's single-PUT pattern) — no new presign method needed on the interface, `TerrainPanel`/`Terrain3DUploadButton` (Task 11) will call `client.presignUpload(filename, "application/octet-stream")` directly, exactly like the ingestion upload flow does.
- Produces: working implementations of the 3 new `ItemClient` methods, satisfying Task 8's interface.

- [ ] **Step 1: Write the failing test**

Locate the existing test file covering `fetchHostedTileset3dSources`/`createTileset3DUpload` (run `grep -rl "fetchHostedTileset3dSources\|createTileset3DUpload" shell/src/api/*.test.ts` to find it) and add:

```typescript
test("listHostedTerrain3DSources lists terrain3d items via /items", async () => {
  server.use(
    http.get(`${CORE_URL}/items`, ({ request }) => {
      const url = new URL(request.url);
      expect(url.searchParams.get("type")).toBe("terrain3d");
      return HttpResponse.json({ items: [{ pk: "t-1", title: "Relief du massif" }] });
    }),
  );
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  const sources = await client.listHostedTerrain3DSources();
  expect(sources).toEqual([{ id: "t-1", title: "Relief du massif" }]);
});

test("createTerrain3DUpload posts key/filename/title and returns jobId", async () => {
  server.use(
    http.post(`${CORE_URL}/terrain3d/uploads`, async ({ request }) => {
      const body = await request.json();
      expect(body).toEqual({ key: "tenant/x/dem.tif", filename: "dem.tif", title: "Relief" });
      return HttpResponse.json({ jobId: "job-1" }, { status: 201 });
    }),
  );
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  const { jobId } = await client.createTerrain3DUpload({
    key: "tenant/x/dem.tif", filename: "dem.tif", title: "Relief",
  });
  expect(jobId).toBe("job-1");
});

test("getTerrain3DUploadJob returns job status", async () => {
  server.use(
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "t-1" }),
    ),
  );
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  const status = await client.getTerrain3DUploadJob("job-1");
  expect(status).toEqual({ status: "done", errorMessage: null, itemId: "t-1" });
});
```

Match this snippet's imports (`server`, `http`, `HttpResponse`, `CORE_URL`, `createItemClient`) to whatever the surrounding file already imports — adjust names if the existing test file uses different local aliases.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- itemClient` (adjust to the actual test file name found in Step 1)
Expected: FAIL — `client.listHostedTerrain3DSources is not a function`.

- [ ] **Step 3: Implement the 3 methods**

In `shell/src/api/itemClient.ts`, add a new private helper right after `fetchHostedTileset3dSources`:

```typescript
  async function fetchHostedTerrain3dSources(q?: string): Promise<{ id: string; title: string }[]> {
    const query = new URLSearchParams({ type: "terrain3d", pageSize: "200" });
    if (q) query.set("q", q);
    const token = getToken();
    const res = await fetch(`${coreUrl}/items?${query.toString()}`, {
      headers: token ? { Authorization: `Bearer ${token}` } : {},
    });
    if (!res.ok) throw new Error(`Request failed: ${res.status} /items`);
    const data = (await res.json()) as { items?: { pk: string; title: string }[] };
    return (data.items ?? []).map((item) => ({ id: item.pk, title: item.title }));
  }
```

Add the 3 public methods to the returned object literal, right after `getTileset3DUploadJob`:

```typescript
    async listHostedTerrain3DSources(q?: string) {
      return fetchHostedTerrain3dSources(q);
    },

    async createTerrain3DUpload(input: { key: string; filename: string; title: string }) {
      return request<{ jobId: string }>("POST", "/terrain3d/uploads", input);
    },

    async getTerrain3DUploadJob(jobId: string) {
      return request<{
        status: "uploaded" | "converting" | "done" | "error";
        errorMessage: string | null;
        itemId: string | null;
      }>("GET", `/terrain3d/uploads/${jobId}`);
    },
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- itemClient`
Expected: PASS.

- [ ] **Step 5: Verify the shell builds**

Run: `cd shell && npm run build`
Expected: PASS — `ItemClient` interface (Task 8) is now fully satisfied.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/api/itemClient.ts src/api/itemClient.test.ts
git commit -m "feat(shell): implement terrain3d itemClient methods"
```

---

### Task 10: Shell `MapView` — generalized origin-check helper + `transformRequest` bearer attachment

**Files:**
- Modify: `shell/src/map/MapView.tsx`
- Test: `shell/src/map/MapView.test.tsx`

**Interfaces:**
- Consumes: `getAuthToken`/`getCoreUrl` props (already threaded through `MapView`, used by the existing `Tile3DLayer` bearer attachment).
- Produces: `isHostedCoreUrl(url: string, coreUrl: string | undefined, pathPrefix: string): boolean` (generalized, replaces the body of the now-thinner `isHostedTilesetUrl`); a new `HOSTED_TERRAIN3D_PATH = "/terrain3d/"` constant; a `transformRequest` callback passed to `new maplibregl.Map({...})` that attaches `Authorization: Bearer` to requests matching `HOSTED_TERRAIN3D_PATH` under the real core origin.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/map/MapView.test.tsx`, near the existing `attaches a bearer token to a hosted (/tileset3d/) tiles3d layer's requests` tests:

```typescript
test("transformRequest attaches a bearer token to a hosted (/terrain3d/) terrain tile request", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  render(
    <MapView
      config={{ ...baseConfig, terrain: { tilesUrl: "https://core.test/terrain3d/item-1/tiles/{z}/{x}/{y}.png", encoding: "terrarium" } }}
      getAuthToken={getAuthToken}
      getCoreUrl={getCoreUrl}
    />,
  );
  const mapInstance = getLastMapInstance(); // however this file's existing tests already access the maplibregl.Map mock instance — match that pattern
  const transformRequest = mapInstance.constructorArgs.transformRequest;
  const result = transformRequest("https://core.test/terrain3d/item-1/tiles/5/10/12.png", "Tile");
  expect(result).toEqual({
    url: "https://core.test/terrain3d/item-1/tiles/5/10/12.png",
    headers: { Authorization: "Bearer secret-token" },
  });
});

test("transformRequest does not attach a bearer token to an external terrain URL", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  render(
    <MapView
      config={{ ...baseConfig, terrain: { tilesUrl: "https://terrain.example/{z}/{x}/{y}.png", encoding: "terrarium" } }}
      getAuthToken={getAuthToken}
      getCoreUrl={getCoreUrl}
    />,
  );
  const mapInstance = getLastMapInstance();
  const transformRequest = mapInstance.constructorArgs.transformRequest;
  const result = transformRequest("https://terrain.example/5/10/12.png", "Tile");
  expect(result).toEqual({ url: "https://terrain.example/5/10/12.png" });
});

test("transformRequest does not leak the token when the URL merely contains /terrain3d/ on a different origin", () => {
  const getAuthToken = () => "secret-token";
  const getCoreUrl = () => "https://core.test";
  render(
    <MapView
      config={{ ...baseConfig, terrain: { tilesUrl: "https://attacker.test/x/terrain3d/y/tiles/{z}/{x}/{y}.png", encoding: "terrarium" } }}
      getAuthToken={getAuthToken}
      getCoreUrl={getCoreUrl}
    />,
  );
  const mapInstance = getLastMapInstance();
  const transformRequest = mapInstance.constructorArgs.transformRequest;
  const result = transformRequest("https://attacker.test/x/terrain3d/y/tiles/5/10/12.png", "Tile");
  expect(result).toEqual({ url: "https://attacker.test/x/terrain3d/y/tiles/5/10/12.png" });
});
```

Before writing these verbatim, check how this file's existing `maplibregl.Map` mock exposes constructor args to tests (search `MapView.test.tsx` for how the `vi.mock("maplibre-gl", ...)` mock is set up, and how any existing test reads options passed to `new maplibregl.Map(...)`) — reuse that exact access pattern rather than inventing `getLastMapInstance()`/`constructorArgs` if the file already has an established way to inspect map construction options.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- MapView`
Expected: FAIL — `mapInstance.constructorArgs.transformRequest is not a function` (or equivalent, depending on the file's actual mock-access pattern).

- [ ] **Step 3: Generalize the helper and add `transformRequest`**

In `shell/src/map/MapView.tsx`, replace the existing `HOSTED_TILESET3D_PATH`/`isHostedTilesetUrl` block:

```typescript
const HIGHLIGHT_ID = "__highlight__";
const TERRAIN_SOURCE_ID = "__terrain__";
// Path segments distinguishing our own authenticated proxies (served by
// core, design docs §4) from an externally-hosted resource at the same-
// looking path — the latter must never receive our session's bearer token.
const HOSTED_TILESET3D_PATH = "/tileset3d/";
const HOSTED_TERRAIN3D_PATH = "/terrain3d/";

// Real "is this hosted by us" check: a substring match on the URL is not
// enough — layer/terrain URLs are freeform (an author can type any external
// URL via LayerPicker/TerrainPanel), so an attacker-controlled URL like
// "https://attacker.example/x/terrain3d/y/tiles/0/0/0.png" would otherwise
// pass a bare `.includes(pathPrefix)` check and leak the session's bearer
// token cross-origin. A URL only counts as hosted when its origin matches
// the configured core API's origin AND its pathname starts with the proxy
// route's own path segment. Shared by both the tileset3d (deck.gl
// Tile3DLayer, see buildTiles3DLayer) and terrain3d (MapLibre
// transformRequest, see below) call sites — never duplicate this check.
function isHostedCoreUrl(url: string, coreUrl: string | undefined, pathPrefix: string): boolean {
  if (!coreUrl) return false;
  try {
    const target = new URL(url);
    const core = new URL(coreUrl);
    return target.origin === core.origin && target.pathname.startsWith(pathPrefix);
  } catch {
    return false;
  }
}

function isHostedTilesetUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TILESET3D_PATH);
}

function isHostedTerrainUrl(url: string, coreUrl: string | undefined): boolean {
  return isHostedCoreUrl(url, coreUrl, HOSTED_TERRAIN3D_PATH);
}
```

Add the `transformRequest` option to the `new maplibregl.Map({...})` call (near where `getAuthTokenRef`/`getCoreUrlRef` are already read for `applyDeckLayers`):

```typescript
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: config.basemap.style,
      center: config.view.center,
      zoom: config.view.zoom,
      pitch: config.view.pitch ?? 0,
      bearing: config.view.bearing ?? 0,
      transformRequest: (url: string) => {
        if (isHostedTerrainUrl(url, getCoreUrlRef.current?.())) {
          const token = getAuthTokenRef.current?.();
          if (token) return { url, headers: { Authorization: `Bearer ${token}` } };
        }
        return { url };
      },
    });
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- MapView`
Expected: PASS, including the 2 pre-existing tileset3d bearer-attachment tests (unaffected — `isHostedTilesetUrl`'s external behavior is unchanged, only its internals now delegate to the shared helper).

- [ ] **Step 5: Run the full shell test suite to check for regressions**

Run: `cd shell && npm run test`
Expected: all previously-passing tests still pass.

- [ ] **Step 6: Commit**

```bash
cd shell && git add src/map/MapView.tsx src/map/MapView.test.tsx
git commit -m "feat(shell): attach bearer token to hosted terrain tile requests"
```

---

### Task 11: Shell `TerrainPanel` — hosted DEM picker + upload button

**Files:**
- Create: `shell/src/map/Terrain3DUploadButton.tsx`
- Create: `shell/src/map/Terrain3DUploadButton.test.tsx`
- Modify: `shell/src/map/TerrainPanel.tsx`
- Test: `shell/src/map/TerrainPanel.test.tsx` (create if it doesn't already exist — check with `ls shell/src/map/TerrainPanel.test.tsx` first)

**Interfaces:**
- Consumes: `useItemClient` (existing hook, `shell/src/api/hooks.ts`); `client.listHostedTerrain3DSources`, `client.presignUpload`, `client.uploadToPresignedUrl`, `client.createTerrain3DUpload`, `client.getTerrain3DUploadJob` (Task 9); `getCoreUrl` — `TerrainPanel` needs the core base URL to build the hosted `tilesUrl`; check whether `TerrainPanel`'s existing callers already thread a `coreUrl`/`getCoreUrl` prop through `MapEditorPage.tsx`, and if not, source it from `useItemClient()`'s own `getCoreUrl?.()` (same accessor `MapView` already uses) rather than adding a new prop.
- Produces: `TerrainPanel` renders a "DEM hébergé" `<select>` populated from `listHostedTerrain3DSources()`, and a `Terrain3DUploadButton` that uploads a new DEM and, on success, refreshes the list and selects the new item — both gated behind `useInstanceInfo().data?.terrain3dEnabled === true` (same discipline as `ExportPanel`/`exportEnabled` in `MapEditorPage.tsx`); the external URL field is never gated.

- [ ] **Step 1: Write the failing `Terrain3DUploadButton` test**

Create `shell/src/map/Terrain3DUploadButton.test.tsx` (mirrors `shell/src/shell/Tileset3DUploadButton.test.tsx` — read that file first to match its exact MSW/render-helper setup, since this step's assertions below assume the same conventions):

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test, vi } from "vitest";
import { Terrain3DUploadButton } from "./Terrain3DUploadButton";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { createItemClient } from "../api/itemClient";

const CORE_URL = "https://core.test";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderButton(onUploaded: () => void) {
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  return render(
    <ItemClientProvider client={client}>
      <Terrain3DUploadButton onUploaded={onUploaded} pollIntervalMs={0} />
    </ItemClientProvider>,
  );
}

test("uploads a DEM and calls onUploaded once the conversion job is done", async () => {
  server.use(
    http.post(`${CORE_URL}/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new HttpResponse(null, { status: 200 })),
    http.post(`${CORE_URL}/terrain3d/uploads`, () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "done", errorMessage: null, itemId: "t-1" }),
    ),
  );
  const onUploaded = vi.fn();
  renderButton(onUploaded);

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief du massif");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await waitFor(() => expect(onUploaded).toHaveBeenCalledWith("t-1"));
});

test("shows the conversion error message and does not call onUploaded", async () => {
  server.use(
    http.post(`${CORE_URL}/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new HttpResponse(null, { status: 200 })),
    http.post(`${CORE_URL}/terrain3d/uploads`, () => HttpResponse.json({ jobId: "job-1" }, { status: 201 })),
    http.get(`${CORE_URL}/terrain3d/uploads/job-1`, () =>
      HttpResponse.json({ status: "error", errorMessage: "GeoTIFF illisible", itemId: null }),
    ),
  );
  const onUploaded = vi.fn();
  renderButton(onUploaded);

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await screen.findByText("GeoTIFF illisible");
  expect(onUploaded).not.toHaveBeenCalled();
});

test("blocks Annuler/Escape/backdrop while an upload is in flight", async () => {
  server.use(
    http.post(`${CORE_URL}/uploads/presign`, () =>
      HttpResponse.json({ uploadUrl: `${CORE_URL}/fake-s3-put`, key: "tenant/x/dem.tif" }),
    ),
    http.put(`${CORE_URL}/fake-s3-put`, () => new Promise(() => {})), // never resolves: stays "uploading"
  );
  renderButton(vi.fn());

  await userEvent.click(screen.getByRole("button", { name: /nouveau dem/i }));
  const file = new File([new Uint8Array(16)], "dem.tif", { type: "application/octet-stream" });
  await userEvent.upload(screen.getByLabelText(/fichier dem/i), file);
  await userEvent.type(screen.getByLabelText(/titre/i), "Relief");
  await userEvent.click(screen.getByRole("button", { name: /importer/i }));

  await waitFor(() => expect(screen.getByRole("button", { name: /annuler/i })).toBeDisabled());
});
```

Match imports (`ItemClientProvider`, `createItemClient`) to whatever `Tileset3DUploadButton.test.tsx` actually imports — this snippet assumes the same module paths that file uses; adjust if they differ.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- Terrain3DUploadButton`
Expected: FAIL — module `./Terrain3DUploadButton` doesn't exist.

- [ ] **Step 3: Implement `Terrain3DUploadButton`**

Create `shell/src/map/Terrain3DUploadButton.tsx` (single presigned PUT, no multipart — Global Constraints):

```typescript
// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { useItemClient } from "../api/hooks";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

const DEFAULT_POLL_INTERVAL_MS = 1500;
// Un job de conversion qui n'atteint jamais un état terminal ne doit pas
// laisser le dialogue définitivement infermable — même garde-fou que
// Tileset3DUploadButton (design tileset3d hosting, leçon Task 12/I3).
const POLL_TIMEOUT_MS = 5 * 60 * 1000;

type Phase = "form" | "uploading" | "converting" | "error";

// pollIntervalMs is injectable for tests only (this file's suite is
// MSW-based with real timers, where fake timers would fight userEvent's
// own scheduler) — mirrors Tileset3DUploadButton's pollTimeoutMs param.
export function Terrain3DUploadButton({
  onUploaded, pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
}: {
  onUploaded: (itemId: string) => void;
  pollIntervalMs?: number;
}) {
  const [open, setOpen] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [title, setTitle] = useState("");
  const [phase, setPhase] = useState<Phase>("form");
  const [error, setError] = useState("");
  const client = useItemClient();

  function close() {
    setOpen(false);
    setFile(null);
    setTitle("");
    setPhase("form");
    setError("");
  }

  async function poll(jobId: string) {
    const deadline = Date.now() + POLL_TIMEOUT_MS;
    for (;;) {
      const job = await client.getTerrain3DUploadJob(jobId);
      if (job.status === "done" && job.itemId) {
        onUploaded(job.itemId);
        close();
        return;
      }
      if (job.status === "error") {
        setPhase("error");
        setError(job.errorMessage ?? "Échec de la conversion du DEM.");
        return;
      }
      if (Date.now() >= deadline) {
        setPhase("error");
        setError("La conversion du DEM prend trop de temps. Réessayez plus tard.");
        return;
      }
      await new Promise((r) => setTimeout(r, pollIntervalMs));
    }
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file || !title.trim()) return;
    setPhase("uploading");
    setError("");
    try {
      const { uploadUrl, key } = await client.presignUpload(file.name, "application/octet-stream");
      await client.uploadToPresignedUrl(uploadUrl, file);
      setPhase("converting");
      const { jobId } = await client.createTerrain3DUpload({ key, filename: file.name, title: title.trim() });
      await poll(jobId);
    } catch (e) {
      setPhase("error");
      setError(e instanceof Error ? e.message : "Échec de l'envoi du DEM.");
    }
  }

  const busy = phase === "uploading" || phase === "converting";

  // Même garde que Tileset3DUploadButton : fermer le dialogue en plein
  // envoi/conversion laisserait le chaîne submit()/poll() tourner en
  // arrière-plan sans dialogue pour la refléter.
  function requestClose() {
    if (busy) return;
    close();
  }

  return (
    <>
      <Button size="sm" variant="outline" onClick={() => setOpen(true)}>
        Nouveau DEM
      </Button>
      <Dialog open={open} onClose={requestClose} title="Nouveau DEM">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Fichier DEM (GeoTIFF)
            <input
              aria-label="Fichier DEM (GeoTIFF)"
              type="file"
              accept=".tif,.tiff"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          {phase === "uploading" && <p className="text-sm text-slate-500">Envoi du fichier…</p>}
          {phase === "converting" && <p className="text-sm text-slate-500">Conversion en COG…</p>}
          {phase === "error" && (
            <p role="alert" className="text-sm text-red-600">{error}</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close} disabled={busy}>
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

Run: `cd shell && npm run test -- Terrain3DUploadButton`
Expected: PASS (3 tests).

- [ ] **Step 5: Write the failing `TerrainPanel` test**

Create (or extend) `shell/src/map/TerrainPanel.test.tsx`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { afterAll, afterEach, beforeAll, expect, test, vi } from "vitest";
import { TerrainPanel } from "./TerrainPanel";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { createItemClient } from "../api/itemClient";

const CORE_URL = "https://core.test";
const server = setupServer();
beforeAll(() => server.listen({ onUnhandledRequest: "error" }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

function renderPanel(onChange: (next: unknown) => void, { terrain3dEnabled = true } = {}) {
  server.use(
    http.get(`${CORE_URL}/instance`, () => HttpResponse.json({ readOnly: false, terrain3dEnabled })),
  );
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <TerrainPanel value={null} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("selecting a hosted DEM sets tilesUrl to the terrain3d proxy URL", async () => {
  server.use(
    http.get(`${CORE_URL}/items`, () =>
      HttpResponse.json({ items: [{ pk: "t-1", title: "Relief du massif" }] }),
    ),
  );
  const onChange = vi.fn();
  renderPanel(onChange);

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  const select = await screen.findByLabelText(/dem hébergé/i);
  await userEvent.selectOptions(select, "t-1");

  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith({
      tilesUrl: `${CORE_URL}/terrain3d/t-1/tiles/{z}/{x}/{y}.png`,
      encoding: "terrarium",
      exaggeration: 1,
    }),
  );
});

test("external URL field remains usable and independent of the hosted picker", async () => {
  server.use(http.get(`${CORE_URL}/items`, () => HttpResponse.json({ items: [] })));
  const onChange = vi.fn();
  renderPanel(onChange);

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  await userEvent.type(screen.getByLabelText(/url de tuiles terrain/i), "https://ext.example/{z}/{x}/{y}.png");
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ tilesUrl: "https://ext.example/{z}/{x}/{y}.png" }),
  );
});

test("hosted DEM picker and upload button stay hidden when terrain3dEnabled is false", async () => {
  const onChange = vi.fn();
  renderPanel(onChange, { terrain3dEnabled: false });

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  // External field still there (never gated)...
  expect(screen.getByLabelText(/url de tuiles terrain/i)).toBeInTheDocument();
  // ...but the hosted section is gone, so nothing hits the disabled /terrain3d/* routes.
  expect(screen.queryByLabelText(/dem hébergé/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /nouveau dem/i })).not.toBeInTheDocument();
});
```

`renderPanel` wraps `TerrainPanel` in a `QueryClientProvider` because `useInstanceInfo()` (Task 11's new capability-flag gate, added in Step 7 below) uses the same TanStack Query hook `MapEditorPage`/`ExportPanel` already rely on elsewhere in the shell — match whichever import path (`@tanstack/react-query` vs. a local wrapper) `MapEditorPage.test.tsx` or `ExportPanel.test.tsx` already uses for this exact setup, rather than assuming `@tanstack/react-query` directly if this codebase wraps it.

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npm run test -- TerrainPanel`
Expected: FAIL — no "DEM hébergé" select exists yet.

- [ ] **Step 7: Implement the hosted DEM picker in `TerrainPanel`**

Replace `shell/src/map/TerrainPanel.tsx` with:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import type { MapTerrainConfig } from "../api/types";
import { useInstanceInfo, useItemClient } from "../api/hooks";
import { Terrain3DUploadButton } from "./Terrain3DUploadButton";

export function TerrainPanel({
  value, onChange,
}: {
  value: MapTerrainConfig | null;
  onChange: (next: MapTerrainConfig | null) => void;
}) {
  const enabled = value != null;
  const client = useItemClient();
  const instanceQuery = useInstanceInfo();
  // Gate the hosted picker + upload button behind the capability flag, not
  // just the routes: an instance with CORE_TERRAIN3D_ENABLED=false must not
  // even offer UI that would hit a 404'd /terrain3d/* route (same discipline
  // as ExportPanel/exportEnabled in MapEditorPage.tsx). The external URL
  // field is never gated — it has no dependency on this capability.
  const terrain3dEnabled = instanceQuery.data?.terrain3dEnabled === true;
  const [hostedSources, setHostedSources] = useState<{ id: string; title: string }[]>([]);

  async function refreshHostedSources() {
    try {
      setHostedSources(await client.listHostedTerrain3DSources());
    } catch {
      setHostedSources([]); // liste vide plutôt qu'une erreur bloquante pour le champ URL manuelle
    }
  }

  useEffect(() => {
    if (enabled && terrain3dEnabled) refreshHostedSources();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [enabled, terrain3dEnabled]);

  function toggle(checked: boolean) {
    onChange(checked ? { tilesUrl: "", encoding: "terrarium", exaggeration: 1 } : null);
  }

  function patch(partial: Partial<MapTerrainConfig>) {
    if (!value) return;
    onChange({ ...value, ...partial });
  }

  // `Number("") === 0`: clearing the field must not silently flatten the
  // terrain. An empty (or otherwise unparseable) input leaves the current
  // exaggeration untouched.
  function patchExaggeration(raw: string) {
    if (raw.trim() === "") return;
    const next = Number(raw);
    if (!Number.isFinite(next)) return;
    patch({ exaggeration: next });
  }

  function selectHosted(itemId: string) {
    if (!itemId) return;
    const coreUrl = client.getCoreUrl?.();
    if (!coreUrl) return;
    patch({ tilesUrl: `${coreUrl}/terrain3d/${itemId}/tiles/{z}/{x}/{y}.png`, encoding: "terrarium" });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="mb-1 mt-3 text-xs font-medium text-slate-500">Terrain 3D</p>
      <label className="flex items-center gap-2 text-sm">
        <input
          aria-label="Activer le terrain 3D"
          type="checkbox"
          checked={enabled}
          onChange={(e) => toggle(e.target.checked)}
        />
        Activer le terrain 3D
      </label>
      {enabled && value && (
        <>
          {terrain3dEnabled && (
            <>
              <label className="flex flex-col gap-1 text-sm">
                DEM hébergé
                <select aria-label="DEM hébergé" defaultValue="" onChange={(e) => selectHosted(e.target.value)}>
                  <option value="">— choisir un DEM hébergé —</option>
                  {hostedSources.map((s) => (
                    <option key={s.id} value={s.id}>{s.title}</option>
                  ))}
                </select>
              </label>
              <Terrain3DUploadButton onUploaded={(itemId) => { refreshHostedSources(); selectHosted(itemId); }} />
            </>
          )}
          <label className="flex flex-col gap-1 text-sm">
            URL de tuiles terrain (terrain-RGB, encodage terrarium)
            <input
              aria-label="URL de tuiles terrain"
              type="text"
              placeholder="https://…/{z}/{x}/{y}.png"
              value={value.tilesUrl}
              onChange={(e) => patch({ tilesUrl: e.target.value })}
            />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Exaggeration
            <input
              aria-label="Exaggeration du terrain"
              type="number"
              step={0.1}
              min={0}
              value={value.exaggeration ?? 1}
              onChange={(e) => patchExaggeration(e.target.value)}
            />
          </label>
        </>
      )}
    </div>
  );
}
```

Before finalizing, verify `useItemClient()`'s return type actually exposes `getCoreUrl` (Task 8 added it to the `ItemClient` interface as optional, mirroring `MapView`'s existing usage) — if `hooks.ts`'s `useItemClient` wraps the client in a way that drops optional methods, adjust `selectHosted` to read it the same way `MapView.tsx` already does (check that call site) instead of assuming direct passthrough.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npm run test -- TerrainPanel`
Expected: PASS (3 tests).

- [ ] **Step 9: Run the full shell test suite and build to check for regressions**

Run: `cd shell && npm run test && npm run build`
Expected: all previously-passing tests still pass; build succeeds.

- [ ] **Step 10: Commit**

```bash
cd shell && git add src/map/Terrain3DUploadButton.tsx src/map/Terrain3DUploadButton.test.tsx src/map/TerrainPanel.tsx src/map/TerrainPanel.test.tsx
git commit -m "feat(shell): hosted DEM picker and upload button in TerrainPanel"
```

---

### Task 12: E2E Playwright spec

**Files:**
- Create: `shell/e2e/terrain3d-hosting.spec.ts`

**Interfaces:**
- Consumes: `shell/e2e/mocks.ts::mockCore` (every shell E2E spec runs against `VITE_AUTH_MODE=mock` with the core API fully intercepted via Playwright `page.route(...)`, never a real core/worker/TiTiler stack — confirmed by reading `shell/e2e/tileset3d.spec.ts` in full, which is this task's direct template: a route-mocked single-file-equivalent upload flow ending in a job-status poll, then a proxy-URL network assertion). `mockCore`'s default `**/items*` handler already filters by `type` (fixed for the tileset3d spec's own regression, `shell/e2e/mocks.ts` lines ~56-65) — no shared-file changes needed here, only a spec-local item fixture.

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/terrain3d-hosting.spec.ts`, modeled directly on `shell/e2e/tileset3d.spec.ts`'s `mockTileset3DUploadFlow`/test pair, adapted for terrain3d's single presigned-PUT upload (no multipart parts loop) and for `TerrainPanel` instead of `LayerPicker`:

```typescript
// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

async function mockTerrain3DUploadFlow(page: Page) {
  let jobPolls = 0;
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, terrain3dEnabled: true } });
  });
  await page.route("**/uploads/presign", async (route) => {
    await route.fulfill({ json: { uploadUrl: "https://minio.test/terrain3d-raw", key: "t-mock/x/dem.tif" } });
  });
  await page.route("https://minio.test/terrain3d-raw", async (route) => {
    await route.fulfill({ status: 200, body: "" });
  });
  await page.route("**/terrain3d/uploads", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({ json: { jobId: "job-1" }, status: 201 });
  });
  await page.route("**/terrain3d/uploads/job-1", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    jobPolls += 1;
    if (jobPolls < 2) {
      await route.fulfill({ json: { status: "converting", errorMessage: null, itemId: null } });
    } else {
      await route.fulfill({ json: { status: "done", errorMessage: null, itemId: "d1" } });
    }
  });
  await page.route("https://core.test/items?*", async (route) => {
    const url = new URL(route.request().url());
    if (url.searchParams.get("type") !== "terrain3d") return route.fallback();
    await route.fulfill({
      json: {
        items: [{
          pk: "d1", resourceType: "terrain3d", title: "Relief du massif E2E", abstract: "",
          owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: null, isPublished: false,
        }],
        total: 1, page: 1, pageSize: 200,
      },
    });
  });
  await page.route("https://core.test/terrain3d/d1/tiles/*/*/*.png", async (route) => {
    await route.fulfill({ status: 200, contentType: "image/png", body: Buffer.from("fake-png-tile") });
  });
}

test("upload a DEM, select it as hosted terrain, tiles resolve", async ({ page }) => {
  await mockCore(page);
  await mockTerrain3DUploadFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const newItemDialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await newItemDialog.getByLabel("Type").selectOption("map");
  await newItemDialog.getByLabel("Titre").fill("Carte avec terrain hébergé");
  await newItemDialog.getByRole("button", { name: "Créer" }).click();
  await expect(page.locator("canvas.maplibregl-canvas")).toBeVisible();

  await page.getByLabel("Activer le terrain 3D").check();
  await page.getByRole("button", { name: "Nouveau DEM" }).click();
  await page.getByLabel("Fichier DEM (GeoTIFF)").setInputFiles({
    name: "dem.tif", mimeType: "application/octet-stream", buffer: Buffer.from("fake dem bytes"),
  });
  await page.getByLabel("Titre").fill("Relief du massif E2E");
  await page.getByRole("button", { name: "Importer" }).click();
  await expect(page.getByRole("dialog", { name: "Nouveau DEM" })).toHaveCount(0, { timeout: 10_000 });

  const tileRequest = page.waitForResponse((r) => /\/terrain3d\/d1\/tiles\/.+\.png$/.test(r.url()));
  await page.getByLabel("DEM hébergé").selectOption("d1");
  const response = await tileRequest;
  expect(response.status()).toBe(200);
});
```

Per `mockTileset3DUploadFlow`'s established convention (`shell/e2e/tileset3d.spec.ts`), the `/items/{id}`-style create-map response is already covered generically by `mockCore`'s default map-creation handling — confirm this by reading `shell/e2e/map-editor.spec.ts`'s "create a Map" test first if unsure; do not duplicate that route mock here. Selecting a value in the "DEM hébergé" `<select>` is what triggers MapLibre to actually request a terrain tile (`applyTerrain`, `MapView.tsx`) — that's why the tile-request assertion is anchored to the `selectOption` call rather than to the earlier upload-dialog close.

- [ ] **Step 2: Run the spec**

Run: `cd shell && npx playwright test e2e/terrain3d-hosting.spec.ts`
Expected: PASS. If the tile request never fires (MapLibre's `raster-dem` source may debounce or require a `moveend`/idle tick before issuing its first tile request — behavior not observable from this plan alone), add `await page.waitForTimeout(0)` is not an acceptable fix; instead inspect whether `applyTerrain`/`map.setTerrain` needs an explicit `map.triggerRepaint()` or an initial viewport nudge to provoke the first tile fetch in a headless context, by comparing against how `map-editor.spec.ts`'s existing terrain-URL test (if one exists — check `grep -n "Activer le terrain 3d" shell/e2e/*.spec.ts` first) already gets its first terrain tile request to fire.

- [ ] **Step 3: Run the full E2E suite to check for regressions**

Run: `cd shell && npm run e2e`
Expected: all specs pass, including every pre-existing one (no regression — this task adds a new spec file and touches no shared code).

- [ ] **Step 4: Commit**

```bash
cd shell && git add e2e/terrain3d-hosting.spec.ts
git commit -m "test(e2e): upload a DEM and select it as hosted terrain via TerrainPanel"
```

---

## Manual acceptance checks (not CI-enforced, per Global Constraints)

Before flipping `CORE_TERRAIN3D_ENABLED=true` in any real environment, run once against a real deployed stack (not required for the plan's tasks to be considered complete):

1. Convert a real-world DEM (a few hundred MB) and confirm conversion time/memory stay within acceptable bounds for the `worker` container's resource limits.
2. Load a hosted terrain in the map viewer and pan/zoom across it, confirming tile requests resolve promptly under the core→TiTiler proxy hop (no CDN, per design §1/§8 — this is the accepted v1 cost, not a bug to chase here).
3. **Confirm TiTiler can actually read `s3://` from MinIO** (final-branch-review finding I3, defensive fix, never exercised end-to-end): the `titiler` service now also carries `AWS_S3_ENDPOINT=minio:9000`, `AWS_HTTPS=NO`, `AWS_VIRTUAL_HOSTING=FALSE` in `docker-compose.yml`. `AWS_ENDPOINT_URL` alone is a boto3/AWS-SDK name that GDAL's `/vsis3/` driver — what `rasterio.open("s3://…")` inside rio-tiler ultimately uses — does not read. Request one tile through `GET /terrain3d/{item_id}/tiles/{z}/{x}/{y}.png` against a real stack and confirm a 200 (a mis-resolved endpoint surfaces as a 502 from the proxy, not a 404).

---

## Post-plan: update `CLAUDE.md`

Once all 12 tasks are merged and verified, add a `### Fait` entry documenting this increment (non-numbered, "reste de la vision post-v0.1", same convention as the "3D (hébergement de tilesets uploadés)" entry it follows), and narrow the "reste de la vision post-v0.1, 3D" bullet's still-open list down to the remaining two items: `mapbox`/`terrainrgb` encoding, and 3D conversion tooling (py3dtiles, point clouds). This is a documentation step, not a plan task — follow the `finishing-a-development-branch` skill for the actual merge/branch decision.
