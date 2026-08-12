# SP-14o — Requête visuelle : plan d'implémentation

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Livrer l'assistant no-code « requête visuelle » (dernière pièce de SP-14, jalon M11) : un utilisateur compose Filtrer→Joindre→Résumer sur une collection, l'assistant provisionne une collection de sortie, compile et exécute un `Pipeline` SP-15 contraint qui écrit dans un dataset créé pour l'occasion, et permet de rouvrir l'assistant plus tard.

**Architecture:** Cœur : une nouvelle capacité de provisionnement de collection vide (`create_empty_collection`, précédent réutilisé de l'ingestion SP-6a) exposée par une route non-admin, un champ `sourcePipelineId` sur `DatasetPayload` avec validation croisée (patron `alert_validation.py`), et un correctif sur `_write_dataset` qui l'effaçait silencieusement à chaque re-run. Shell : le wizard pré-crée le dataset (pk connu), compile un `PipelinePayload` standard référençant ce `datasetId` via `writer.dataset`, le sauvegarde par la route générique `/configs` (aucune route bespoke côté shell), puis déclenche et suit son run — évitant tout problème de « comment retrouver l'item créé par un job async ».

**Tech Stack:** FastAPI/Pydantic/SQLAlchemy (cœur), React/TS/Vitest/React Query (shell), pytest (`@pytest.mark.postgis` pour le DDL réel), Playwright (E2E).

## Global Constraints

- Contrat de couches import-linter existant respecté : `app.collections` reste strictement en-dessous d'`app.pipelines`/`app.configs` — aucune nouvelle dépendance inversée.
- Messages d'erreur de validation croisée génériques (existence vs lisibilité indiscernables), même patron que `get_readable_collection`/`alert_validation.py` : `"pipeline not found"` dans tous les cas d'échec.
- Toute chaîne SQL construite par interpolation doit échapper identifiants (`"..."`, doubler les guillemets) et littéraux (`'...'`, doubler les apostrophes) — jamais de concaténation non échappée d'une valeur utilisateur.
- Tests Vitest colocalisés (`*.test.ts`/`*.test.tsx`), tests pytest sous `core/tests/`.
- Docs/commentaires en français, code/identifiants en anglais (CLAUDE.md).
- Commits conventionnels (`feat(core): …`, `feat(shell): …`), un sujet par commit.
- **Correction découverte pendant ce plan (déjà reportée dans la spec, commit `5718f64`)** : `transform.filter.expr` est une expression scalaire SQL DuckDB bornée, **pas du CEL** — voir `core/app/pipelines/expr_validation.py`. Tout le code de ce plan compile vers du SQL, jamais du CEL.
- **Précision de câblage non présente dans la spec (need-to-know pour ce plan)** : `transform.join` utilise `JOIN ... USING (on)` — une seule colonne de jointure au nom identique des deux côtés. Toute colonne du côté joint qui entrerait en collision de nom avec le côté base (hors la colonne de jointure elle-même) doit être renommée **avant** la jointure, via un `transform.select` posé sur la branche jointe (entre son `reader.collection` et l'arête secondaire du `transform.join`) — `transform.select` est une PROJECTION (`SELECT <colonnes listées> FROM ...`), pas un rename in-place : toute colonne omise du dict `columns` est perdue.

---

## Task 1 : schémas `EmptyCollectionColumn`/`EmptyCollectionCreate` + garde de type SQL

**Files:**
- Modify: `core/app/collections/schemas.py`
- Test: `core/tests/test_empty_collection_schema.py`

**Interfaces:**
- Produces: `EmptyCollectionColumn{name: str, sqlType: Literal[...]}`, `EmptyCollectionCreate{title: str, columns: list[EmptyCollectionColumn], geometryType: Literal[...] | None, srid: int | None}` — consommés par Task 2 (`create_empty_collection`) et Task 3 (route).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_empty_collection_schema.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.collections.schemas import EmptyCollectionColumn, EmptyCollectionCreate


def test_accepts_a_valid_payload_with_known_sql_types():
    payload = EmptyCollectionCreate(
        title="Ma requête",
        columns=[
            EmptyCollectionColumn(name="commune", sqlType="text"),
            EmptyCollectionColumn(name="total", sqlType="integer"),
        ],
        geometryType="Point", srid=4326,
    )
    assert payload.columns[0].sqlType == "text"


def test_rejects_an_unknown_sql_type():
    with pytest.raises(ValidationError):
        EmptyCollectionColumn(name="x", sqlType="text); DROP TABLE users; --")


def test_rejects_an_unknown_geometry_type():
    with pytest.raises(ValidationError):
        EmptyCollectionCreate(title="t", columns=[], geometryType="NotAGeometry", srid=4326)


def test_geometry_type_and_srid_default_to_none():
    payload = EmptyCollectionCreate(title="t", columns=[])
    assert payload.geometryType is None
    assert payload.srid is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_empty_collection_schema.py -v`
Expected: FAIL with `ImportError: cannot import name 'EmptyCollectionColumn'`

- [ ] **Step 3: Write minimal implementation**

In `core/app/collections/schemas.py`, add `from typing import Literal` to the existing `from pydantic import BaseModel, Field` import line if not already imported, then append:

```python
class EmptyCollectionColumn(BaseModel):
    # 59 = 63 (limite d'identifiant Postgres) - len('ix__tenant_id') marge la
    # plus courte possible côté nom de colonne ; en pratique une colonne
    # inférée par le wizard ne colle jamais à cette limite.
    name: str = Field(min_length=1, max_length=59)
    sqlType: Literal["text", "integer", "bigint", "double precision", "boolean", "date", "timestamptz"]


class EmptyCollectionCreate(BaseModel):
    title: str = Field(min_length=1)
    columns: list[EmptyCollectionColumn] = Field(default_factory=list)
    geometryType: Literal[
        "Point", "MultiPoint", "LineString", "MultiLineString", "Polygon", "MultiPolygon",
    ] | None = None
    srid: int | None = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_empty_collection_schema.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/schemas.py core/tests/test_empty_collection_schema.py
git commit -m "feat(core): schémas EmptyCollectionCreate avec allowlist de types SQL (SP-14o)"
```

---

## Task 2 : `create_empty_collection` (provisionnement DDL réel)

**Files:**
- Create: `core/app/collections/provisioning.py`
- Test: `core/tests/test_collections_provisioning.py`

**Interfaces:**
- Consumes: `EmptyCollectionColumn` (Task 1), `app.collections.repository.create_collection`, `app.collections.ddl.quote_ident`, `app.collections.introspection.Introspector`.
- Produces: `create_empty_collection(session, *, tenant_id, owner_id, title, columns: list[EmptyCollectionColumn], geometry_type: str | None, srid: int | None, introspect: Introspector, apply_ddl: Callable[[Session, str], None]) -> Collection` — consommé par Task 3.

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_collections_provisioning.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from sqlalchemy import text

from app.collections.ddl import apply_collection_ddl
from app.collections.introspection_pg import introspect_table
from app.collections.provisioning import create_empty_collection
from app.collections.schemas import EmptyCollectionColumn
from app.db import Base, make_session_factory
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def env(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    yield Session, tenant, user
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def test_creates_an_empty_table_with_the_requested_columns_and_no_rows(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s, tenant_id=tenant.id, owner_id=user.id, title="Ma requête",
            columns=[
                EmptyCollectionColumn(name="commune", sqlType="text"),
                EmptyCollectionColumn(name="total", sqlType="integer"),
            ],
            geometry_type=None, srid=None,
            introspect=introspect_table, apply_ddl=apply_collection_ddl,
        )
        s.commit()
        rows = s.execute(text(f"SELECT commune, total FROM public.{col.table_name}")).fetchall()
        assert rows == []
        assert col.geometry_column is None
        assert col.feature_count == 0
        assert col.is_public is False


def test_creates_a_geometry_column_when_geometry_type_is_given(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s, tenant_id=tenant.id, owner_id=user.id, title="Ma requête spatiale",
            columns=[EmptyCollectionColumn(name="commune", sqlType="text")],
            geometry_type="Point", srid=4326,
            introspect=introspect_table, apply_ddl=apply_collection_ddl,
        )
        s.commit()
        assert col.geometry_column == "geom"
        assert col.geometry_type == "Point"
        assert col.srid == 4326


def test_column_names_are_quoted_defensively(env):
    Session, tenant, user = env
    with Session() as s:
        col = create_empty_collection(
            s, tenant_id=tenant.id, owner_id=user.id, title="Colonne réservée",
            columns=[EmptyCollectionColumn(name="select", sqlType="text")],  # mot réservé SQL
            geometry_type=None, srid=None,
            introspect=introspect_table, apply_ddl=apply_collection_ddl,
        )
        s.commit()
        rows = s.execute(text(f'SELECT "select" FROM public.{col.table_name}')).fetchall()
        assert rows == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_provisioning.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'app.collections.provisioning'` (skip silently instead if `CORE_TEST_DATABASE_URL` is unset — expected on this machine per prior session notes; run against a real Postgres to actually verify).

- [ ] **Step 3: Write minimal implementation**

```python
# core/app/collections/provisioning.py
# SPDX-License-Identifier: Apache-2.0
"""Provisionne une collection vide (schéma explicite, aucune ligne) pour un
consommateur qui la remplira lui-même ensuite — premier appelant : l'assistant
de requête visuelle (SP-14o), qui a besoin d'une collection de sortie avant de
pouvoir sauvegarder le pipeline qui l'alimentera. Factorise le motif
CREATE TABLE + apply_collection_ddl + create_collection déjà écrit dans
app.ingestion.importer.run_import (SP-6a), sans insertion de lignes et avec
geometry_type/srid nullables (l'ingestion importe toujours un fichier
géoréférencé ; le cas non-spatial ne lui a jamais été nécessaire)."""
import uuid
from collections.abc import Callable

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.audit.writer import write_audit
from app.collections import repository as collections_repo
from app.collections.ddl import quote_ident
from app.collections.introspection import Introspector
from app.collections.models import Collection
from app.collections.schemas import EmptyCollectionColumn


def create_empty_collection(
    session: Session, *, tenant_id: str, owner_id: str, title: str,
    columns: list[EmptyCollectionColumn], geometry_type: str | None, srid: int | None,
    introspect: Introspector, apply_ddl: Callable[[Session, str], None],
) -> Collection:
    table_name = f"query_{uuid.uuid4().hex[:12]}"
    t = quote_ident(session, table_name)
    col_defs = ", ".join(
        f"{quote_ident(session, c.name)} {c.sqlType}" for c in columns
    )
    create_sql = f"CREATE TABLE public.{t} (id serial PRIMARY KEY, tenant_id text NOT NULL"
    if col_defs:
        create_sql += f", {col_defs}"
    if geometry_type is not None:
        create_sql += f", geom geometry({geometry_type}, {srid or 4326})"
    create_sql += ")"
    session.execute(text(create_sql))

    info = introspect(session, table_name)
    apply_ddl(session, table_name)
    col = collections_repo.create_collection(
        session, tenant_id=tenant_id, owner_id=owner_id, table_name=table_name,
        title=title, description="", is_public=False, pk_column=info.pk_column,
        geometry_column=info.geometry_column, geometry_type=info.geometry_type,
        srid=info.srid, feature_count=0,
    )
    write_audit(
        session, tenant_id=tenant_id, actor_id=owner_id, actor_kind="user",
        action="collection.create", object_type="collection", object_id=col.id,
        payload={"tableName": col.table_name},
    )
    return col
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=postgresql://...  uv run pytest tests/test_collections_provisioning.py -v -m postgis`
Expected: PASS (3 tests) against a real Postgres. If no real Postgres is reachable in this environment, all 3 SKIP with "CORE_TEST_DATABASE_URL non défini" — do not mark this task done on skip alone; note it explicitly as unverified, same discipline as the SP-15d qgis tests (cf. `sp15d-execution-notes` memory).

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/provisioning.py core/tests/test_collections_provisioning.py
git commit -m "feat(core): create_empty_collection, provisionnement DDL réutilisant le motif SP-6a (SP-14o)"
```

---

## Task 3 : route `POST /collections/empty`

**Files:**
- Modify: `core/app/collections/routes.py`
- Test: `core/tests/test_collections_empty_route.py`

**Interfaces:**
- Consumes: `create_empty_collection` (Task 2), `EmptyCollectionCreate` (Task 1), existing `get_introspector`/`get_ddl_applier`/`_collection_json` from `routes.py`.
- Produces: `POST /collections/empty` → 201 `_collection_json` shape (`{id, title, ..., featureCount, canWrite, ...}`) — consommé par le shell (Task 6).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_collections_empty_route.py
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user
    client = TestClient(app)
    yield client
    with pg_engine.begin() as conn:
        conn.execute(text(
            "TRUNCATE items, configs, config_revisions, collections, "
            "audit_log, users, tenants CASCADE"
        ))


def test_creates_a_readable_empty_collection_for_a_regular_non_admin_user(pg_app):
    resp = pg_app.post("/collections/empty", json={
        "title": "Ma requête",
        "columns": [{"name": "commune", "sqlType": "text"}],
        "geometryType": None, "srid": None,
    })
    assert resp.status_code == 201
    body = resp.json()
    assert body["featureCount"] == 0
    assert pg_app.get(f"/collections/{body['id']}").status_code == 200


def test_rejects_an_unknown_sql_type_with_422(pg_app):
    resp = pg_app.post("/collections/empty", json={
        "title": "Injection",
        "columns": [{"name": "x", "sqlType": "text); DROP TABLE users; --"}],
    })
    assert resp.status_code == 422
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_collections_empty_route.py -v -m postgis`
Expected: FAIL with 404 (route doesn't exist yet)

- [ ] **Step 3: Write minimal implementation**

In `core/app/collections/routes.py`, add to the imports:
```python
from app.collections.provisioning import create_empty_collection
from app.collections.schemas import CollectionCreate, CollectionPatch, EmptyCollectionCreate
```
(replace the existing `from app.collections.schemas import CollectionCreate, CollectionPatch` line with the one above.)

Add the route, right after `register_collection` (after line 184):

```python
@router.post("/collections/empty", status_code=201)
def create_empty_collection_route(
    body: EmptyCollectionCreate,
    user=Depends(get_current_user), session: Session = Depends(get_session),
    introspect: Introspector = Depends(get_introspector),
    apply_ddl: Callable = Depends(get_ddl_applier),
):
    col = create_empty_collection(
        session, tenant_id=user.tenant_id, owner_id=user.id, title=body.title,
        columns=body.columns, geometry_type=body.geometryType, srid=body.srid,
        introspect=introspect, apply_ddl=apply_ddl,
    )
    return _collection_json(col, True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_collections_empty_route.py -v -m postgis`
Expected: PASS (2 tests) against a real Postgres; SKIPPED without one — flag as unverified if skipped, same as Task 2.

- [ ] **Step 5: Commit**

```bash
git add core/app/collections/routes.py core/tests/test_collections_empty_route.py
git commit -m "feat(core): route POST /collections/empty, non-admin (SP-14o)"
```

---

## Task 4 : `DatasetPayload.sourcePipelineId` + validation croisée

**Files:**
- Modify: `core/app/configs/schemas.py`
- Modify: `core/app/configs/dataset_validation.py`
- Test: `core/tests/test_dataset_source_pipeline_validation.py`

**Interfaces:**
- Produces: `DatasetPayload.sourcePipelineId: str | None` — consommé par Task 5 (préservation) et le shell (Task 6, 13, 16).

- [ ] **Step 1: Write the failing test**

```python
# core/tests/test_dataset_source_pipeline_validation.py
# SPDX-License-Identifier: Apache-2.0
from fastapi.testclient import TestClient

from app.collections import repository as collections_repo
from app.db import init_db, make_engine, make_session_factory
from app.items import repository as items_repo
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


def _client_and_user(monkeypatch, tmp_path):
    db_url = f"sqlite+pysqlite:///{tmp_path / 'source_pipeline_validation.db'}"
    monkeypatch.setenv("DATABASE_URL", db_url)
    monkeypatch.setenv("CORE_AUTH_MODE", "mock")
    app = create_app()
    engine = make_engine(db_url)
    init_db(engine)
    Session = make_session_factory(engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="mock-sub", username="mockuser",
            email=None, first_name="Mock", last_name="User",
        )
        s.commit()
    client = TestClient(app)
    client.headers["Authorization"] = "Bearer mock:alice"
    return client, tenant, user, Session


def _seed_collection(Session, tenant, user) -> str:
    with Session() as s:
        col = collections_repo.create_collection(
            s, tenant_id=tenant.id, owner_id=user.id, table_name="communes",
            title="Communes", description="", is_public=True, pk_column="id",
            geometry_column=None, geometry_type=None, srid=None,
        )
        s.commit()
        return col.id


def _dataset_body(collection_id: str, source_pipeline_id: str | None) -> dict:
    return {
        "title": "Vue synthèse",
        "config": {
            "kind": "dataset",
            "dataset": {
                "source": "collection",
                "collectionId": collection_id,
                "sourcePipelineId": source_pipeline_id,
            },
        },
    }


def test_create_dataset_rejects_a_nonexistent_source_pipeline(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    resp = client.post("/configs", json=_dataset_body(collection_id, "does-not-exist"))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "pipeline not found"


def test_create_dataset_rejects_a_non_pipeline_source_pipeline_id(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    with Session() as s:
        other_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Not a pipeline",
        )
        s.commit()
        other_item_id = other_item.id
    resp = client.post("/configs", json=_dataset_body(collection_id, other_item_id))
    assert resp.status_code == 422
    assert resp.json()["detail"] == "pipeline not found"


def test_create_dataset_succeeds_with_a_readable_source_pipeline(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    with Session() as s:
        pipeline_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="Ma requête",
        )
        s.commit()
        pipeline_item_id = pipeline_item.id
    resp = client.post("/configs", json=_dataset_body(collection_id, pipeline_item_id))
    assert resp.status_code == 201
    assert resp.json()["kind"] == "dataset"


def test_create_dataset_without_source_pipeline_id_still_works(monkeypatch, tmp_path):
    client, tenant, user, Session = _client_and_user(monkeypatch, tmp_path)
    collection_id = _seed_collection(Session, tenant, user)
    resp = client.post("/configs", json=_dataset_body(collection_id, None))
    assert resp.status_code == 201
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_dataset_source_pipeline_validation.py -v`
Expected: FAIL — `sourcePipelineId` unrecognized by Pydantic model (extra field ignored by default, so the "rejects" tests fail because no 422 is raised) or `ValidationError` if `model_config` forbids extra fields.

- [ ] **Step 3: Write minimal implementation**

In `core/app/configs/schemas.py`, in `DatasetPayload` (after `crossFilterLinks`):

```python
    crossFilterLinks: list[DatasetCrossFilterLink] = Field(default_factory=list)  # SP-14n
    sourcePipelineId: str | None = None  # SP-14o : pipeline qui alimente ce
        # dataset via writer.dataset, si créé par l'assistant de requête
        # visuelle plutôt qu'à la main ; référence validée dans
        # app.configs.dataset_validation, pas ici (un model_validator Pydantic
        # n'a pas accès à la Session/l'utilisateur courant).
```

In `core/app/configs/dataset_validation.py`, update imports and the validation function:

```python
from collections.abc import Callable

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.configs.schemas import BuilderConfig
from app.items import repository as items_repo
from app.sharing.authorization import can
from app.users.models import User

DatasetValidator = Callable[[Session, BuilderConfig, User], None]

_validators: dict[str, DatasetValidator] = {}


def register_dataset_validator(source: str, validator: DatasetValidator) -> None:
    _validators[source] = validator


def _validate_source_pipeline(session: Session, source_pipeline_id: str, *, user: User) -> None:
    facts = items_repo.get_access_facts(session, tenant_id=user.tenant_id, item_id=source_pipeline_id)
    if facts is None or not can(session, user_id=user.id, action="read", item=facts):
        raise HTTPException(status_code=422, detail="pipeline not found")
    target = items_repo.get_item(session, tenant_id=user.tenant_id, item_id=source_pipeline_id)
    assert target is not None  # get_access_facts just confirmed it exists
    if target.resourceType != "pipeline":
        raise HTTPException(status_code=422, detail="pipeline not found")


def validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    payload = config.dataset
    assert payload is not None
    validator = _validators.get(payload.source)
    assert validator is not None, f"no dataset validator registered for source={payload.source!r}"
    validator(session, config, user)
    if payload.sourcePipelineId is not None:
        _validate_source_pipeline(session, payload.sourcePipelineId, user=user)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_dataset_source_pipeline_validation.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/schemas.py core/app/configs/dataset_validation.py core/tests/test_dataset_source_pipeline_validation.py
git commit -m "feat(core): DatasetPayload.sourcePipelineId + validation croisée (SP-14o)"
```

---

## Task 5 : préserver `sourcePipelineId` dans `_write_dataset`

**Files:**
- Modify: `core/app/pipelines/runtime.py:551-555`
- Test: `core/tests/test_pipeline_runtime.py` (nouveau test ajouté après `test_writer_dataset_updates_existing_dataset_preserving_metadata`, ligne ~637)

**Interfaces:**
- Consumes: `DatasetPayload.sourcePipelineId` (Task 4).

**Bug réel trouvé en préparant ce plan** : `_write_dataset`'s update-in-place branch reconstruit un `DatasetPayload` frais depuis `current.columns`/`current.timeField`/`current.reactsToExtent`/`current.crossFilterLinks` — sans `sourcePipelineId`. Sans ce correctif, le bouton « Modifier la requête » disparaîtrait dès le premier run planifié (cron SP-15h) ou manuel après la création initiale, puisque `sourcePipelineId` serait remis à `None` à chaque écriture.

- [ ] **Step 1: Write the failing test**

Add to `core/tests/test_pipeline_runtime.py`, right after `test_writer_dataset_updates_existing_dataset_preserving_metadata` (before the `@pytest.mark.postgis` on the next test at line 640):

```python
@pytest.mark.postgis
def test_writer_dataset_update_preserves_source_pipeline_id(pg_engine, monkeypatch, tmp_path):
    from app.configs import repository as configs_repo
    from app.configs.schemas import BuilderConfig, DatasetPayload
    from app.items import repository as items_repo

    Base.metadata.create_all(pg_engine)
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant = get_or_create_default_tenant(s)
        user = get_or_create_user(
            s, tenant_id=tenant.id, oidc_sub="a", username="alice",
            email=None, first_name="", last_name="",
        )
        s.execute(text(
            "INSERT INTO collections (id, tenant_id, owner_id, table_name, title, "
            "description, pk_column, geometry_column, is_public, editable, "
            "created_at, updated_at) "
            "VALUES ('villes_out', :t, :o, 'villes_out', 'Villes out', "
            "'', 'id', 'geometry', false, true, now(), now())"
        ), {"t": tenant.id, "o": user.id})
        s.execute(text(
            "CREATE TABLE villes_out (id SERIAL PRIMARY KEY, tenant_id VARCHAR, "
            "region VARCHAR, pop INTEGER, geometry geometry(Point, 4326))"
        ))
        apply_collection_ddl(s, "villes_out")

        pipeline_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="pipeline", title="Ma requête",
        )
        existing_item = items_repo.create_item(
            s, tenant_id=tenant.id, owner_id=user.id, resource_type="dataset", title="Ancien dataset",
        )
        existing_config = configs_repo.create_config(
            s, BuilderConfig(kind="dataset", dataset=DatasetPayload(
                source="collection", collectionId="villes_out_old",
                sourcePipelineId=pipeline_item.id,
            )),
            item_id=existing_item.id, tenant_id=tenant.id,
        )
        s.commit()

        _write_partition(tmp_path, tenant_id=tenant.id, rows=[_row(1, "Nord", 10, x=1.0, y=45.0)])
        monkeypatch.setattr(runtime, "_table_info_for_collection", lambda session, collection_id: _table_info_for(collection_id))
        monkeypatch.setattr(
            runtime, "_require_readable_collection_id",
            lambda session, *, tenant_id, user, collection_id: collection_id,
        )

        payload = _dataset_pipeline_payload(
            reader_collection="villes", writer_collection="villes_out", dataset_id=existing_item.id,
        )
        runtime.run_pipeline(
            s, payload=payload, tenant_id=tenant.id, user=user,
            endpoint_url="http://localhost:9000", access_key="x", secret_key="y",
            base_uri=str(tmp_path),
        )
        s.commit()

        updated = configs_repo.get_config(s, existing_config.id)
        assert updated.config.dataset.sourcePipelineId == pipeline_item.id  # préservé, pas effacé

    with pg_engine.begin() as conn:
        conn.execute(text(
            "DROP TABLE villes_out; "
            "TRUNCATE items, configs, config_revisions, collections, audit_log, users, tenants CASCADE"
        ))
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py::test_writer_dataset_update_preserves_source_pipeline_id -v -m postgis`
Expected: FAIL — `assert updated.config.dataset.sourcePipelineId == pipeline_item.id` fails because it's `None`.

- [ ] **Step 3: Write minimal implementation**

In `core/app/pipelines/runtime.py`, in `_write_dataset` (around line 551), change:

```python
        updated_dataset = DatasetPayload(
            source="collection", collectionId=p.collectionId,
            columns=current.columns, timeField=current.timeField,
            reactsToExtent=current.reactsToExtent, crossFilterLinks=current.crossFilterLinks,
        )
```
to:
```python
        updated_dataset = DatasetPayload(
            source="collection", collectionId=p.collectionId,
            columns=current.columns, timeField=current.timeField,
            reactsToExtent=current.reactsToExtent, crossFilterLinks=current.crossFilterLinks,
            sourcePipelineId=current.sourcePipelineId,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_runtime.py -v -m postgis`
Expected: PASS (all tests in file, including the new one and the pre-existing ones — confirms no regression)

- [ ] **Step 5: Commit**

```bash
git add core/app/pipelines/runtime.py core/tests/test_pipeline_runtime.py
git commit -m "fix(core): writer.dataset préserve sourcePipelineId sur update (SP-14o)"
```

---

## Task 6 : types shell + `ItemClient.createEmptyCollection` + round-trip `sourcePipelineId`

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (ajout de cas ; fichier existant probable — si absent, créer)

**Interfaces:**
- Produces: `EmptyCollectionColumn{name,sqlType}`, `CreateEmptyCollectionInput{title,columns,geometryType,srid}`, `ItemClient.createEmptyCollection(input): Promise<{id:string}>`, `DatasetConfig.sourcePipelineId?: string | null` — consommés par Task 9, 13, 16.

- [ ] **Step 1: Write the failing test**

```ts
// shell/src/api/itemClient.test.ts (ajouter ce bloc — adapter l'import du serveur MSW existant si le fichier existe déjà)
import { describe, expect, test } from "vitest";
import { http, HttpResponse } from "msw";
import { setupServer } from "msw/node";
import { createItemClient } from "./itemClient";

const server = setupServer();

describe("createEmptyCollection", () => {
  test("posts to /collections/empty and returns the created id", async () => {
    server.use(
      http.post("https://core.test/collections/empty", async ({ request }) => {
        const body = await request.json();
        expect(body).toEqual({
          title: "Ma requête", columns: [{ name: "commune", sqlType: "text" }],
          geometryType: null, srid: null,
        });
        return HttpResponse.json({ id: "query_abc123" }, { status: 201 });
      }),
    );
    server.listen();
    try {
      const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
      const result = await client.createEmptyCollection({
        title: "Ma requête", columns: [{ name: "commune", sqlType: "text" }],
        geometryType: null, srid: null,
      });
      expect(result).toEqual({ id: "query_abc123" });
    } finally {
      server.close();
    }
  });
});
```

(If `shell/src/api/itemClient.test.ts` already exists with its own `server`/lifecycle setup, add this `describe` block to it instead of creating a duplicate MSW server — check the file first.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- itemClient -t createEmptyCollection`
Expected: FAIL — `client.createEmptyCollection is not a function`

- [ ] **Step 3: Write minimal implementation**

In `shell/src/api/types.ts`, add near `CollectionSchema` (after line 103):

```ts
export type EmptyCollectionColumn = { name: string; sqlType: string };

export type CreateEmptyCollectionInput = {
  title: string;
  columns: EmptyCollectionColumn[];
  geometryType: string | null;
  srid: number | null;
};
```

Extend the `ItemClient` interface with:
```ts
  createEmptyCollection(input: CreateEmptyCollectionInput): Promise<{ id: string }>;
```

Extend both `DatasetConfig` union branches with `sourcePipelineId?: string | null;` (added after `crossFilterLinks?: CrossFilterLink[];` on each branch).

In `shell/src/api/itemClient.ts`, add the method to the `createItemClient` factory object:

```ts
async createEmptyCollection(input: CreateEmptyCollectionInput): Promise<{ id: string }> {
  const data = await request<{ id: string }>("POST", "/collections/empty", {
    title: input.title, columns: input.columns,
    geometryType: input.geometryType, srid: input.srid,
  });
  return { id: data.id };
},
```

In `getDatasetConfig`, add `sourcePipelineId: resolved.sourcePipelineId ?? null` to both branches of the returned object literal (mirroring how `timeField`/`reactsToExtent`/`crossFilterLinks` are already forwarded from `resolved`).

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- itemClient`
Expected: PASS (all itemClient tests, including the new one)

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient.createEmptyCollection + round-trip sourcePipelineId (SP-14o)"
```

---

## Task 7 : `inferOutputColumns` (inférence de schéma)

**Files:**
- Create: `shell/src/builder/visualQuery/inferSchema.ts`
- Test: `shell/src/builder/visualQuery/inferSchema.test.ts`

**Interfaces:**
- Consumes: `CollectionSchema`/`CollectionSchemaField`/`CollectionFieldType` (déjà existants, `shell/src/api/types.ts`).
- Produces: `SummaryConfig`, `MetricConfig`, `JoinConfig`, `InferredColumn`, `InferredSchema`, `inferOutputColumns(base, join, joinedSchema, summary): InferredSchema` — consommé par Task 9, 13.

- [ ] **Step 1: Write the failing test**

```ts
// shell/src/builder/visualQuery/inferSchema.test.ts
import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { inferOutputColumns } from "./inferSchema";

const BASE: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
    { name: "signale_le", type: "datetime", required: false },
  ],
};

const JOINED: CollectionSchema = {
  collection: "communes", pk: "id", geometry: null,
  fields: [
    { name: "commune", type: "string", required: true },  // colonne de jointure
    { name: "population", type: "integer", required: false },
    { name: "gravite", type: "string", required: false },  // collision de nom avec BASE, type différent
  ],
};

describe("inferOutputColumns", () => {
  test("passthrough : reprend toutes les colonnes de base avec la géométrie de base", () => {
    const result = inferOutputColumns(BASE, null, null, null);
    expect(result.columns).toEqual([
      { name: "commune", sqlType: "text" },
      { name: "gravite", sqlType: "integer" },
      { name: "signale_le", sqlType: "timestamptz" },
    ]);
    expect(result.geometryType).toBe("Point");
    expect(result.srid).toBe(4326);
  });

  test("jointure : renomme la colonne jointe en collision, jamais la colonne de jointure elle-même", () => {
    const join = { collectionId: "communes", on: "commune", how: "inner" as const };
    const result = inferOutputColumns(BASE, join, JOINED, null);
    const names = result.columns.map((c) => c.name);
    expect(names).toContain("commune");       // colonne de jointure, une seule fois
    expect(names).toContain("population");    // pas de collision, nom inchangé
    expect(names).toContain("joined_gravite"); // collision avec BASE.gravite, renommée
    expect(names).not.toContain("gravite");    // le renommage remplace, pas ajoute
  });

  test("résumé : count -> integer, sum/avg -> double precision, aucune géométrie", () => {
    const summary = {
      groupBy: ["commune"],
      metrics: [
        { alias: "nb", function: "count" as const, sourceColumn: null },
        { alias: "total_gravite", function: "sum" as const, sourceColumn: "gravite" },
      ],
    };
    const result = inferOutputColumns(BASE, null, null, summary);
    expect(result.columns).toEqual([
      { name: "commune", sqlType: "text" },
      { name: "nb", sqlType: "integer" },
      { name: "total_gravite", sqlType: "double precision" },
    ]);
    expect(result.geometryType).toBeNull();
  });

  test("colonne de type unsupported est exclue silencieusement", () => {
    const withUnsupported: CollectionSchema = {
      ...BASE,
      fields: [...BASE.fields, { name: "brut", type: "unsupported", required: false }],
    };
    const result = inferOutputColumns(withUnsupported, null, null, null);
    expect(result.columns.map((c) => c.name)).not.toContain("brut");
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- inferSchema`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
// shell/src/builder/visualQuery/inferSchema.ts
import type { CollectionFieldType, CollectionSchema } from "../../api/types";

export type JoinConfig = { collectionId: string; on: string; how: "inner" | "left" };
export type MetricFunction = "count" | "sum" | "avg" | "min" | "max";
export type MetricConfig = { alias: string; function: MetricFunction; sourceColumn: string | null };
export type SummaryConfig = { groupBy: string[]; metrics: MetricConfig[] };

export type InferredColumn = { name: string; sqlType: string };
export type InferredSchema = { columns: InferredColumn[]; geometryType: string | null; srid: number | null };

// Aligné sur les 7 types SQL acceptés par EmptyCollectionColumn.sqlType côté
// cœur (core/app/collections/schemas.py) — "unsupported" n'a pas d'équivalent
// SQL sûr, la colonne est simplement exclue de la sortie.
const FIELD_TYPE_TO_SQL: Record<CollectionFieldType, string | null> = {
  string: "text", integer: "integer", number: "double precision",
  boolean: "boolean", date: "date", datetime: "timestamptz",
  enum: "text", unsupported: null,
};

function sqlTypeOf(schema: CollectionSchema, columnName: string): string {
  const field = schema.fields.find((f) => f.name === columnName);
  return (field && FIELD_TYPE_TO_SQL[field.type]) || "double precision";
}

export function inferOutputColumns(
  base: CollectionSchema, join: JoinConfig | null, joinedSchema: CollectionSchema | null,
  summary: SummaryConfig | null,
): InferredSchema {
  if (summary) {
    const columns: InferredColumn[] = [];
    for (const name of summary.groupBy) {
      const sqlType = sqlTypeOf(base, name);
      columns.push({ name, sqlType });
    }
    for (const metric of summary.metrics) {
      const sqlType =
        metric.function === "count" ? "integer"
        : metric.function === "sum" || metric.function === "avg" ? "double precision"
        : sqlTypeOf(base, metric.sourceColumn ?? "");
      columns.push({ name: metric.alias, sqlType });
    }
    // Un dataset résumé n'a pas de géométrie propre en v1 : un agrégat groupé
    // ne correspond à aucune géométrie individuelle sans jointure de retour
    // vers une couche de contour, hors périmètre de cet assistant.
    return { columns, geometryType: null, srid: null };
  }

  if (join && joinedSchema) {
    const baseNames = new Set(base.fields.map((f) => f.name));
    const columns: InferredColumn[] = [];
    for (const f of base.fields) {
      const sqlType = FIELD_TYPE_TO_SQL[f.type];
      if (sqlType) columns.push({ name: f.name, sqlType });
    }
    for (const f of joinedSchema.fields) {
      if (f.name === join.on) continue; // dédupliquée par JOIN ... USING, déjà comptée côté base
      const sqlType = FIELD_TYPE_TO_SQL[f.type];
      if (!sqlType) continue;
      const outputName = baseNames.has(f.name) ? `joined_${f.name}` : f.name;
      columns.push({ name: outputName, sqlType });
    }
    return { columns, geometryType: base.geometry?.type ?? null, srid: base.geometry?.srid ?? null };
  }

  const columns: InferredColumn[] = [];
  for (const f of base.fields) {
    const sqlType = FIELD_TYPE_TO_SQL[f.type];
    if (sqlType) columns.push({ name: f.name, sqlType });
  }
  return { columns, geometryType: base.geometry?.type ?? null, srid: base.geometry?.srid ?? null };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- inferSchema`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/inferSchema.ts shell/src/builder/visualQuery/inferSchema.test.ts
git commit -m "feat(shell): inferOutputColumns, inférence de schéma côté client (SP-14o)"
```

---

## Task 8 : compilation/décompilation du filtre (SQL scalaire borné)

**Files:**
- Create: `shell/src/builder/visualQuery/compileFilter.ts`
- Test: `shell/src/builder/visualQuery/compileFilter.test.ts`

**Interfaces:**
- Consumes: `CollectionSchema` (types.ts).
- Produces: `FilterOperator`, `FilterRow`, `quoteIdent`, `quoteSqlLiteral`, `compileFilterRowsToSql(rows, schema): string`, `decompileSqlToFilterRows(expr): FilterRow[] | null` — consommés par Task 9, 10.

- [ ] **Step 1: Write the failing test**

```ts
// shell/src/builder/visualQuery/compileFilter.test.ts
import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { compileFilterRowsToSql, decompileSqlToFilterRows } from "./compileFilter";

const SCHEMA: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [
    { name: "commune", type: "string", required: true },
    { name: "gravite", type: "integer", required: false },
    { name: "actif", type: "boolean", required: false },
  ],
};

describe("compileFilterRowsToSql", () => {
  test("une ligne = une comparaison quotée", () => {
    const sql = compileFilterRowsToSql([{ column: "gravite", operator: "gt", value: "3" }], SCHEMA);
    expect(sql).toBe('"gravite" > 3');
  });

  test("plusieurs lignes combinées en ET", () => {
    const sql = compileFilterRowsToSql(
      [
        { column: "commune", operator: "eq", value: "Paris" },
        { column: "actif", operator: "eq", value: "true" },
      ],
      SCHEMA,
    );
    expect(sql).toBe('"commune" = \'Paris\' AND "actif" = TRUE');
  });

  test("échappe les apostrophes dans une valeur texte", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "eq", value: "L'Île" }], SCHEMA);
    expect(sql).toBe('"commune" = \'L\'\'Île\'');
  });

  test("contains produit un LIKE encadré de %", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "contains", value: "par" }], SCHEMA);
    expect(sql).toBe('"commune" LIKE \'%par%\'');
  });
});

describe("decompileSqlToFilterRows", () => {
  test("round-trip sur une expression simple", () => {
    const original = [{ column: "gravite", operator: "gt" as const, value: "3" }];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("round-trip sur plusieurs lignes ET", () => {
    const original = [
      { column: "commune", operator: "eq" as const, value: "Paris" },
      { column: "actif", operator: "eq" as const, value: "true" },
    ];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("round-trip sur contains", () => {
    const original = [{ column: "commune", operator: "contains" as const, value: "par" }];
    expect(decompileSqlToFilterRows(compileFilterRowsToSql(original, SCHEMA))).toEqual(original);
  });

  test("chaîne vide -> aucune ligne", () => {
    expect(decompileSqlToFilterRows("")).toEqual([]);
  });

  test("forme non reconnue -> null (repli attendu vers le canvas complet)", () => {
    expect(decompileSqlToFilterRows("length(\"commune\") > 3")).toBeNull();
  });

  test("limite documentée : une valeur contenant littéralement ' AND ' casse le round-trip proprement (renvoie null, pas un crash)", () => {
    const sql = compileFilterRowsToSql([{ column: "commune", operator: "eq", value: "ROCK AND ROLL" }], SCHEMA);
    // Ambigu avec un split naïf sur " AND " — comportement documenté et
    // accepté : renvoie null (repli vers le canvas), jamais une exception ni
    // un résultat silencieusement faux.
    expect(decompileSqlToFilterRows(sql)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- compileFilter`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
// shell/src/builder/visualQuery/compileFilter.ts
import type { CollectionFieldType, CollectionSchema } from "../../api/types";

export type FilterOperator = "eq" | "neq" | "gt" | "gte" | "lt" | "lte" | "contains";
export type FilterRow = { column: string; operator: FilterOperator; value: string };

export function quoteIdent(name: string): string {
  return `"${name.replace(/"/g, '""')}"`;
}

export function quoteSqlLiteral(value: string): string {
  return `'${value.replace(/'/g, "''")}'`;
}

const OPERATOR_TO_SQL: Record<FilterOperator, string> = {
  eq: "=", neq: "!=", gt: ">", gte: ">=", lt: "<", lte: "<=", contains: "LIKE",
};
const SQL_TO_OPERATOR: Record<string, FilterOperator> = {
  "=": "eq", "!=": "neq", ">": "gt", ">=": "gte", "<": "lt", "<=": "lte", LIKE: "contains",
};

function formatValue(row: FilterRow, fieldType: CollectionFieldType): string {
  if (row.operator === "contains") return quoteSqlLiteral(`%${row.value}%`);
  switch (fieldType) {
    case "integer":
    case "number":
      return row.value; // le formulaire (Task 10) ne laisse saisir que des chiffres pour ces types
    case "boolean":
      return row.value === "true" ? "TRUE" : "FALSE";
    default:
      return quoteSqlLiteral(row.value);
  }
}

export function compileFilterRowsToSql(rows: FilterRow[], schema: CollectionSchema): string {
  return rows
    .map((row) => {
      const field = schema.fields.find((f) => f.name === row.column);
      const fieldType = field?.type ?? "string";
      return `${quoteIdent(row.column)} ${OPERATOR_TO_SQL[row.operator]} ${formatValue(row, fieldType)}`;
    })
    .join(" AND ");
}

// Best-effort : ne comprend que la forme exacte produite par
// compileFilterRowsToSql. Toute forme non reconnue (y compris une valeur
// texte contenant littéralement " AND ", cf. test dédié) renvoie null — le
// point d'appel (Task 9/13) traite null comme "pipeline modifié à la main,
// repli vers le canvas complet", un comportement voulu, pas un bug.
export function decompileSqlToFilterRows(expr: string): FilterRow[] | null {
  if (expr === "") return [];
  const clauses = expr.split(" AND ");
  const rows: FilterRow[] = [];
  for (const clause of clauses) {
    const match = clause.match(/^"((?:[^"]|"")+)" (=|!=|>=|<=|>|<|LIKE) (.+)$/);
    if (!match) return null;
    const [, rawColumn, sqlOp, rawValue] = match;
    const column = rawColumn.replace(/""/g, '"');
    const operator = SQL_TO_OPERATOR[sqlOp];
    let value: string;
    if (operator === "contains") {
      const litMatch = rawValue.match(/^'%(.*)%'$/);
      if (!litMatch) return null;
      value = litMatch[1].replace(/''/g, "'");
    } else if (rawValue === "TRUE" || rawValue === "FALSE") {
      value = rawValue === "TRUE" ? "true" : "false";
    } else if (rawValue.startsWith("'")) {
      const litMatch = rawValue.match(/^'(.*)'$/);
      if (!litMatch) return null;
      value = litMatch[1].replace(/''/g, "'");
    } else {
      value = rawValue; // numérique, non quoté
    }
    rows.push({ column, operator, value });
  }
  return rows;
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- compileFilter`
Expected: PASS (10 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/compileFilter.ts shell/src/builder/visualQuery/compileFilter.test.ts
git commit -m "feat(shell): compilation/décompilation du filtre en SQL scalaire borné (SP-14o)"
```

---

## Task 9 : compilation/décompilation du pipeline complet

**Files:**
- Create: `shell/src/builder/visualQuery/compilePipeline.ts`
- Test: `shell/src/builder/visualQuery/compilePipeline.test.ts`

**Interfaces:**
- Consumes: `PipelineNode`/`PipelineEdge`/`PipelinePayload`/`PipelineRefreshPolicy` (types.ts), `genNodeId`/`genEdgeId` (`../pipeline/graphOps`), `FilterRow`/`compileFilterRowsToSql`/`decompileSqlToFilterRows`/`quoteIdent` (Task 8), `JoinConfig`/`SummaryConfig`/`MetricConfig` (Task 7).
- Produces: `VisualQueryState`, `compileVisualQueryToPipeline(state, baseSchema, joinedSchema, outputCollectionId, datasetItemId): PipelinePayload`, `decompilePipelineToWizardState(pipeline): {baseCollectionId, filters, join, summary} | null` — consommés par Task 13.

- [ ] **Step 1: Write the failing test**

```ts
// shell/src/builder/visualQuery/compilePipeline.test.ts
import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { compileVisualQueryToPipeline, decompilePipelineToWizardState, VisualQueryState } from "./compilePipeline";

const BASE: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "gravite", type: "integer", required: false }],
};
const JOINED: CollectionSchema = {
  collection: "communes", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "population", type: "integer", required: false }],
};

function baseState(overrides: Partial<VisualQueryState> = {}): VisualQueryState {
  return {
    title: "Ma requête", baseCollectionId: "incidents",
    filters: [], join: null, summary: null, refreshPolicy: null,
    ...overrides,
  };
}

describe("compileVisualQueryToPipeline", () => {
  test("filtre seul : reader -> filter -> writer.dataset", () => {
    const state = baseState({ filters: [{ column: "gravite", operator: "gt", value: "3" }] });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "transform.filter", "writer.dataset"]);
    const writer = pipeline.nodes.find((n) => n.op === "writer.dataset")!;
    expect(writer.params).toEqual({ collectionId: "query_out", datasetId: "dataset-1" });
    expect(pipeline.edges).toHaveLength(2);
    expect(pipeline.edges.every((e) => e.role == null)).toBe(true);
  });

  test("aucune étape optionnelle : reader -> writer.dataset directement", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "writer.dataset"]);
  });

  test("jointure : deux readers, un select implicite sur la branche jointe, arête secondaire", () => {
    const state = baseState({ join: { collectionId: "communes", on: "commune", how: "inner" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, JOINED, "query_out", "dataset-1");
    const ops = pipeline.nodes.map((n) => n.op);
    expect(ops).toEqual(["reader.collection", "reader.collection", "transform.select", "transform.join", "writer.dataset"]);
    const joinNode = pipeline.nodes.find((n) => n.op === "transform.join")!;
    expect(joinNode.params).toEqual({ on: "commune", how: "inner" });
    const secondaryEdge = pipeline.edges.find((e) => e.role === "secondary")!;
    const selectNode = pipeline.nodes.find((n) => n.op === "transform.select")!;
    expect(secondaryEdge.from).toBe(selectNode.id);
    expect(secondaryEdge.to).toBe(joinNode.id);
    // La colonne de jointure est gardée telle quelle (null = pas de renommage) ;
    // "population" ne collide pas avec BASE, gardée telle quelle aussi.
    expect(selectNode.params).toEqual({ columns: { commune: null, population: null } });
  });

  test("jointure avec collision de nom hors colonne de jointure : renommage joined_<nom>", () => {
    const joinedWithCollision: CollectionSchema = {
      ...JOINED,
      fields: [...JOINED.fields, { name: "gravite", type: "string", required: false }],
    };
    const state = baseState({ join: { collectionId: "communes", on: "commune", how: "left" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, joinedWithCollision, "query_out", "dataset-1");
    const selectNode = pipeline.nodes.find((n) => n.op === "transform.select")!;
    expect(selectNode.params).toEqual({
      columns: { commune: null, population: null, gravite: "joined_gravite" },
    });
  });

  test("résumé : aggregate avec count(*) et sum(colonne quotée)", () => {
    const state = baseState({
      summary: {
        groupBy: ["commune"],
        metrics: [
          { alias: "nb", function: "count", sourceColumn: null },
          { alias: "total", function: "sum", sourceColumn: "gravite" },
        ],
      },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    const aggNode = pipeline.nodes.find((n) => n.op === "transform.aggregate")!;
    expect(aggNode.params).toEqual({
      groupBy: ["commune"], metrics: { nb: "count(*)", total: 'sum("gravite")' },
    });
  });

  test("propage refreshPolicy quand fournie", () => {
    const state = baseState({ refreshPolicy: { enabled: true, cron: "0 6 * * *" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    expect(pipeline.refreshPolicy).toEqual({ enabled: true, cron: "0 6 * * *" });
  });
});

describe("decompilePipelineToWizardState", () => {
  test("round-trip sur filtre + jointure + résumé", () => {
    const state = baseState({
      filters: [{ column: "gravite", operator: "gt", value: "3" }],
      join: { collectionId: "communes", on: "commune", how: "inner" },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, JOINED, "query_out", "dataset-1");
    const decompiled = decompilePipelineToWizardState(pipeline);
    expect(decompiled).toEqual({
      baseCollectionId: "incidents",
      filters: [{ column: "gravite", operator: "gt", value: "3" }],
      join: { collectionId: "communes", on: "commune", how: "inner" },
      summary: null,
    });
  });

  test("forme non reconnue (nœud supplémentaire ajouté à la main) -> null", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    pipeline.nodes.push({ id: "extra", kind: "transform", op: "transform.derive", x: 0, y: 0, params: { column: "x", expr: "1" } });
    pipeline.edges.push({ id: "e-extra", from: pipeline.nodes[0].id, to: "extra" });
    expect(decompilePipelineToWizardState(pipeline)).toBeNull();
  });

  test("plusieurs writers -> null", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    pipeline.nodes.push({ id: "w2", kind: "writer", op: "writer.export", x: 0, y: 0, params: { format: "csv", key: "x" } });
    expect(decompilePipelineToWizardState(pipeline)).toBeNull();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- compilePipeline`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```ts
// shell/src/builder/visualQuery/compilePipeline.ts
import type { PipelineEdge, PipelineNode, PipelinePayload, PipelineRefreshPolicy, CollectionSchema } from "../../api/types";
import { genEdgeId, genNodeId } from "../pipeline/graphOps";
import { FilterRow, compileFilterRowsToSql, decompileSqlToFilterRows, quoteIdent } from "./compileFilter";
import { JoinConfig, MetricConfig, SummaryConfig } from "./inferSchema";

export type VisualQueryState = {
  title: string;
  baseCollectionId: string;
  filters: FilterRow[];
  join: JoinConfig | null;
  summary: SummaryConfig | null;
  refreshPolicy: PipelineRefreshPolicy | null;
};

function metricExpr(metric: MetricConfig): string {
  if (metric.function === "count") return "count(*)";
  return `${metric.function}(${quoteIdent(metric.sourceColumn!)})`;
}

export function compileVisualQueryToPipeline(
  state: VisualQueryState, baseSchema: CollectionSchema, joinedSchema: CollectionSchema | null,
  outputCollectionId: string, datasetItemId: string,
): PipelinePayload {
  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];
  let x = 0;

  function addNode(kind: PipelineNode["kind"], op: string, params: Record<string, unknown>): PipelineNode {
    const n: PipelineNode = { id: genNodeId(), kind, op, x: (x += 200), y: 0, params };
    nodes.push(n);
    return n;
  }
  function addEdge(from: PipelineNode, to: PipelineNode, role?: "secondary") {
    edges.push({ id: genEdgeId(), from: from.id, to: to.id, role: role ?? null });
  }

  const baseReader = addNode("reader", "reader.collection", { collectionId: state.baseCollectionId });
  let mainTail = baseReader;

  if (state.filters.length > 0) {
    const filterNode = addNode("transform", "transform.filter", {
      expr: compileFilterRowsToSql(state.filters, baseSchema),
    });
    addEdge(mainTail, filterNode);
    mainTail = filterNode;
  }

  if (state.join && joinedSchema) {
    const joinedReader = addNode("reader", "reader.collection", { collectionId: state.join.collectionId });
    const baseNames = new Set(baseSchema.fields.map((f) => f.name));
    const joinedColumns: Record<string, string | null> = {};
    for (const f of joinedSchema.fields) {
      if (f.name === state.join.on) { joinedColumns[f.name] = null; continue; }
      joinedColumns[f.name] = baseNames.has(f.name) ? `joined_${f.name}` : null;
    }
    const joinedSelect = addNode("transform", "transform.select", { columns: joinedColumns });
    addEdge(joinedReader, joinedSelect);

    const joinNode = addNode("transform", "transform.join", { on: state.join.on, how: state.join.how });
    addEdge(mainTail, joinNode);
    addEdge(joinedSelect, joinNode, "secondary");
    mainTail = joinNode;
  }

  if (state.summary) {
    const metrics: Record<string, string> = {};
    for (const metric of state.summary.metrics) metrics[metric.alias] = metricExpr(metric);
    const aggregateNode = addNode("transform", "transform.aggregate", {
      groupBy: state.summary.groupBy, metrics,
    });
    addEdge(mainTail, aggregateNode);
    mainTail = aggregateNode;
  }

  const writerNode = addNode("writer", "writer.dataset", {
    collectionId: outputCollectionId, datasetId: datasetItemId,
  });
  addEdge(mainTail, writerNode);

  return { nodes, edges, refreshPolicy: state.refreshPolicy };
}

function decompileMetrics(metrics: Record<string, string>): MetricConfig[] | null {
  const result: MetricConfig[] = [];
  for (const [alias, expr] of Object.entries(metrics)) {
    if (expr === "count(*)") { result.push({ alias, function: "count", sourceColumn: null }); continue; }
    const match = expr.match(/^(sum|avg|min|max)\("((?:[^"]|"")+)"\)$/);
    if (!match) return null;
    result.push({
      alias, function: match[1] as MetricConfig["function"], sourceColumn: match[2].replace(/""/g, '"'),
    });
  }
  return result;
}

// Best-effort, reconnaît uniquement la forme exacte produite par
// compileVisualQueryToPipeline ci-dessus : un seul writer.dataset, au plus
// deux readers, une chaîne primaire sans branchement non reconnu. Toute
// autre forme (pipeline retouché à la main dans le canvas complet) renvoie
// null — le point d'appel (Task 13) traite ça comme un repli attendu vers
// PipelineBuilderPage, pas une erreur.
export function decompilePipelineToWizardState(pipeline: PipelinePayload): {
  baseCollectionId: string; filters: FilterRow[]; join: JoinConfig | null; summary: SummaryConfig | null;
} | null {
  const byId = new Map(pipeline.nodes.map((n) => [n.id, n]));
  const readerNodes = pipeline.nodes.filter((n) => n.kind === "reader");
  const writerNodes = pipeline.nodes.filter((n) => n.kind === "writer");
  if (writerNodes.length !== 1 || writerNodes[0].op !== "writer.dataset") return null;
  if (readerNodes.length < 1 || readerNodes.length > 2) return null;
  if (readerNodes.some((n) => n.op !== "reader.collection")) return null;

  const primaryReader = readerNodes.find(
    (r) => !pipeline.edges.some((e) => e.from === r.id && e.role === "secondary"),
  );
  if (!primaryReader) return null;

  let currentId = primaryReader.id;
  const visited = new Set<string>([currentId]);
  let filters: FilterRow[] = [];
  let join: JoinConfig | null = null;
  let summary: SummaryConfig | null = null;

  while (true) {
    const outgoing = pipeline.edges.filter((e) => e.from === currentId && e.role !== "secondary");
    if (outgoing.length !== 1) return null;
    const next = byId.get(outgoing[0].to);
    if (!next) return null;
    if (next.id === writerNodes[0].id) break;
    if (visited.has(next.id)) return null;
    visited.add(next.id);

    if (next.op === "transform.filter" && filters.length === 0 && !join && !summary) {
      const decompiled = decompileSqlToFilterRows(String(next.params.expr ?? ""));
      if (decompiled === null) return null;
      filters = decompiled;
      currentId = next.id;
      continue;
    }
    if (next.op === "transform.join" && !join && !summary) {
      const secondaryEdge = pipeline.edges.find((e) => e.to === next.id && e.role === "secondary");
      const joinedReader = readerNodes.find((r) => r.id !== primaryReader.id);
      if (!secondaryEdge || !joinedReader) return null;
      const selectEdge = pipeline.edges.find((e) => e.from === joinedReader.id);
      const selectNode = selectEdge ? byId.get(selectEdge.to) : undefined;
      if (!selectNode || selectNode.op !== "transform.select" || selectEdge!.to !== secondaryEdge.from) return null;
      join = {
        collectionId: String(joinedReader.params.collectionId),
        on: String(next.params.on),
        how: next.params.how === "left" ? "left" : "inner",
      };
      currentId = next.id;
      continue;
    }
    if (next.op === "transform.aggregate" && !summary) {
      const params = next.params as { groupBy?: string[]; metrics?: Record<string, string> };
      const metrics = decompileMetrics(params.metrics ?? {});
      if (metrics === null) return null;
      summary = { groupBy: params.groupBy ?? [], metrics };
      currentId = next.id;
      continue;
    }
    return null;
  }

  return { baseCollectionId: String(primaryReader.params.collectionId), filters, join, summary };
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- compilePipeline`
Expected: PASS (9 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/compilePipeline.ts shell/src/builder/visualQuery/compilePipeline.test.ts
git commit -m "feat(shell): compilation/décompilation wizard <-> PipelinePayload (SP-14o)"
```

---

## Task 10 : `QueryFilterBuilder`

**Files:**
- Create: `shell/src/builder/visualQuery/QueryFilterBuilder.tsx`
- Test: `shell/src/builder/visualQuery/QueryFilterBuilder.test.tsx`

**Interfaces:**
- Consumes: `FilterRow`/`FilterOperator` (Task 8), `CollectionSchema` (types.ts).
- Produces: `QueryFilterBuilder({schema, rows, onChange}): JSX.Element` — consommé par Task 13.

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/builder/visualQuery/QueryFilterBuilder.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QueryFilterBuilder } from "./QueryFilterBuilder";

const SCHEMA: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "gravite", type: "integer", required: false }],
};

describe("QueryFilterBuilder", () => {
  test("ajoute une ligne de filtre et notifie le parent", async () => {
    const onChange = vi.fn();
    render(<QueryFilterBuilder schema={SCHEMA} rows={[]} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter un filtre" }));
    expect(onChange).toHaveBeenCalledWith([{ column: "commune", operator: "eq", value: "" }]);
  });

  test("modifier la colonne d'une ligne existante notifie le parent avec la ligne mise à jour", async () => {
    const onChange = vi.fn();
    render(
      <QueryFilterBuilder
        schema={SCHEMA}
        rows={[{ column: "commune", operator: "eq", value: "" }]}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Colonne du filtre 1"), "gravite");
    expect(onChange).toHaveBeenCalledWith([{ column: "gravite", operator: "eq", value: "" }]);
  });

  test("supprime une ligne", async () => {
    const onChange = vi.fn();
    render(
      <QueryFilterBuilder
        schema={SCHEMA}
        rows={[{ column: "commune", operator: "eq", value: "" }]}
        onChange={onChange}
      />,
    );
    await userEvent.click(screen.getByRole("button", { name: "Supprimer le filtre 1" }));
    expect(onChange).toHaveBeenCalledWith([]);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- QueryFilterBuilder`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```tsx
// shell/src/builder/visualQuery/QueryFilterBuilder.tsx
import type { CollectionSchema } from "../../api/types";
import { FilterOperator, FilterRow } from "./compileFilter";
import { Button } from "../../ui/button";

const OPERATOR_LABELS: Record<FilterOperator, string> = {
  eq: "égal à", neq: "différent de", gt: "supérieur à", gte: "supérieur ou égal à",
  lt: "inférieur à", lte: "inférieur ou égal à", contains: "contient",
};

export function QueryFilterBuilder({
  schema, rows, onChange,
}: { schema: CollectionSchema; rows: FilterRow[]; onChange: (rows: FilterRow[]) => void }) {
  function updateRow(index: number, patch: Partial<FilterRow>) {
    onChange(rows.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  }
  function removeRow(index: number) {
    onChange(rows.filter((_, i) => i !== index));
  }
  function addRow() {
    onChange([...rows, { column: schema.fields[0]?.name ?? "", operator: "eq", value: "" }]);
  }

  return (
    <div className="flex flex-col gap-2">
      {rows.map((row, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            aria-label={`Colonne du filtre ${i + 1}`}
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={row.column}
            onChange={(e) => updateRow(i, { column: e.target.value })}
          >
            {schema.fields.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
          </select>
          <select
            aria-label={`Opérateur du filtre ${i + 1}`}
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={row.operator}
            onChange={(e) => updateRow(i, { operator: e.target.value as FilterOperator })}
          >
            {Object.entries(OPERATOR_LABELS).map(([op, label]) => (
              <option key={op} value={op}>{label}</option>
            ))}
          </select>
          <input
            aria-label={`Valeur du filtre ${i + 1}`}
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={row.value}
            onChange={(e) => updateRow(i, { value: e.target.value })}
          />
          <button
            type="button"
            aria-label={`Supprimer le filtre ${i + 1}`}
            className="text-xs text-red-600"
            onClick={() => removeRow(i)}
          >
            Supprimer
          </button>
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={addRow}>
        Ajouter un filtre
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- QueryFilterBuilder`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/QueryFilterBuilder.tsx shell/src/builder/visualQuery/QueryFilterBuilder.test.tsx
git commit -m "feat(shell): composant QueryFilterBuilder (SP-14o)"
```

---

## Task 11 : `QueryJoinPicker`

**Files:**
- Create: `shell/src/builder/visualQuery/QueryJoinPicker.tsx`
- Test: `shell/src/builder/visualQuery/QueryJoinPicker.test.tsx`

**Interfaces:**
- Consumes: `JoinConfig` (Task 7), `CollectionSchema`.
- Produces: `QueryJoinPicker({baseSchema, joinedSchema, collections, value, onChange}): JSX.Element` — consommé par Task 13.

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/builder/visualQuery/QueryJoinPicker.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QueryJoinPicker } from "./QueryJoinPicker";

const BASE: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }],
};
const JOINED: CollectionSchema = {
  collection: "communes", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "population", type: "integer", required: false }],
};

describe("QueryJoinPicker", () => {
  test("propose seulement les colonnes communes aux deux collections comme colonne de jointure", async () => {
    const onChange = vi.fn();
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={JOINED}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "", how: "inner" }}
        onChange={onChange}
      />,
    );
    const options = screen.getAllByRole("option", { name: /commune$/ });
    expect(options).toHaveLength(1); // "commune" est la seule colonne présente des deux côtés
  });

  test("affiche un message si aucune colonne n'est commune", () => {
    const disjointJoined: CollectionSchema = { ...JOINED, fields: [{ name: "population", type: "integer", required: false }] };
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={disjointJoined}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "", how: "inner" }}
        onChange={vi.fn()}
      />,
    );
    expect(screen.getByText(/Aucune colonne commune/)).toBeInTheDocument();
  });

  test("change how notifie le parent", async () => {
    const onChange = vi.fn();
    render(
      <QueryJoinPicker
        baseSchema={BASE} joinedSchema={JOINED}
        collections={[{ id: "communes", title: "Communes" }]}
        value={{ collectionId: "communes", on: "commune", how: "inner" }}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Type de jointure"), "left");
    expect(onChange).toHaveBeenCalledWith({ collectionId: "communes", on: "commune", how: "left" });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- QueryJoinPicker`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```tsx
// shell/src/builder/visualQuery/QueryJoinPicker.tsx
import type { CollectionSchema } from "../../api/types";
import { JoinConfig } from "./inferSchema";

export function QueryJoinPicker({
  baseSchema, joinedSchema, collections, value, onChange,
}: {
  baseSchema: CollectionSchema; joinedSchema: CollectionSchema | null;
  collections: { id: string; title: string }[];
  value: JoinConfig; onChange: (next: JoinConfig) => void;
}) {
  const baseNames = new Set(baseSchema.fields.map((f) => f.name));
  const commonColumns = joinedSchema ? joinedSchema.fields.filter((f) => baseNames.has(f.name)) : [];

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-xs">
        Collection à joindre
        <select
          aria-label="Collection à joindre"
          className="h-8 rounded border border-slate-300 px-2 text-xs"
          value={value.collectionId}
          onChange={(e) => onChange({ ...value, collectionId: e.target.value, on: "" })}
        >
          <option value="">Choisir…</option>
          {collections.map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </label>
      {joinedSchema && commonColumns.length === 0 && (
        <p className="text-xs text-red-600">
          Aucune colonne commune entre les deux collections — la jointure est impossible.
        </p>
      )}
      {commonColumns.length > 0 && (
        <label className="flex flex-col gap-1 text-xs">
          Colonne de jointure
          <select
            aria-label="Colonne de jointure"
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={value.on}
            onChange={(e) => onChange({ ...value, on: e.target.value })}
          >
            <option value="">Choisir…</option>
            {commonColumns.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs">
        Type de jointure
        <select
          aria-label="Type de jointure"
          className="h-8 rounded border border-slate-300 px-2 text-xs"
          value={value.how}
          onChange={(e) => onChange({ ...value, how: e.target.value as "inner" | "left" })}
        >
          <option value="inner">Garder seulement les correspondances</option>
          <option value="left">Garder toutes les lignes de base</option>
        </select>
      </label>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- QueryJoinPicker`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/QueryJoinPicker.tsx shell/src/builder/visualQuery/QueryJoinPicker.test.tsx
git commit -m "feat(shell): composant QueryJoinPicker (SP-14o)"
```

---

## Task 12 : `QuerySummaryBuilder`

**Files:**
- Create: `shell/src/builder/visualQuery/QuerySummaryBuilder.tsx`
- Test: `shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx`

**Interfaces:**
- Consumes: `SummaryConfig`/`MetricConfig`/`MetricFunction` (Task 7), `CollectionSchema`.
- Produces: `QuerySummaryBuilder({schema, value, onChange}): JSX.Element` — consommé par Task 13.

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { CollectionSchema } from "../../api/types";
import { QuerySummaryBuilder } from "./QuerySummaryBuilder";

const SCHEMA: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "gravite", type: "integer", required: false }],
};

describe("QuerySummaryBuilder", () => {
  test("ajouter une métrique count ne demande pas de colonne source", async () => {
    const onChange = vi.fn();
    render(<QuerySummaryBuilder schema={SCHEMA} value={{ groupBy: [], metrics: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByRole("button", { name: "Ajouter une métrique" }));
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [], metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null }],
    });
  });

  test("changer la fonction en sum exige alors une colonne source", async () => {
    const onChange = vi.fn();
    render(
      <QuerySummaryBuilder
        schema={SCHEMA}
        value={{ groupBy: [], metrics: [{ alias: "metrique_1", function: "count", sourceColumn: null }] }}
        onChange={onChange}
      />,
    );
    await userEvent.selectOptions(screen.getByLabelText("Fonction de la métrique 1"), "sum");
    expect(onChange).toHaveBeenCalledWith({
      groupBy: [], metrics: [{ alias: "metrique_1", function: "sum", sourceColumn: "gravite" }],
    });
  });

  test("cocher une colonne de regroupement l'ajoute à groupBy", async () => {
    const onChange = vi.fn();
    render(<QuerySummaryBuilder schema={SCHEMA} value={{ groupBy: [], metrics: [] }} onChange={onChange} />);
    await userEvent.click(screen.getByLabelText("Regrouper par commune"));
    expect(onChange).toHaveBeenCalledWith({ groupBy: ["commune"], metrics: [] });
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- QuerySummaryBuilder`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```tsx
// shell/src/builder/visualQuery/QuerySummaryBuilder.tsx
import type { CollectionSchema } from "../../api/types";
import { MetricConfig, MetricFunction, SummaryConfig } from "./inferSchema";
import { Button } from "../../ui/button";

const FUNCTION_LABELS: Record<MetricFunction, string> = {
  count: "Compter", sum: "Somme", avg: "Moyenne", min: "Minimum", max: "Maximum",
};

export function QuerySummaryBuilder({
  schema, value, onChange,
}: { schema: CollectionSchema; value: SummaryConfig; onChange: (next: SummaryConfig) => void }) {
  function toggleGroupBy(name: string, checked: boolean) {
    onChange({
      ...value,
      groupBy: checked ? [...value.groupBy, name] : value.groupBy.filter((g) => g !== name),
    });
  }
  function updateMetric(index: number, patch: Partial<MetricConfig>) {
    const metrics = value.metrics.map((m, i) => {
      if (i !== index) return m;
      const next = { ...m, ...patch };
      if (next.function === "count") next.sourceColumn = null;
      else if (next.sourceColumn === null) next.sourceColumn = schema.fields[0]?.name ?? null;
      return next;
    });
    onChange({ ...value, metrics });
  }
  function addMetric() {
    onChange({
      ...value,
      metrics: [...value.metrics, { alias: `metrique_${value.metrics.length + 1}`, function: "count", sourceColumn: null }],
    });
  }

  return (
    <div className="flex flex-col gap-2">
      <p className="text-xs font-medium text-slate-500">Regrouper par</p>
      {schema.fields.map((f) => (
        <label key={f.name} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label={`Regrouper par ${f.name}`}
            checked={value.groupBy.includes(f.name)}
            onChange={(e) => toggleGroupBy(f.name, e.target.checked)}
          />
          {f.name}
        </label>
      ))}
      <p className="text-xs font-medium text-slate-500">Métriques</p>
      {value.metrics.map((metric, i) => (
        <div key={i} className="flex items-center gap-2">
          <select
            aria-label={`Fonction de la métrique ${i + 1}`}
            className="h-8 rounded border border-slate-300 px-2 text-xs"
            value={metric.function}
            onChange={(e) => updateMetric(i, { function: e.target.value as MetricFunction })}
          >
            {Object.entries(FUNCTION_LABELS).map(([fn, label]) => <option key={fn} value={fn}>{label}</option>)}
          </select>
          {metric.function !== "count" && (
            <select
              aria-label={`Colonne de la métrique ${i + 1}`}
              className="h-8 rounded border border-slate-300 px-2 text-xs"
              value={metric.sourceColumn ?? ""}
              onChange={(e) => updateMetric(i, { sourceColumn: e.target.value })}
            >
              {schema.fields.map((f) => <option key={f.name} value={f.name}>{f.name}</option>)}
            </select>
          )}
        </div>
      ))}
      <Button type="button" size="sm" variant="outline" onClick={addMetric}>
        Ajouter une métrique
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- QuerySummaryBuilder`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/visualQuery/QuerySummaryBuilder.tsx shell/src/builder/visualQuery/QuerySummaryBuilder.test.tsx
git commit -m "feat(shell): composant QuerySummaryBuilder (SP-14o)"
```

---

## Task 13 : `VisualQueryWizardPage` (orchestration)

**Files:**
- Create: `shell/src/pages/VisualQueryWizardPage.tsx`
- Test: `shell/src/pages/VisualQueryWizardPage.test.tsx`

**Interfaces:**
- Consumes: tout ce qui précède (Task 6-12), `useCollectionsAdmin`/`usePipelineOps` (hooks existants), `PipelineScheduleEditor`/`PipelineRunPanel` (existants), `useAuth`.
- Produces: `VisualQueryWizardPage({pipelinePk, initialTitle}: {pipelinePk: string | null; initialTitle?: string}): JSX.Element` — consommé par Task 14 (routes.tsx).

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/pages/VisualQueryWizardPage.test.tsx
import { describe, expect, test, vi } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { VisualQueryWizardPage } from "./VisualQueryWizardPage";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false, isAuthenticated: true, username: "alice",
    getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(), error: null,
  }),
}));

const BASE_SCHEMA = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string" as const, required: true }],
};

function renderWizard(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listCollections: () => Promise.resolve([{ id: "incidents", title: "Incidents" }]),
    getCollectionSchema: () => Promise.resolve(BASE_SCHEMA),
    createEmptyCollection: vi.fn().mockResolvedValue({ id: "query_out" }),
    createDatasetItem: vi.fn().mockResolvedValue({ pk: "dataset-1", resourceType: "dataset", title: "Ma requête", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-1", isPublished: false }),
    createPipelineItem: vi.fn().mockResolvedValue({ pk: "pipeline-1", resourceType: "pipeline", title: "Requête — Ma requête", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-2", isPublished: false }),
    saveDatasetConfig: vi.fn().mockResolvedValue(undefined),
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([{ id: "run-1", status: "succeeded", startedAt: null, finishedAt: null, error: null, nodeStats: {} }]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/datasets/visual-query/new"]}>
          <Routes>
            <Route path="/datasets/visual-query/new" element={<VisualQueryWizardPage pipelinePk={null} initialTitle="Ma requête" />} />
            <Route path="/datasets/:pk/edit" element={<div>dataset-edit-page</div>} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

describe("VisualQueryWizardPage", () => {
  test("crée la collection de sortie, le dataset, le pipeline, les relie, lance le run, puis redirige", async () => {
    const client = renderWizard();
    await userEvent.selectOptions(await screen.findByLabelText("Collection de base"), "incidents");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));

    await waitFor(() => expect(client.createEmptyCollection).toHaveBeenCalled());
    expect(client.createDatasetItem).toHaveBeenCalledWith(
      expect.objectContaining({ source: "collection", collectionId: "query_out" }),
    );
    expect(client.createPipelineItem).toHaveBeenCalledWith(
      expect.objectContaining({ owner: "alice" }),
    );
    expect(client.saveDatasetConfig).toHaveBeenCalledWith(
      "dataset-1", expect.objectContaining({ sourcePipelineId: "pipeline-1" }),
    );
    expect(client.runPipeline).toHaveBeenCalledWith("pipeline-1");
    await waitFor(() => expect(screen.getByText("dataset-edit-page")).toBeInTheDocument());
  });

  test("affiche une erreur si le provisionnement échoue, sans créer le dataset ni le pipeline", async () => {
    const client = renderWizard({ createEmptyCollection: vi.fn().mockRejectedValue(new Error("quota dépassé")) });
    await userEvent.selectOptions(await screen.findByLabelText("Collection de base"), "incidents");
    await userEvent.click(screen.getByRole("button", { name: "Créer" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("quota dépassé");
    expect(client.createDatasetItem).not.toHaveBeenCalled();
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- VisualQueryWizardPage`
Expected: FAIL — module doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

```tsx
// shell/src/pages/VisualQueryWizardPage.tsx
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import { useCollectionsAdmin, usePipelineConfig } from "../api/hooks";
import type { CollectionSchema, PipelineRefreshPolicy } from "../api/types";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { QueryFilterBuilder } from "../builder/visualQuery/QueryFilterBuilder";
import { QueryJoinPicker } from "../builder/visualQuery/QueryJoinPicker";
import { QuerySummaryBuilder } from "../builder/visualQuery/QuerySummaryBuilder";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { inferOutputColumns } from "../builder/visualQuery/inferSchema";
import { FilterRow } from "../builder/visualQuery/compileFilter";
import { JoinConfig, SummaryConfig } from "../builder/visualQuery/inferSchema";
import { VisualQueryState, compileVisualQueryToPipeline, decompilePipelineToWizardState } from "../builder/visualQuery/compilePipeline";

export function VisualQueryWizardPage({ pipelinePk, initialTitle }: { pipelinePk: string | null; initialTitle?: string }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const collectionsQuery = useCollectionsAdmin({ enabled: true });
  const existingPipelineQuery = usePipelineConfig(pipelinePk ?? "", { enabled: pipelinePk !== null });

  const [title, setTitle] = useState(initialTitle ?? "");
  const [baseCollectionId, setBaseCollectionId] = useState("");
  const [filters, setFilters] = useState<FilterRow[]>([]);
  const [join, setJoin] = useState<JoinConfig | null>(null);
  const [summary, setSummary] = useState<SummaryConfig | null>(null);
  const [refreshPolicy, setRefreshPolicy] = useState<PipelineRefreshPolicy | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [createdPipelinePk, setCreatedPipelinePk] = useState<string | null>(null);
  const [createdDatasetPk, setCreatedDatasetPk] = useState<string | null>(null);
  const [unrecognizedShape, setUnrecognizedShape] = useState(false);

  const baseSchemaQuery = useQuery({
    queryKey: ["collection-schema", baseCollectionId],
    queryFn: () => client.getCollectionSchema(baseCollectionId),
    enabled: Boolean(baseCollectionId),
  });
  const joinedSchemaQuery = useQuery({
    queryKey: ["collection-schema", join?.collectionId],
    queryFn: () => client.getCollectionSchema(join!.collectionId),
    enabled: Boolean(join?.collectionId),
  });

  useEffect(() => {
    if (pipelinePk === null || !existingPipelineQuery.data) return;
    const decompiled = decompilePipelineToWizardState(existingPipelineQuery.data);
    if (decompiled === null) { setUnrecognizedShape(true); return; }
    setBaseCollectionId(decompiled.baseCollectionId);
    setFilters(decompiled.filters);
    setJoin(decompiled.join);
    setSummary(decompiled.summary);
    setRefreshPolicy(existingPipelineQuery.data.refreshPolicy ?? null);
  }, [pipelinePk, existingPipelineQuery.data]);

  if (pipelinePk !== null && unrecognizedShape) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Cette requête a été modifiée dans l'éditeur avancé et ne peut plus être ouverte dans
        l'assistant. <a className="underline" href={`/pipelines/${pipelinePk}/edit`}>Ouvrir dans l'éditeur avancé</a>.
      </p>
    );
  }

  const baseSchema: CollectionSchema | undefined = baseSchemaQuery.data;

  async function handleCreate() {
    if (!baseSchema) return;
    setError(null);
    setSubmitting(true);
    try {
      const state: VisualQueryState = { title, baseCollectionId, filters, join, summary, refreshPolicy };
      const inferred = inferOutputColumns(baseSchema, join, joinedSchemaQuery.data ?? null, summary);
      const { id: outputCollectionId } = await client.createEmptyCollection({
        title: `${title} (données)`,
        columns: inferred.columns.map((c) => ({ name: c.name, sqlType: c.sqlType })),
        geometryType: inferred.geometryType, srid: inferred.srid,
      });
      const datasetItem = await client.createDatasetItem({
        title, owner: username ?? "", source: "collection", collectionId: outputCollectionId,
      });
      const pipeline = compileVisualQueryToPipeline(
        state, baseSchema, joinedSchemaQuery.data ?? null, outputCollectionId, datasetItem.pk,
      );
      const pipelineItem = await client.createPipelineItem({
        title: `Requête — ${title}`, owner: username ?? "", pipeline,
      });
      await client.saveDatasetConfig(datasetItem.pk, {
        source: "collection", collectionId: outputCollectionId, columns: {},
        sourcePipelineId: pipelineItem.pk,
      });
      await client.runPipeline(pipelineItem.pk);
      setCreatedPipelinePk(pipelineItem.pk);
      setCreatedDatasetPk(datasetItem.pk);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Échec de la création.");
    } finally {
      setSubmitting(false);
    }
  }

  if (createdPipelinePk && createdDatasetPk) {
    return (
      <div className="flex flex-col gap-2 p-4">
        <p>Exécution de la requête…</p>
        <PipelineRunPanel
          pipelineId={createdPipelinePk}
          onLatestRunChange={(run) => {
            if (run?.status === "succeeded") navigate(`/datasets/${createdDatasetPk}/edit`);
          }}
        />
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-xl font-semibold">Nouvelle requête visuelle</h2>
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Collection de base
        <select
          aria-label="Collection de base"
          className="h-9 rounded-md border border-slate-300 px-3 text-sm"
          value={baseCollectionId}
          onChange={(e) => setBaseCollectionId(e.target.value)}
        >
          <option value="">Choisir…</option>
          {(collectionsQuery.data ?? []).map((c) => <option key={c.id} value={c.id}>{c.title}</option>)}
        </select>
      </label>
      {baseSchema && (
        <>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Filtrer</p>
            <QueryFilterBuilder schema={baseSchema} rows={filters} onChange={setFilters} />
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Joindre</p>
            {join ? (
              <QueryJoinPicker
                baseSchema={baseSchema} joinedSchema={joinedSchemaQuery.data ?? null}
                collections={collectionsQuery.data ?? []} value={join} onChange={setJoin}
              />
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => setJoin({ collectionId: "", on: "", how: "inner" })}>
                Ajouter une jointure
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Résumer</p>
            {summary ? (
              <QuerySummaryBuilder schema={baseSchema} value={summary} onChange={setSummary} />
            ) : (
              <Button type="button" size="sm" variant="outline" onClick={() => setSummary({ groupBy: [], metrics: [] })}>
                Ajouter un résumé
              </Button>
            )}
          </div>
          <div>
            <p className="mb-1 text-xs font-medium text-slate-500">Planifier</p>
            <PipelineScheduleEditor value={refreshPolicy} onChange={setRefreshPolicy} />
          </div>
        </>
      )}
      {error && <p role="alert" className="text-sm text-red-600">{error}</p>}
      <Button size="sm" className="w-fit" disabled={submitting || !title.trim() || !baseCollectionId} onClick={handleCreate}>
        Créer
      </Button>
    </div>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- VisualQueryWizardPage`
Expected: PASS (2 tests) — adjust selectors/mocks as needed based on actual `Input`/`Button` component rendering (check via `npm run test` output, not by guessing further).

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/VisualQueryWizardPage.tsx shell/src/pages/VisualQueryWizardPage.test.tsx
git commit -m "feat(shell): VisualQueryWizardPage, orchestration de bout en bout (SP-14o)"
```

---

## Task 14 : câblage des routes

**Files:**
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `VisualQueryWizardPage` (Task 13).

- [ ] **Step 1: Write the failing test**

Pas de test dédié (câblage pur, déjà couvert par le test E2E de Task 17 et le test Vitest de Task 13 qui rend directement le composant sans passer par `routes.tsx`). Vérifier manuellement après l'étape 3 :

Run: `cd shell && npm run build`
Expected: FAIL avant l'étape 3 si `VisualQueryWizardPage` n'est pas encore importé dans `routes.tsx` alors qu'un test l'attend déjà en E2E — sinon ce build passe déjà ; dans ce cas, passer directement à l'étape 3 puis vérifier que le build passe toujours (pas de régression TypeScript).

- [ ] **Step 2: (n/a — pas de test à faire échouer, câblage pur)**

- [ ] **Step 3: Write minimal implementation**

In `shell/src/shell/routes.tsx`, add near `PipelineNewRoute`/`PipelineEditRoute`:

```tsx
function VisualQueryWizardNewRoute() {
  const location = useLocation();
  const title = (location.state as { title?: string } | null)?.title;
  return <VisualQueryWizardPage pipelinePk={null} initialTitle={title} />;
}

function VisualQueryWizardEditRoute() {
  const { pipelinePk } = useParams();
  return <VisualQueryWizardPage pipelinePk={pipelinePk!} />;
}
```

Add the import at the top: `import { VisualQueryWizardPage } from "../pages/VisualQueryWizardPage";`

In `AppRoutes()`, add right after the `/pipelines/:pk/edit` route:

```tsx
        <Route path="/datasets/visual-query/new" element={<VisualQueryWizardNewRoute />} />
        <Route path="/datasets/visual-query/:pipelinePk/edit" element={<VisualQueryWizardEditRoute />} />
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run build`
Expected: PASS (tsc --noEmit + vite build succeed)

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/routes.tsx
git commit -m "feat(shell): route l'assistant de requête visuelle (SP-14o)"
```

---

## Task 15 : entrée dans `NewItemButton`

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx`

**Interfaces:**
- Consumes: route `/datasets/visual-query/new` (Task 14).

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/shell/NewItemButton.test.tsx (ajouter ce test au fichier existant)
test("selecting « Dataset par requête visuelle » only asks for a title, and navigates to /datasets/visual-query/new with the title in route state, without calling the create API", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false, etlEnabled: true })),
  );
  let configPosted = false;
  server.use(
    http.post("https://core.test/configs", () => { configPosted = true; return HttpResponse.json({ id: "cfg-x", kind: "app", itemId: "x" }); }),
  );
  function VisualQueryNewProbe() {
    const location = useLocation();
    const state = location.state as { title?: string } | null;
    return <div>visual-query-new-{state?.title ?? ""}</div>;
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/datasets/visual-query/new" element={<VisualQueryNewProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "visual-query");
  await userEvent.type(screen.getByLabelText("Titre"), "Ma requête");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("visual-query-new-Ma requête")).toBeInTheDocument();
  expect(configPosted).toBe(false);
});

test("the visual-query option is hidden when etlEnabled is false", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false, etlEnabled: false })),
  );
  render(<Harness><NewItemButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await waitFor(() => expect(screen.queryByRole("option", { name: "Dataset par requête visuelle" })).not.toBeInTheDocument());
});
```

(Adapt imports — this file already has `server`, `Harness`, `useLocation`, `MemoryRouter`, `QueryClient`/`QueryClientProvider`, `ItemClientProvider`, `createItemClient` in scope per the existing "Pipeline" test above it; mirror those exactly.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- NewItemButton`
Expected: FAIL — `visual-query` option doesn't exist, `userEvent.selectOptions` throws.

- [ ] **Step 3: Write minimal implementation**

In `shell/src/shell/NewItemButton.tsx`:

```tsx
type Kind = "app" | "dashboard" | "map" | "site" | "dataset" | "pipeline" | "visual-query";
```

In the `<select>`, right after the `dataset` option:
```tsx
              {etlEnabled && <option value="visual-query">Dataset par requête visuelle</option>}
```

In `submit()`, right after the existing `if (kind === "pipeline") { ... return; }` block:
```tsx
    if (kind === "visual-query") {
      close();
      navigate("/datasets/visual-query/new", { state: { title: clean } });
      return;
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- NewItemButton`
Expected: PASS (all NewItemButton tests, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx
git commit -m "feat(shell): option « Dataset par requête visuelle » dans NewItemButton (SP-14o)"
```

---

## Task 16 : bouton « Modifier la requête » dans `DatasetEditPage`

**Files:**
- Modify: `shell/src/pages/DatasetEditPage.tsx`
- Test: `shell/src/pages/DatasetEditPage.test.tsx`

**Interfaces:**
- Consumes: `DatasetConfig.sourcePipelineId` (Task 6), route `/datasets/visual-query/:pipelinePk/edit` (Task 14).

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/pages/DatasetEditPage.test.tsx (ajouter ce test au fichier existant, adapter le patron de rendu déjà en place dans ce fichier)
test("shows a « Modifier la requête » button when sourcePipelineId is set, linking to the wizard's edit route", async () => {
  // adapter au patron de rendu déjà utilisé par les autres tests de ce fichier
  // (mock ItemClient avec getDatasetConfig renvoyant sourcePipelineId: "pipeline-1"),
  // MemoryRouter avec une route probe sur "/datasets/visual-query/:pipelinePk/edit"
  // pour vérifier la navigation.
  expect(await screen.findByRole("button", { name: "Modifier la requête" })).toBeInTheDocument();
});

test("hides the button when sourcePipelineId is absent (dataset created by hand)", async () => {
  // même patron, getDatasetConfig sans sourcePipelineId (ou null)
  expect(screen.queryByRole("button", { name: "Modifier la requête" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- DatasetEditPage`
Expected: FAIL — button doesn't exist yet.

- [ ] **Step 3: Write minimal implementation**

In `shell/src/pages/DatasetEditPage.tsx`, add the import: `import { useNavigate } from "react-router-dom";` and `const navigate = useNavigate();` inside the component body. Then, right after the `<AlertRuleEditor .../>` line, add:

```tsx
      {draft.sourcePipelineId && (
        <Button
          type="button" size="sm" variant="outline" className="w-fit"
          onClick={() => navigate(`/datasets/visual-query/${draft.sourcePipelineId}/edit`)}
        >
          Modifier la requête
        </Button>
      )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- DatasetEditPage`
Expected: PASS (all DatasetEditPage tests, including the 2 new ones)

- [ ] **Step 5: Commit**

```bash
git add shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx
git commit -m "feat(shell): bouton « Modifier la requête » sur DatasetEditPage (SP-14o)"
```

---

## Task 17 : E2E Playwright

**Files:**
- Create: `shell/e2e/visual-query.spec.ts`

**Interfaces:**
- Consumes: l'application complète (toutes les tâches précédentes), stack `docker compose` avec `CORE_ETL_ENABLED=true`.

- [ ] **Step 1: Write the failing test**

```ts
// shell/e2e/visual-query.spec.ts
import { expect, test } from "@playwright/test";

test("crée un dataset par requête visuelle avec filtre, puis le rouvre pour vérifier la requête", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Type").selectOption("visual-query");
  await page.getByLabel("Titre").fill("E2E requête visuelle");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/datasets\/visual-query\/new/);
  await page.getByLabel("Collection de base").selectOption({ label: /./ }); // première collection seedée disponible
  await page.getByRole("button", { name: "Ajouter un filtre" }).click();
  await page.getByLabel("Valeur du filtre 1").fill("1");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page.getByText("Exécution de la requête…")).toBeVisible();
  await expect(page).toHaveURL(/\/datasets\/[^/]+\/edit/, { timeout: 30_000 });
  await expect(page.getByRole("button", { name: "Modifier la requête" })).toBeVisible();

  await page.getByRole("button", { name: "Modifier la requête" }).click();
  await expect(page).toHaveURL(/\/datasets\/visual-query\/.+\/edit/);
  await expect(page.getByLabel("Valeur du filtre 1")).toHaveValue("1");
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- visual-query`
Expected: FAIL — no such flow exists yet before Tasks 1-16 land; run this only after all prior tasks are merged, as the final verification step of the branch.

- [ ] **Step 3: (implementation already done by Tasks 1-16 — this step confirms wiring end-to-end)**

Adjust selectors above based on actual DOM once run against the real stack (`docker compose up -d` with `CORE_ETL_ENABLED=true` set in `.env`, per CLAUDE.md commands) — the exact collection seeded for E2E fixtures should be checked against `shell/e2e/` existing fixtures/seed data before finalizing the `selectOption` call.

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && VITE_AUTH_MODE=mock npm run e2e -- visual-query`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/visual-query.spec.ts
git commit -m "test(e2e): parcours complet de la requête visuelle (SP-14o)"
```

---

## Self-Review (effectuée pendant la rédaction de ce plan)

**Couverture du spec** : les 4 sections de la spec (mécanique matérialisée, provisionnement, modèle de données/flux, composants UI/tests) ont chacune une ou plusieurs tâches. Point non couvert par une tâche dédiée : le hors-périmètre explicite de la spec (jointures chaînées, tri serveur, requête live, refactor ingestion) — correctement absent, car hors périmètre.

**Corrections trouvées en préparant ce plan (au-delà de la correction CEL→SQL déjà reportée au spec, commit `5718f64`)** :
1. `transform.join` utilise `JOIN ... USING (col)` — une seule colonne de jointure au nom partagé, pas deux colonnes distinctes par côté (corrigé dans la spec et dans ce plan).
2. Le renommage anti-collision doit se faire **avant** la jointure sur la branche jointe (un `transform.select` entre le `reader.collection` joint et l'arête secondaire), jamais après — `transform.select` est une projection, pas un rename in-place ; une collision non résolue avant `SELECT * ... JOIN ... USING` produirait deux colonnes de sortie au même nom, ambiguës pour tout consommateur derrière (Task 9).
3. `_write_dataset` efface silencieusement `sourcePipelineId` à chaque re-run (update-in-place) — bug réel trouvé en lisant `runtime.py`, corrigé en Task 5 avec un test de régression avant même que le champ existe en usage réel.
4. Le pré-créer le dataset (avec `datasetId` connu) puis créer le pipeline en second, plutôt que laisser `writer.dataset` créer le dataset et devoir retrouver son id après un job asynchrone — la spec décrivait l'ordre inverse ; ce plan choisit l'ordre qui évite un problème réel (« comment récupérer l'id d'un item créé par un job procrastinate qu'on ne peut interroger que par son `runId`, jamais par l'id d'item qu'il a créé »).

**Cohérence des types** : `PipelineNode`/`PipelineEdge` (Task 9) utilisent exactement les noms de champs confirmés dans `shell/src/api/types.ts` (`from`, pas `from_` — l'alias Pydantic côté cœur n'a pas d'équivalent côté TS). `EmptyCollectionColumn.sqlType` (Task 1, cœur) et `InferredColumn.sqlType`/`EmptyCollectionColumn` (Task 7, shell) partagent exactement les 7 valeurs autorisées. `MetricFunction`/`MetricConfig`/`JoinConfig`/`SummaryConfig` définis une seule fois (Task 7, `inferSchema.ts`) et réimportés partout ailleurs (Task 9, 12, 13) — aucune redéfinition divergente.

**Point d'incertitude assumé, pas un trou du plan** : Task 13's Step 4 note explicitement qu'un ajustement des sélecteurs de test peut être nécessaire une fois le rendu réel observé (patron `Input`/`Button` du repo non entièrement vérifié caractère pour caractère) — traité par l'exécutant au moment du TDD, pas deviné à l'avance.
