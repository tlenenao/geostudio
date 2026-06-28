# Builder Service (SP-0a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the FastAPI "Builder Service" that stores, validates and versions the no-code App/Dashboard configurations for the GeoStudio platform, and links each config to a shareable GeoNode item.

**Architecture:** A small FastAPI app backed by PostgreSQL via SQLAlchemy 2.0. A Pydantic schema validates the config envelope (data sources, layout, inter-widget messages). A repository layer persists each save as an immutable revision, allowing rollback. GeoNode is accessed through a narrow `ItemClient` port so the service stays testable in isolation (a stub is used in tests; a real HTTP adapter is wired last).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2, pytest, httpx (TestClient), uv (packaging). PostgreSQL in production, in-memory SQLite in tests.

## Global Constraints

- Python version floor: **3.12** (use `from __future__ import annotations` not required; native generics OK).
- The browser never talks to this service for tile data — this service handles **configs and item linkage only**.
- Config envelope `kind` is exactly one of `"app"` or `"dashboard"` (same schema for both).
- App and Dashboard configs share **one** schema (`BuilderConfig`); no separate models.
- Every save creates a new immutable revision; configs are never updated in place.
- All persistence goes through the repository layer; routes never touch the ORM session directly except via the injected dependency.
- GeoNode access goes through the `ItemClient` protocol only; no direct GeoNode imports outside `app/geonode.py`.

---

### Task 1: Project scaffold + health endpoint

**Files:**
- Create: `builder-service/pyproject.toml`
- Create: `builder-service/app/__init__.py`
- Create: `builder-service/app/main.py`
- Test: `builder-service/tests/__init__.py`
- Test: `builder-service/tests/test_health.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `app.main.create_app() -> fastapi.FastAPI` (application factory); a `GET /health` route returning `{"status": "ok"}`.

- [ ] **Step 1: Create `builder-service/pyproject.toml`**

```toml
[project]
name = "geostudio-builder-service"
version = "0.1.0"
description = "GeoStudio Builder Service — stores and versions App/Dashboard configs"
requires-python = ">=3.12"
dependencies = [
    "fastapi>=0.111",
    "uvicorn[standard]>=0.30",
    "sqlalchemy>=2.0",
    "pydantic>=2.7",
    "httpx>=0.27",
]

[dependency-groups]
dev = [
    "pytest>=8.2",
]

[tool.pytest.ini_options]
pythonpath = ["."]
testpaths = ["tests"]
```

- [ ] **Step 2: Create empty package files**

Create `builder-service/app/__init__.py` and `builder-service/tests/__init__.py`, both empty.

- [ ] **Step 3: Write the failing test**

Create `builder-service/tests/test_health.py`:

```python
from fastapi.testclient import TestClient

from app.main import create_app


def test_health_returns_ok():
    client = TestClient(create_app())
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- [ ] **Step 4: Run test to verify it fails**

Run (from `builder-service/`): `uv run pytest tests/test_health.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.main'`.

- [ ] **Step 5: Write minimal implementation**

Create `builder-service/app/main.py`:

```python
from fastapi import FastAPI


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/test_health.py -v`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add builder-service/pyproject.toml builder-service/app builder-service/tests
git commit -m "feat(builder-service): scaffold FastAPI app with health endpoint"
```

---

### Task 2: Config envelope schema (Pydantic)

**Files:**
- Create: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py`

**Interfaces:**
- Consumes: nothing.
- Produces: Pydantic models in `app.schemas`:
  - `DataSource(id: str, type: str, service: str, layer: str, query: dict = {})`
  - `LayoutItem(widget: str, x: int, y: int, w: int, h: int, props: dict = {})`
  - `Layout(type: Literal["grid"], breakpoints: dict = {}, items: list[LayoutItem] = [])`
  - `Message(from_: str (alias "from"), event: str, to: str, action: str)`
  - `BuilderConfig(version: int = 1, itemId: str | None = None, kind: Literal["app","dashboard"], theme: dict = {}, dataSources: list[DataSource] = [], layout: Layout, messages: list[Message] = [])`
  - `BuilderConfig` uses `populate_by_name=True` so both `from` and `from_` work.

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_schemas.py`:

```python
import pytest
from pydantic import ValidationError

from app.schemas import BuilderConfig


def _valid_payload(kind: str = "app") -> dict:
    return {
        "version": 1,
        "kind": kind,
        "dataSources": [
            {"id": "ds1", "type": "feature", "service": "martin",
             "layer": "communes", "query": {}}
        ],
        "layout": {
            "type": "grid",
            "breakpoints": {"lg": 12},
            "items": [
                {"widget": "map", "x": 0, "y": 0, "w": 8, "h": 6, "props": {}},
                {"widget": "table", "x": 8, "y": 0, "w": 4, "h": 6, "props": {}},
            ],
        },
        "messages": [
            {"from": "map", "event": "select", "to": "table", "action": "filter"}
        ],
    }


def test_valid_app_config_parses():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.kind == "app"
    assert config.layout.items[0].widget == "map"
    assert config.messages[0].from_ == "map"


def test_valid_dashboard_config_parses():
    config = BuilderConfig.model_validate(_valid_payload("dashboard"))
    assert config.kind == "dashboard"


def test_invalid_kind_rejected():
    payload = _valid_payload()
    payload["kind"] = "website"
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_layout_required():
    payload = _valid_payload()
    del payload["layout"]
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate(payload)


def test_message_from_alias_round_trips():
    config = BuilderConfig.model_validate(_valid_payload())
    dumped = config.model_dump(by_alias=True)
    assert dumped["messages"][0]["from"] == "map"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.schemas'`.

- [ ] **Step 3: Write minimal implementation**

Create `builder-service/app/schemas.py`:

```python
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class DataSource(BaseModel):
    id: str
    type: str
    service: str
    layer: str
    query: dict = Field(default_factory=dict)


class LayoutItem(BaseModel):
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)


class Layout(BaseModel):
    type: Literal["grid"]
    breakpoints: dict = Field(default_factory=dict)
    items: list[LayoutItem] = Field(default_factory=list)


class Message(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    event: str
    to: str
    action: str


class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout
    messages: list[Message] = Field(default_factory=list)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_schemas.py -v`
Expected: PASS (5 tests).

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/schemas.py builder-service/tests/test_schemas.py
git commit -m "feat(builder-service): add validated BuilderConfig schema"
```

---

### Task 3: Database models + session

**Files:**
- Create: `builder-service/app/db.py`
- Create: `builder-service/app/models.py`
- Test: `builder-service/tests/test_models.py`

**Interfaces:**
- Consumes: nothing.
- Produces:
  - `app.db.Base` (SQLAlchemy `DeclarativeBase`).
  - `app.db.make_engine(url: str)` and `app.db.make_session_factory(engine)` returning a `sessionmaker[Session]`.
  - `app.db.init_db(engine)` creating all tables.
  - `app.models.Config(id: str, kind: str, item_id: str | None, current_version: int, created_at, updated_at)`.
  - `app.models.ConfigRevision(id: int, config_id: str, version: int, data: dict, created_at)`.

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_models.py`:

```python
from sqlalchemy import select

from app.db import Base, make_engine, make_session_factory, init_db
from app.models import Config, ConfigRevision


def test_can_persist_config_and_revision():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as session:
        config = Config(id="c1", kind="app", item_id=None, current_version=1)
        session.add(config)
        session.add(ConfigRevision(config_id="c1", version=1, data={"kind": "app"}))
        session.commit()

    with Session() as session:
        loaded = session.scalar(select(Config).where(Config.id == "c1"))
        assert loaded is not None
        assert loaded.kind == "app"
        assert loaded.current_version == 1
        rev = session.scalar(select(ConfigRevision).where(ConfigRevision.config_id == "c1"))
        assert rev.data == {"kind": "app"}


def test_base_metadata_has_both_tables():
    assert "configs" in Base.metadata.tables
    assert "config_revisions" in Base.metadata.tables
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_models.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.db'`.

- [ ] **Step 3: Write `app/db.py`**

```python
from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    pass


def make_engine(url: str) -> Engine:
    connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
    return create_engine(url, connect_args=connect_args)


def make_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False)


def init_db(engine: Engine) -> None:
    # Import models so they register on Base.metadata before create_all.
    from app import models  # noqa: F401

    Base.metadata.create_all(engine)
```

- [ ] **Step 4: Write `app/models.py`**

```python
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Config(Base):
    __tablename__ = "configs"

    id: Mapped[str] = mapped_column(String, primary_key=True)
    kind: Mapped[str] = mapped_column(String, nullable=False)
    item_id: Mapped[str | None] = mapped_column(String, nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=_now, onupdate=_now)


class ConfigRevision(Base):
    __tablename__ = "config_revisions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    config_id: Mapped[str] = mapped_column(ForeignKey("configs.id"), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    data: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_now)
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_models.py -v`
Expected: PASS (2 tests).

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/db.py builder-service/app/models.py builder-service/tests/test_models.py
git commit -m "feat(builder-service): add SQLAlchemy models and session factory"
```

---

### Task 4: Repository layer (create / get / update / revisions / rollback)

**Files:**
- Create: `builder-service/app/repository.py`
- Test: `builder-service/tests/test_repository.py`

**Interfaces:**
- Consumes: `app.schemas.BuilderConfig`, `app.models.Config`, `app.models.ConfigRevision`, `app.db` factories.
- Produces in `app.repository`:
  - `ConfigRead(BaseModel)` with `id: str, kind: str, itemId: str | None, version: int, config: BuilderConfig`.
  - `RevisionInfo(BaseModel)` with `version: int, created_at: datetime`.
  - `create_config(session, config: BuilderConfig, item_id: str | None) -> ConfigRead`
  - `get_config(session, config_id: str) -> ConfigRead | None`
  - `update_config(session, config_id: str, config: BuilderConfig) -> ConfigRead | None` (None if not found; new revision otherwise)
  - `list_revisions(session, config_id: str) -> list[RevisionInfo]`
  - `rollback_config(session, config_id: str, version: int) -> ConfigRead | None` (copies an old revision as a new revision; None if config or version missing)

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_repository.py`:

```python
import pytest

from app.db import make_engine, make_session_factory, init_db
from app import repository as repo
from app.schemas import BuilderConfig


@pytest.fixture()
def session():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        yield s


def _config(kind: str = "app", widget: str = "map") -> BuilderConfig:
    return BuilderConfig.model_validate({
        "kind": kind,
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    })


def test_create_then_get(session):
    created = repo.create_config(session, _config(), item_id="item-1")
    assert created.version == 1
    assert created.itemId == "item-1"

    loaded = repo.get_config(session, created.id)
    assert loaded is not None
    assert loaded.config.kind == "app"
    assert loaded.config.layout.items[0].widget == "map"


def test_get_missing_returns_none(session):
    assert repo.get_config(session, "nope") is None


def test_update_creates_new_revision(session):
    created = repo.create_config(session, _config(widget="map"), item_id=None)
    updated = repo.update_config(session, created.id, _config(widget="table"))
    assert updated is not None
    assert updated.version == 2
    assert updated.config.layout.items[0].widget == "table"

    revisions = repo.list_revisions(session, created.id)
    assert [r.version for r in revisions] == [1, 2]


def test_update_missing_returns_none(session):
    assert repo.update_config(session, "nope", _config()) is None


def test_rollback_restores_old_revision_as_new(session):
    created = repo.create_config(session, _config(widget="map"), item_id=None)
    repo.update_config(session, created.id, _config(widget="table"))

    rolled = repo.rollback_config(session, created.id, version=1)
    assert rolled is not None
    assert rolled.version == 3
    assert rolled.config.layout.items[0].widget == "map"
    assert [r.version for r in repo.list_revisions(session, created.id)] == [1, 2, 3]


def test_rollback_missing_version_returns_none(session):
    created = repo.create_config(session, _config(), item_id=None)
    assert repo.rollback_config(session, created.id, version=99) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_repository.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.repository'`.

- [ ] **Step 3: Write minimal implementation**

Create `builder-service/app/repository.py`:

```python
import uuid
from datetime import datetime

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Config, ConfigRevision
from app.schemas import BuilderConfig


class ConfigRead(BaseModel):
    id: str
    kind: str
    itemId: str | None
    version: int
    config: BuilderConfig


class RevisionInfo(BaseModel):
    version: int
    created_at: datetime


def _to_read(config: Config, revision: ConfigRevision) -> ConfigRead:
    return ConfigRead(
        id=config.id,
        kind=config.kind,
        itemId=config.item_id,
        version=revision.version,
        config=BuilderConfig.model_validate(revision.data),
    )


def _latest_revision(session: Session, config_id: str) -> ConfigRevision | None:
    return session.scalar(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id)
        .order_by(ConfigRevision.version.desc())
    )


def create_config(session: Session, config: BuilderConfig, item_id: str | None) -> ConfigRead:
    config_id = uuid.uuid4().hex
    record = Config(id=config_id, kind=config.kind, item_id=item_id, current_version=1)
    revision = ConfigRevision(
        config_id=config_id, version=1, data=config.model_dump(by_alias=True)
    )
    session.add(record)
    session.add(revision)
    session.commit()
    session.refresh(record)
    return _to_read(record, revision)


def get_config(session: Session, config_id: str) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    revision = _latest_revision(session, config_id)
    if revision is None:
        return None
    return _to_read(record, revision)


def update_config(session: Session, config_id: str, config: BuilderConfig) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    new_version = record.current_version + 1
    revision = ConfigRevision(
        config_id=config_id, version=new_version, data=config.model_dump(by_alias=True)
    )
    record.current_version = new_version
    session.add(revision)
    session.commit()
    session.refresh(record)
    return _to_read(record, revision)


def list_revisions(session: Session, config_id: str) -> list[RevisionInfo]:
    revisions = session.scalars(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id)
        .order_by(ConfigRevision.version.asc())
    ).all()
    return [RevisionInfo(version=r.version, created_at=r.created_at) for r in revisions]


def rollback_config(session: Session, config_id: str, version: int) -> ConfigRead | None:
    record = session.get(Config, config_id)
    if record is None:
        return None
    source = session.scalar(
        select(ConfigRevision)
        .where(ConfigRevision.config_id == config_id, ConfigRevision.version == version)
    )
    if source is None:
        return None
    new_version = record.current_version + 1
    revision = ConfigRevision(config_id=config_id, version=new_version, data=source.data)
    record.current_version = new_version
    session.add(revision)
    session.commit()
    session.refresh(record)
    return _to_read(record, revision)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/repository.py builder-service/tests/test_repository.py
git commit -m "feat(builder-service): add config repository with revisioning and rollback"
```

---

### Task 5: GeoNode item client port + stub

**Files:**
- Create: `builder-service/app/geonode.py`
- Test: `builder-service/tests/test_geonode.py`

**Interfaces:**
- Consumes: nothing.
- Produces in `app.geonode`:
  - `ItemClient` (typing.Protocol) with `create_item(self, title: str, type: str, owner: str) -> str`.
  - `StubItemClient` implementing the protocol: returns a generated id (`"item-" + uuid hex`) and records calls in `self.created: list[dict]`.

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_geonode.py`:

```python
from app.geonode import ItemClient, StubItemClient


def test_stub_creates_item_and_records_call():
    client: ItemClient = StubItemClient()
    item_id = client.create_item(title="My App", type="app", owner="alice")
    assert item_id.startswith("item-")
    assert client.created == [{"title": "My App", "type": "app", "owner": "alice"}]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geonode.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.geonode'`.

- [ ] **Step 3: Write minimal implementation**

Create `builder-service/app/geonode.py`:

```python
import uuid
from typing import Protocol


class ItemClient(Protocol):
    def create_item(self, title: str, type: str, owner: str) -> str:
        """Create a shareable item in the content backend, returning its id."""
        ...


class StubItemClient:
    def __init__(self) -> None:
        self.created: list[dict] = []

    def create_item(self, title: str, type: str, owner: str) -> str:
        self.created.append({"title": title, "type": type, "owner": owner})
        return "item-" + uuid.uuid4().hex
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_geonode.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/geonode.py builder-service/tests/test_geonode.py
git commit -m "feat(builder-service): add ItemClient port and in-memory stub"
```

---

### Task 6: API routes + dependency wiring

**Files:**
- Create: `builder-service/app/routes.py`
- Modify: `builder-service/app/main.py`
- Test: `builder-service/tests/test_routes.py`

**Interfaces:**
- Consumes: `app.repository`, `app.schemas.BuilderConfig`, `app.geonode.ItemClient`/`StubItemClient`, `app.db` factories.
- Produces in `app.routes`:
  - `get_session()` and `get_item_client()` FastAPI dependencies (overridable in tests).
  - `router` (`APIRouter`) with:
    - `POST /configs` body `CreateConfigRequest{title: str, owner: str, config: BuilderConfig}` → 201 `ConfigRead` (creates a GeoNode item, links it).
    - `GET /configs/{config_id}` → 200 `ConfigRead` or 404.
    - `PUT /configs/{config_id}` body `BuilderConfig` → 200 `ConfigRead` or 404.
    - `GET /configs/{config_id}/revisions` → 200 `list[RevisionInfo]`.
    - `POST /configs/{config_id}/rollback` body `RollbackRequest{version: int}` → 200 `ConfigRead` or 404.
- Modifies `app.main.create_app` to: build engine from `DATABASE_URL` env (default in-memory sqlite), `init_db`, include `router`, and register default dependency providers.

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_routes.py`:

```python
import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.db import make_engine, make_session_factory, init_db
from app.geonode import StubItemClient
from app import routes


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)
    stub = StubItemClient()

    app = create_app()

    def override_session():
        with Session() as s:
            yield s

    app.dependency_overrides[routes.get_session] = override_session
    app.dependency_overrides[routes.get_item_client] = lambda: stub

    test_client = TestClient(app)
    test_client.stub = stub  # type: ignore[attr-defined]
    return test_client


def _config_body(widget: str = "map") -> dict:
    return {
        "kind": "app",
        "layout": {"type": "grid", "items": [
            {"widget": widget, "x": 0, "y": 0, "w": 4, "h": 4}
        ]},
    }


def _create(client, widget: str = "map") -> dict:
    response = client.post("/configs", json={
        "title": "My App", "owner": "alice", "config": _config_body(widget)
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_create_config_creates_item_and_returns_201(client):
    body = _create(client)
    assert body["version"] == 1
    assert body["itemId"].startswith("item-")
    assert client.stub.created[0]["title"] == "My App"


def test_get_config_returns_it(client):
    created = _create(client)
    response = client.get(f"/configs/{created['id']}")
    assert response.status_code == 200
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_get_missing_config_returns_404(client):
    assert client.get("/configs/nope").status_code == 404


def test_put_updates_and_bumps_version(client):
    created = _create(client, widget="map")
    response = client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    assert response.status_code == 200
    assert response.json()["version"] == 2
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "table"


def test_put_missing_config_returns_404(client):
    assert client.put("/configs/nope", json=_config_body()).status_code == 404


def test_revisions_listed(client):
    created = _create(client)
    client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    response = client.get(f"/configs/{created['id']}/revisions")
    assert response.status_code == 200
    assert [r["version"] for r in response.json()] == [1, 2]


def test_rollback_restores_revision(client):
    created = _create(client, widget="map")
    client.put(f"/configs/{created['id']}", json=_config_body(widget="table"))
    response = client.post(f"/configs/{created['id']}/rollback", json={"version": 1})
    assert response.status_code == 200
    assert response.json()["version"] == 3
    assert response.json()["config"]["layout"]["items"][0]["widget"] == "map"


def test_rollback_missing_returns_404(client):
    created = _create(client)
    assert client.post(
        f"/configs/{created['id']}/rollback", json={"version": 99}
    ).status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_routes.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.routes'`.

- [ ] **Step 3: Write `app/routes.py`**

```python
from collections.abc import Iterator

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app import repository as repo
from app.geonode import ItemClient, StubItemClient
from app.repository import ConfigRead, RevisionInfo
from app.schemas import BuilderConfig

router = APIRouter()

# Default providers; create_app() overrides get_session with a real factory,
# and tests override both via app.dependency_overrides.
_default_item_client = StubItemClient()


def get_session() -> Iterator[Session]:  # pragma: no cover - overridden at runtime
    raise RuntimeError("get_session dependency not configured")


def get_item_client() -> ItemClient:
    return _default_item_client


class CreateConfigRequest(BaseModel):
    title: str
    owner: str
    config: BuilderConfig


class RollbackRequest(BaseModel):
    version: int


@router.post("/configs", response_model=ConfigRead, status_code=status.HTTP_201_CREATED)
def create_config(
    request: CreateConfigRequest,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
) -> ConfigRead:
    item_id = items.create_item(
        title=request.title, type=request.config.kind, owner=request.owner
    )
    return repo.create_config(session, request.config, item_id=item_id)


@router.get("/configs/{config_id}", response_model=ConfigRead)
def get_config(config_id: str, session: Session = Depends(get_session)) -> ConfigRead:
    result = repo.get_config(session, config_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.put("/configs/{config_id}", response_model=ConfigRead)
def update_config(
    config_id: str,
    config: BuilderConfig,
    session: Session = Depends(get_session),
) -> ConfigRead:
    result = repo.update_config(session, config_id, config)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.get("/configs/{config_id}/revisions", response_model=list[RevisionInfo])
def list_revisions(
    config_id: str, session: Session = Depends(get_session)
) -> list[RevisionInfo]:
    return repo.list_revisions(session, config_id)


@router.post("/configs/{config_id}/rollback", response_model=ConfigRead)
def rollback_config(
    config_id: str,
    request: RollbackRequest,
    session: Session = Depends(get_session),
) -> ConfigRead:
    result = repo.rollback_config(session, config_id, request.version)
    if result is None:
        raise HTTPException(status_code=404, detail="config or version not found")
    return result
```

- [ ] **Step 4: Update `app/main.py`**

Replace the contents of `builder-service/app/main.py` with:

```python
import os
from collections.abc import Iterator

from fastapi import FastAPI
from sqlalchemy.orm import Session

from app import routes
from app.db import init_db, make_engine, make_session_factory


def create_app() -> FastAPI:
    app = FastAPI(title="GeoStudio Builder Service", version="0.1.0")

    database_url = os.environ.get("DATABASE_URL", "sqlite+pysqlite:///:memory:")
    engine = make_engine(database_url)
    init_db(engine)
    session_factory = make_session_factory(engine)

    def get_session() -> Iterator[Session]:
        with session_factory() as session:
            yield session

    app.dependency_overrides[routes.get_session] = get_session
    app.include_router(routes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
```

- [ ] **Step 5: Run all tests to verify they pass**

Run: `uv run pytest -v`
Expected: PASS — all tests across `test_health`, `test_schemas`, `test_models`, `test_repository`, `test_geonode`, `test_routes`.

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/routes.py builder-service/app/main.py builder-service/tests/test_routes.py
git commit -m "feat(builder-service): add config CRUD/rollback API routes"
```

---

### Task 7: Real GeoNode HTTP adapter

**Files:**
- Modify: `builder-service/app/geonode.py`
- Test: `builder-service/tests/test_geonode_http.py`

**Interfaces:**
- Consumes: `httpx`, `ItemClient` protocol.
- Produces in `app.geonode`:
  - `GeoNodeItemClient(base_url: str, token: str, http: httpx.Client | None = None)` implementing `ItemClient`.
  - `create_item` POSTs to `{base_url}/api/v2/resources` with `{"title", "resource_type": type, "owner": owner}` and `Authorization: Bearer {token}`, returning `str(response.json()["resource"]["pk"])`.

- [ ] **Step 1: Write the failing test**

Create `builder-service/tests/test_geonode_http.py`:

```python
import httpx

from app.geonode import GeoNodeItemClient, ItemClient


def test_geonode_client_posts_and_returns_pk():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["json"] = httpx.Request(
            request.method, request.url, content=request.content
        ).content
        return httpx.Response(201, json={"resource": {"pk": 42}})

    transport = httpx.MockTransport(handler)
    http = httpx.Client(transport=transport)
    client: ItemClient = GeoNodeItemClient(
        base_url="https://geonode.example", token="t0ken", http=http
    )

    item_id = client.create_item(title="My App", type="app", owner="alice")

    assert item_id == "42"
    assert captured["url"] == "https://geonode.example/api/v2/resources"
    assert captured["auth"] == "Bearer t0ken"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_geonode_http.py -v`
Expected: FAIL — `ImportError: cannot import name 'GeoNodeItemClient'`.

- [ ] **Step 3: Add the adapter to `app/geonode.py`**

Append to `builder-service/app/geonode.py`:

```python
import httpx


class GeoNodeItemClient:
    def __init__(
        self, base_url: str, token: str, http: httpx.Client | None = None
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._token = token
        self._http = http or httpx.Client()

    def create_item(self, title: str, type: str, owner: str) -> str:
        response = self._http.post(
            f"{self._base_url}/api/v2/resources",
            json={"title": title, "resource_type": type, "owner": owner},
            headers={"Authorization": f"Bearer {self._token}"},
        )
        response.raise_for_status()
        return str(response.json()["resource"]["pk"])
```

Also add `import httpx` to the top of the file if not already present (move it up with the other imports).

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_geonode_http.py -v`
Expected: PASS.

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -v`
Expected: PASS (all tests).

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/geonode.py builder-service/tests/test_geonode_http.py
git commit -m "feat(builder-service): add real GeoNode HTTP item adapter"
```

---

### Task 8: Containerization + compose integration

**Files:**
- Create: `builder-service/Dockerfile`
- Create: `builder-service/.dockerignore`
- Modify: `docker-compose.yml` (add `builder-service` service)
- Test: manual smoke test (commands below)

**Interfaces:**
- Consumes: the existing `postgis` service and `.env` (`PG_PASSWORD`) from the repo root compose file.
- Produces: a `builder-service` container listening on port `8200`, env `DATABASE_URL` pointing at PostgreSQL.

- [ ] **Step 1: Create `builder-service/Dockerfile`**

```dockerfile
FROM python:3.12-slim

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml ./
RUN uv pip install --system --no-cache \
    "fastapi>=0.111" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "pydantic>=2.7" "httpx>=0.27" "psycopg[binary]>=3.1"

COPY app ./app

EXPOSE 8200
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8200"]
```

- [ ] **Step 2: Create `builder-service/.dockerignore`**

```
tests/
__pycache__/
*.pyc
.pytest_cache/
.venv/
```

- [ ] **Step 3: Add the service to `docker-compose.yml`**

Add under `services:` (match the indentation of existing services such as `martin`):

```yaml
  builder-service:
    build: ./builder-service
    environment:
      DATABASE_URL: postgresql+psycopg://gis:${PG_PASSWORD}@pgbouncer:6432/gis
    ports:
      - "8200:8200"
    networks: [gis-net]
    depends_on: [pgbouncer]
```

- [ ] **Step 4: Build and smoke-test**

Run:
```bash
docker compose build builder-service
docker compose up -d postgis pgbouncer builder-service
sleep 8
curl -s http://localhost:8200/health
```
Expected: `{"status":"ok"}`.

- [ ] **Step 5: Smoke-test a config round-trip**

Run:
```bash
curl -s -X POST http://localhost:8200/configs \
  -H 'Content-Type: application/json' \
  -d '{"title":"Smoke","owner":"admin","config":{"kind":"dashboard","layout":{"type":"grid","items":[{"widget":"map","x":0,"y":0,"w":4,"h":4}]}}}'
```
Expected: JSON with `"version":1` and an `"itemId"` (a stub item id unless GeoNode wiring is configured).

- [ ] **Step 6: Commit**

```bash
git add builder-service/Dockerfile builder-service/.dockerignore docker-compose.yml
git commit -m "feat(builder-service): add Dockerfile and docker-compose service"
```

---

## Self-Review

**Spec coverage (against SP-0a scope — config storage/validation/versioning + item linkage):**
- Validated config envelope → Task 2. ✅
- Versioned persistence + rollback → Tasks 3, 4. ✅
- CRUD API → Task 6. ✅
- GeoNode item linkage via port → Tasks 5, 7. ✅
- Browser never fetches tiles here (configs only) → enforced by design; no tile endpoints added. ✅
- Deployment integration with existing stack → Task 8. ✅
- The shell `item-client` façade, map viewer, canvas engine, widgets → **out of SP-0a** (SP-0b/0c/0d), as planned.

**Placeholder scan:** No TBD/TODO; every code step contains complete code. ✅

**Type consistency:** `ConfigRead`/`RevisionInfo` defined in Task 4 are reused verbatim in Task 6 routes. `ItemClient.create_item(title, type, owner) -> str` defined in Task 5 is matched by `StubItemClient` (Task 5) and `GeoNodeItemClient` (Task 7), and called identically in Task 6. `get_session`/`get_item_client` dependency names are consistent between Task 6 routes, `main.py`, and the route tests. ✅

## Notes for SP-0b → SP-0d

The frontend `item-client` façade (SP-0b) will consume this service's `POST/GET/PUT /configs` plus `GET /configs/{id}/revisions` and `POST /configs/{id}/rollback`, and GeoNode's API v2 for catalog/sharing. Keep the `ConfigRead` shape stable as the contract.
