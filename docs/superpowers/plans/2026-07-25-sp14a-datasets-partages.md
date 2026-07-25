# SP-14a — Datasets partagés Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make "dataset" a platform object — a named, cataloged, shared, permissioned reference to a collection (arbitrage A28) — immediately consumable by the existing `chart`/`table`/`indicator`/`datasetCard` widgets, without a new pipeline or duplicated schema.

**Architecture:** Reuse the existing `Item` + `BuilderConfig(kind=...)` pattern exactly as SP-13a did for `"site"`: a new `kind: "dataset"` with a `dataset: DatasetPayload | None` sibling field (mirroring `map: MapConfig | None`). No new core module, no new `/datasets/*` routes — the generic `/configs` CRUD is reused as-is. The schema is never duplicated: it's derived at read time from the collection (`table_info_to_schema`, already used by SP-3/SP-4) and merged in the shell with the dataset's column overrides. On the shell, `DataSource` gains an optional `datasetId` field that `queryDataSource`/`featuresUrl` resolve to a `collectionId` before delegating, unchanged, to the existing `features`/`statistics` code paths.

**Tech Stack:** Python/FastAPI + SQLAlchemy + Pydantic (core), React/TypeScript + react-query + Vitest + Playwright (shell).

## Global Constraints

- `resource_type`/`kind` value is exactly `"dataset"` (not `"Dataset"`, not `"shared-dataset"`).
- No new core module (`core/app/datasets/` does **not** get created) — reuse `app/configs/` and `app/items/`.
- No new dedicated `/datasets/*` API route — only the generic `/configs`, `/configs/by-item/{pk}`, `/items?type=dataset` endpoints, exactly as used by `app`/`dashboard`/`map`/`site`.
- The dataset never stores a duplicated schema — only column *overrides* (`columns: dict[str, DatasetColumnMeta]`); the base schema is always re-derived from `table_info_to_schema` / `GET /collections/{id}/schema`.
- `config.version` stays `1`; `datasetId` on `DataSource` and `"dataset"` as a new `BuilderConfig.kind` are purely additive — the 13 existing Playwright E2E specs must stay green unmodified.
- UI/doc wording: the new object is always labeled **"Dataset partagé"** or **"Dataset analytique"**, never plain "Dataset" — that word is already taken by the SP-13c open-data preview (`datasetCard` widget "Fiche jeu de données", `DatasetPage.tsx`, route `/public/datasets/:collectionId`), which is untouched by this plan.
- Reading a dataset's metadata and reading its underlying data are two independently-checked permissions: the dataset's own `can()` (owner/share/`is_published`/`is_public`, like any item) and the collection's RLS (already enforced by `features`/`aggregate`, nothing to add). A dataset shared more broadly than its source collection must never leak data.
- `refreshPolicy`, metrics (CEL), pipeline transforms (`filter`/`join`/`derive`/`pivot`/`spatial`), non-`collection` sources, global temporal/spatial context, cross-filter, SQL Lab are **out of scope** — do not add fields or UI for them.

---

## Part A — Core (Python/FastAPI)

### Task 1: `BuilderConfig` gains `kind="dataset"`

**Files:**
- Modify: `core/app/configs/schemas.py`
- Test: `core/tests/test_dataset_config_schema.py` (new)

**Interfaces:**
- Produces: `DatasetColumnMeta` (fields `label: str | None`, `description: str | None`, `format: str | None`), `DatasetPayload` (fields `source: Literal["collection"]`, `collectionId: str`, `columns: dict[str, DatasetColumnMeta]`), `BuilderConfig.dataset: DatasetPayload | None`, `BuilderConfig.kind` literal now includes `"dataset"`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_dataset_config_schema.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from pydantic import ValidationError

from app.configs.schemas import BuilderConfig


def _dataset_body(collection_id: str = "parcs") -> dict:
    return {
        "version": 1,
        "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": collection_id, "columns": {}},
    }


def test_dataset_config_valide():
    config = BuilderConfig.model_validate(_dataset_body())
    assert config.kind == "dataset"
    assert config.dataset.collectionId == "parcs"


def test_dataset_config_sans_payload_rejete():
    with pytest.raises(ValidationError):
        BuilderConfig.model_validate({"version": 1, "kind": "dataset"})


def test_dataset_config_colonnes_optionnelles():
    body = _dataset_body()
    body["dataset"]["columns"] = {"nom": {"label": "Nom", "format": "text"}}
    config = BuilderConfig.model_validate(body)
    assert config.dataset.columns["nom"].label == "Nom"
    assert config.dataset.columns["nom"].format == "text"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: FAIL — `kind` literal rejects `"dataset"` (`ValidationError` raised on `model_validate` itself, not inside the test body).

- [ ] **Step 3: Implement the schema changes**

In `core/app/configs/schemas.py`, add the two new models right after `MapConfig` (after line 85, before `class BuilderConfig`):

```python
class DatasetColumnMeta(BaseModel):
    label: str | None = None
    description: str | None = None
    format: str | None = None  # libre (ex. "currency", "percent", "date"),
                                 # interprété côté widget consommateur


class DatasetPayload(BaseModel):
    source: Literal["collection"]  # seul type supporté en SP-14a
    collectionId: str
    columns: dict[str, DatasetColumnMeta] = Field(default_factory=dict)
```

Then update `BuilderConfig` itself:

```python
class BuilderConfig(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    version: int = 1
    itemId: str | None = None
    kind: Literal["app", "dashboard", "map", "site", "dataset"]
    theme: dict = Field(default_factory=dict)
    dataSources: list[DataSource] = Field(default_factory=list)
    layout: Layout | None = None
    messages: list[Message] = Field(default_factory=list)
    pages: list[Page] = Field(default_factory=list)
    navigationMode: Literal["tabs", "story"] = "tabs"
    variables: list[Variable] = Field(default_factory=list)
    map: MapConfig | None = None
    dataset: DatasetPayload | None = None

    @model_validator(mode="after")
    def _require_kind_payload(self) -> "BuilderConfig":
        if self.kind in ("app", "dashboard", "site") and self.layout is None:
            raise ValueError(f"{self.kind} config requires a layout")
        if self.kind == "map" and self.map is None:
            raise ValueError("map config requires a map")
        if self.kind == "dataset" and self.dataset is None:
            raise ValueError("dataset config requires a dataset payload")
        return self
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_dataset_config_schema.py -v`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/schemas.py core/tests/test_dataset_config_schema.py
git commit -m "feat(core): add kind=dataset to BuilderConfig (SP-14a)"
```

---

### Task 2: Validate `collectionId` on dataset save

**Files:**
- Modify: `core/app/configs/routes.py`
- Test: `core/tests/test_create_dataset.py` (new)

**Interfaces:**
- Consumes: `BuilderConfig`/`DatasetPayload` from Task 1; `app.collections.repository.get_collection(session, *, tenant_id, collection_id) -> Collection | None`; `app.collections.repository.get_access_facts(col) -> AccessFacts`; `app.sharing.authorization.can(session, *, user_id, action, item, kind, actor_is_admin) -> bool`.
- Produces: `_validate_dataset_payload(session, config, *, user) -> None` (raises `HTTPException(422)` on invalid/unreadable collection), wired into `create_config`, `update_config`, `update_config_by_item`.

- [ ] **Step 1: Write the failing tests**

Create `core/tests/test_create_dataset.py`:

```python
# SPDX-License-Identifier: Apache-2.0
import pytest
from fastapi.testclient import TestClient

from app import db
from app.auth.dependency import get_current_user
from app.collections.models import Collection
from app.db import init_db, make_engine, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user


@pytest.fixture()
def client():
    engine = make_engine("sqlite+pysqlite:///:memory:")
    init_db(engine)
    Session = make_session_factory(engine)

    with Session() as setup_session:
        tenant = get_or_create_default_tenant(setup_session)
        user = get_or_create_user(
            setup_session, tenant_id=tenant.id, oidc_sub="sub-1",
            username="alice", email="alice@example.com", first_name="Alice", last_name="Doe",
        )
        collection = Collection(
            id="parcs", tenant_id=tenant.id, owner_id=user.id, table_name="parcs",
            title="Parcs", pk_column="id", is_public=True, editable=True,
        )
        setup_session.add(collection)
        setup_session.commit()

    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    app.dependency_overrides[get_current_user] = lambda: user

    test_client = TestClient(app)
    test_client.user = user  # type: ignore[attr-defined]
    yield test_client
    engine.dispose()


def _dataset_body(collection_id: str, title: str = "Parcs partagés") -> dict:
    return {
        "title": title,
        "config": {
            "version": 1,
            "kind": "dataset",
            "dataset": {"source": "collection", "collectionId": collection_id, "columns": {}},
        },
    }


def test_create_dataset_avec_collection_existante(client):
    res = client.post("/configs", json=_dataset_body("parcs"))
    assert res.status_code == 201, res.text
    item_id = res.json()["itemId"]
    item = client.get(f"/items/{item_id}").json()
    assert item["resourceType"] == "dataset"


def test_create_dataset_collection_inexistante_rejete(client):
    res = client.post("/configs", json=_dataset_body("inexistante"))
    assert res.status_code == 422


def test_update_dataset_collection_inexistante_rejete(client):
    created = client.post("/configs", json=_dataset_body("parcs"))
    item_id = created.json()["itemId"]
    bad_config = {
        "version": 1, "kind": "dataset",
        "dataset": {"source": "collection", "collectionId": "inexistante", "columns": {}},
    }
    res = client.put(f"/configs/by-item/{item_id}", json=bad_config)
    assert res.status_code == 422
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd core && uv run pytest tests/test_create_dataset.py -v`
Expected: FAIL — `test_create_dataset_collection_inexistante_rejete` and `test_update_dataset_collection_inexistante_rejete` get `201`/`200` instead of `422` (no validation exists yet). `test_create_dataset_avec_collection_existante` passes already (nothing blocks it), which is fine — it's a regression guard for the next step.

- [ ] **Step 3: Implement the validation**

In `core/app/configs/routes.py`, add this function right after `_validate_extension_scope` (after line 64):

```python
def _validate_dataset_payload(session: Session, config: BuilderConfig, *, user: User) -> None:
    if config.kind != "dataset":
        return
    from app.collections import repository as collections_repo

    payload = config.dataset
    assert payload is not None  # guaranteed by BuilderConfig._require_kind_payload
    collection = collections_repo.get_collection(
        session, tenant_id=user.tenant_id, collection_id=payload.collectionId,
    )
    if collection is None:
        raise HTTPException(status_code=422, detail="collection not found")
    readable = can(
        session, user_id=user.id, action="read",
        item=collections_repo.get_access_facts(collection), kind="collection",
        actor_is_admin=user.is_admin,
    )
    if not readable:
        # Same message as the not-found branch: don't leak collection existence.
        raise HTTPException(status_code=422, detail="collection not found")
```

Then call it right after each existing `_validate_extension_scope(...)` call:

In `create_config` (after line 73):
```python
    _validate_extension_scope(session, request.config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, request.config, user=user)
```

In `update_config` (after line 122):
```python
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
```

In `update_config_by_item` (after line 220):
```python
    _validate_extension_scope(session, config, tenant_id=user.tenant_id)
    _validate_dataset_payload(session, config, user=user)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd core && uv run pytest tests/test_create_dataset.py tests/test_dataset_config_schema.py tests/test_create_site.py tests/test_configs_extension_permissions.py -v`
Expected: PASS — all tests green, including the pre-existing `site`/extension-permission tests (regression check).

- [ ] **Step 5: Commit**

```bash
git add core/app/configs/routes.py core/tests/test_create_dataset.py
git commit -m "feat(core): validate dataset collectionId on save (SP-14a)"
```

---

## Part B — Shell (React/TypeScript)

### Task 3: Types — `ResourceType`, `DataSource.datasetId`, `DatasetConfig`

**Files:**
- Modify: `shell/src/api/types.ts`

**Interfaces:**
- Produces: `ResourceType` includes `"dataset"`; `DataSource.datasetId?: string`; `DatasetColumnMeta = { label?: string; description?: string; format?: string }`; `DatasetConfig = { source: "collection"; collectionId: string; columns: Record<string, DatasetColumnMeta> }`; `ItemClient` interface gains `createDatasetItem`, `getDatasetConfig`, `saveDatasetConfig`.

This task is a type-only change (no runtime behavior yet) — it's verified by the TypeScript compiler, not a unit test.

- [ ] **Step 1: Edit `ResourceType`**

In `shell/src/api/types.ts`, line 2:

```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external";
```

(`CreateKind` on line 4 stays `"app" | "dashboard" | "site"` — dataset creation goes through a dedicated `createDatasetItem`, exactly like `map` goes through `createMapItem` rather than the generic `createConfigItem`.)

- [ ] **Step 2: Add `DataSource.datasetId`**

Replace the `DataSource` type (lines 201–207):

```ts
export type DataSource = {
  id: string;
  type: "features" | "static" | "statistics";
  service: string;
  layer: string; // résolu automatiquement si datasetId est présent
  datasetId?: string;
  query: Record<string, unknown>;
};
```

- [ ] **Step 3: Add `DatasetColumnMeta`/`DatasetConfig`**

Right after the `DataSource` type (after the new line 208), add:

```ts
export type DatasetColumnMeta = {
  label?: string;
  description?: string;
  format?: string;
};

export type DatasetConfig = {
  source: "collection";
  collectionId: string;
  columns: Record<string, DatasetColumnMeta>;
};
```

- [ ] **Step 4: Extend `ItemClient`**

In the `ItemClient` interface, right after `saveMapConfig` (line 135), add:

```ts
  createDatasetItem(input: { title: string; owner: string; collectionId: string }): Promise<Item>;
  getDatasetConfig(pk: string): Promise<DatasetConfig>;
  saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void>;
```

- [ ] **Step 5: Verify it compiles**

Run: `cd shell && npm run build`
Expected: FAILS — `itemClient.ts`'s `createItemClient(...)` return object no longer satisfies `ItemClient` (missing the 3 new methods). This is expected; Task 4 implements them.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/types.ts
git commit -m "feat(shell): add dataset kind types (SP-14a)"
```

(Commit even though the build is red — Task 4 is the very next task and fixes it. If your workflow requires green-at-every-commit, squash Tasks 3+4 into one commit instead.)

---

### Task 4: `itemClient.ts` — dataset CRUD + `datasetId` resolution

**Files:**
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: `DatasetConfig`, `DatasetColumnMeta` from Task 3.
- Produces: `createItemClient(...).createDatasetItem/getDatasetConfig/saveDatasetConfig`; `featuresUrl`/`queryDataSource` transparently resolve `source.datasetId` to a `collectionId` before delegating to the existing `features`/`statistics`/`static` code.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts` (append after the existing `saveMapConfig` tests, i.e. after the block ending around line 319):

```ts
test("createDatasetItem posts a dataset payload and returns a dataset Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds1", kind: "dataset", itemId: "ds-1" }, { status: 201 });
    }),
  );
  const item = await makeClient().createDatasetItem({ title: "Parcs", owner: "alice", collectionId: "parcs" });
  expect(body.config.kind).toBe("dataset");
  expect(body.config.dataset).toEqual({ source: "collection", collectionId: "parcs", columns: {} });
  expect(item).toMatchObject({ pk: "ds-1", resourceType: "dataset", title: "Parcs", configId: "cfg-ds1" });
});

test("getDatasetConfig reads the dataset payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-2", () =>
      HttpResponse.json({
        id: "cfg-ds2", itemId: "ds-2", kind: "dataset",
        config: {
          kind: "dataset",
          dataset: { source: "collection", collectionId: "parcs", columns: { nom: { label: "Nom" } } },
        },
      }),
    ),
  );
  const cfg = await makeClient().getDatasetConfig("ds-2");
  expect(cfg).toEqual({ source: "collection", collectionId: "parcs", columns: { nom: { label: "Nom" } } });
});

test("getDatasetConfig throws when the config has no dataset payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-3", () =>
      HttpResponse.json({ id: "cfg-ds3", itemId: "ds-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getDatasetConfig("ds-3")).rejects.toThrow();
});

test("saveDatasetConfig PUTs the dataset config by item", async () => {
  let method = ""; let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/ds-4", async ({ request }) => {
      method = request.method; body = await request.json();
      return HttpResponse.json({ id: "cfg-ds4", itemId: "ds-4", kind: "dataset", dataset: body.dataset });
    }),
  );
  await makeClient().saveDatasetConfig("ds-4", { source: "collection", collectionId: "parcs", columns: {} });
  expect(method).toBe("PUT");
  expect(body.kind).toBe("dataset");
  expect(body.dataset.collectionId).toBe("parcs");
});

test("featuresUrl resolves datasetId to the dataset's collectionId once cached", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-5", () =>
      HttpResponse.json({
        id: "cfg-ds5", itemId: "ds-5", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
  );
  const client = makeClient();
  // Cache-miss: falls back to source.layer (empty) until something warms the cache.
  expect(client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-5", query: {} }))
    .toBe("https://core.test/collections//items");
  await client.getDatasetConfig("ds-5"); // warms the cache
  expect(client.featuresUrl({ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-5", query: {} }))
    .toBe("https://core.test/collections/parcs/items");
});

test("queryDataSource resolves datasetId to the dataset's collectionId before fetching features", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/ds-6", () =>
      HttpResponse.json({
        id: "cfg-ds6", itemId: "ds-6", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
    http.get("https://core.test/collections/parcs/items", () =>
      HttpResponse.json({ features: [{ id: 1, properties: { nom: "Le Parc" } }] }),
    ),
  );
  const records = await makeClient().queryDataSource({
    id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-6", query: {},
  });
  expect(records).toEqual([{ id: 1, properties: { nom: "Le Parc" }, geometry: undefined }]);
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `createDatasetItem`/`getDatasetConfig`/`saveDatasetConfig` are not functions yet (`TypeError`), and the build itself is still red from Task 3.

- [ ] **Step 3: Implement the client methods and `datasetId` resolution**

In `shell/src/api/itemClient.ts`, add `DatasetConfig`/`DatasetColumnMeta` to the type-only import at the top of the file (line 2): append `, DatasetColumnMeta, DatasetConfig` to the existing `import type { ... } from "./types";` list.

Add a module-scope cache + resolver inside `createItemClient(...)`, right after the `request` function definition (after line 136):

```ts
  const datasetCache = new Map<string, { collectionId: string; columns: Record<string, DatasetColumnMeta> }>();

  async function resolveDataset(pk: string): Promise<{ collectionId: string; columns: Record<string, DatasetColumnMeta> }> {
    const cached = datasetCache.get(pk);
    if (cached) return cached;
    const data = await request<{
      config?: { dataset?: { collectionId: string; columns?: Record<string, DatasetColumnMeta> } | null };
    }>("GET", `/configs/by-item/${pk}`);
    const dataset = data.config?.dataset;
    if (!dataset) throw new Error("resolveDataset: config has no dataset payload");
    const resolved = { collectionId: dataset.collectionId, columns: dataset.columns ?? {} };
    datasetCache.set(pk, resolved);
    return resolved;
  }
```

Add the three new methods right after `saveMapConfig` (after line 465):

```ts
    async createDatasetItem(input: { title: string; owner: string; collectionId: string }): Promise<Item> {
      const dataset: DatasetConfig = { source: "collection", collectionId: input.collectionId, columns: {} };
      const config = { version: 1, kind: "dataset", dataset };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createDatasetItem: core returned no itemId");
      datasetCache.set(String(data.itemId), { collectionId: input.collectionId, columns: {} });
      return {
        pk: String(data.itemId), resourceType: "dataset", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getDatasetConfig(pk: string): Promise<DatasetConfig> {
      const resolved = await resolveDataset(pk);
      return { source: "collection", collectionId: resolved.collectionId, columns: resolved.columns };
    },

    async saveDatasetConfig(pk: string, config: DatasetConfig): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "dataset", dataset: config });
      datasetCache.set(pk, { collectionId: config.collectionId, columns: config.columns });
    },
```

Replace `featuresUrl` (lines 536–538):

```ts
    featuresUrl(source: DataSource): string {
      if (source.datasetId) {
        const cached = datasetCache.get(source.datasetId);
        return buildFeaturesUrl(coreUrl, { ...source, layer: cached?.collectionId ?? source.layer });
      }
      return buildFeaturesUrl(coreUrl, source);
    },
```

Replace `queryDataSource` (lines 540–564):

```ts
    async queryDataSource(source: DataSource): Promise<DataRecord[]> {
      const resolved = source.datasetId
        ? { ...source, layer: (await resolveDataset(source.datasetId)).collectionId }
        : source;
      if (resolved.type === "static") {
        return (resolved.query.records as DataRecord[] | undefined) ?? [];
      }
      if (resolved.type === "statistics") {
        const body = buildAggregateBody(resolved.query);
        const data = await request<{ categoryKey: string; rows: Record<string, unknown>[] }>(
          "POST", `/collections/${resolved.layer}/aggregate`, body,
        );
        return data.rows.map((row) => ({ id: String(row[data.categoryKey] ?? ""), properties: row }));
      }
      const token = getToken();
      const res = await fetch(buildFeaturesUrl(coreUrl, resolved), {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw new Error(`Request failed: ${res.status} features ${resolved.layer}`);
      const data = (await res.json()) as {
        features?: { id?: string | number; properties?: Record<string, unknown>; geometry?: unknown }[];
      };
      return (data.features ?? []).map((f, i) => ({
        id: f.id ?? i,
        properties: f.properties ?? {},
        geometry: f.geometry,
      }));
    },
```

- [ ] **Step 4: Run the tests and the build**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts && npm run build`
Expected: PASS — all itemClient tests green, `tsc --noEmit` clean (the `ItemClient` interface is now fully satisfied).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): resolve DataSource.datasetId in itemClient (SP-14a)"
```

---

### Task 5: Schema-fusion helper

**Files:**
- Create: `shell/src/lib/datasetSchema.ts`
- Test: `shell/src/lib/datasetSchema.test.ts`

**Interfaces:**
- Consumes: `CollectionSchema`, `DatasetColumnMeta` from `shell/src/api/types.ts`.
- Produces: `mergeDatasetSchema(schema: CollectionSchema, columns: Record<string, DatasetColumnMeta>): MergedSchemaField[]`, used by Task 8's `DatasetEditPage`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/lib/datasetSchema.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import { mergeDatasetSchema } from "./datasetSchema";
import type { CollectionSchema } from "../api/types";

const schema: CollectionSchema = {
  collection: "parcs",
  pk: "id",
  geometry: { column: "geom", type: "Point", srid: 4326 },
  fields: [
    { name: "nom", type: "string", required: true },
    { name: "surface", type: "number", required: false },
  ],
};

describe("mergeDatasetSchema", () => {
  test("merges column overrides onto the introspected fields, in schema order", () => {
    const merged = mergeDatasetSchema(schema, { nom: { label: "Nom du parc", format: "text" } });
    expect(merged).toEqual([
      { name: "nom", type: "string", required: true, label: "Nom du parc", format: "text" },
      { name: "surface", type: "number", required: false },
    ]);
  });

  test("fields without an override keep only their introspected properties", () => {
    const merged = mergeDatasetSchema(schema, {});
    expect(merged).toEqual(schema.fields);
  });

  test("an override for a column no longer in the schema is silently dropped", () => {
    const merged = mergeDatasetSchema(schema, { disparue: { label: "Fantôme" } });
    expect(merged.find((f) => f.name === "disparue")).toBeUndefined();
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/lib/datasetSchema.test.ts`
Expected: FAIL — `Cannot find module './datasetSchema'`.

- [ ] **Step 3: Implement the helper**

Create `shell/src/lib/datasetSchema.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema, CollectionSchemaField, DatasetColumnMeta } from "../api/types";

export type MergedSchemaField = CollectionSchemaField & DatasetColumnMeta;

export function mergeDatasetSchema(
  schema: CollectionSchema,
  columns: Record<string, DatasetColumnMeta>,
): MergedSchemaField[] {
  return schema.fields.map((field) => ({ ...field, ...columns[field.name] }));
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/lib/datasetSchema.test.ts`
Expected: PASS (3 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/lib/datasetSchema.ts shell/src/lib/datasetSchema.test.ts
git commit -m "feat(shell): merge dataset column overrides onto collection schema (SP-14a)"
```

---

### Task 6: `useCreateDataset`/`useDatasetConfig`/`useSaveDataset` hooks

**Files:**
- Modify: `shell/src/api/hooks.ts`

**Interfaces:**
- Consumes: `client.createDatasetItem`/`getDatasetConfig`/`saveDatasetConfig` from Task 4.
- Produces: `useCreateDataset()`, `useDatasetConfig(pk, options?)`, `useSaveDataset(pk)` — same react-query shape as `useCreateMap`/`useMapConfig`/`useSaveMap`.

No new test file: these hooks are thin react-query wrappers, exercised indirectly by the component tests in Tasks 7–9 (matching how `useCreateMap`/`useMapConfig`/`useSaveMap` have no dedicated hook-level test either).

- [ ] **Step 1: Add `DatasetConfig` to the type import**

In `shell/src/api/hooks.ts` line 4, add `DatasetConfig` to the `import type { ... } from "./types";` list.

- [ ] **Step 2: Add the hooks**

Right after `useSaveMap` (after line 197 per the current file), add:

```ts
export function useCreateDataset() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; collectionId: string }) => client.createDatasetItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useDatasetConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["dataset", pk],
    queryFn: () => client.getDatasetConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useSaveDataset(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (config: DatasetConfig) => client.saveDatasetConfig(pk, config),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["dataset", pk] });
    },
  });
}
```

- [ ] **Step 3: Verify the build**

Run: `cd shell && npm run build`
Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add shell/src/api/hooks.ts
git commit -m "feat(shell): add dataset create/read/save hooks (SP-14a)"
```

---

### Task 7: `NewItemButton` — create a dataset from the catalogue

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx` (extend if it exists, else create)

**Interfaces:**
- Consumes: `useCreateDataset` (Task 6), `useCollectionsAdmin` (existing, `shell/src/api/hooks.ts:253`, a plain `GET /collections` list despite its name).
- Produces: `NewItemButton` renders a `"Dataset partagé"` option in the Type select; when selected, replaces the "Modèle" selector with a "Collection source" selector; on submit, creates the item and navigates to `/datasets/{pk}/edit`.

- [ ] **Step 1: Write the failing test**

Check whether `shell/src/shell/NewItemButton.test.tsx` exists (`ls shell/src/shell/NewItemButton.test.tsx`). If it does, append the test below to it, reusing whatever `render`/`msw` helpers it already imports. If it doesn't exist, create it with this minimal content (adjust the render helper import to match this project's existing test-utils, e.g. `shell/src/test/render.tsx` if present):

```ts
test("creating a dataset posts collectionId and navigates to the dataset editor", async () => {
  let body: any;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [{ id: "parcs", title: "Parcs", description: "", tableName: "parcs", isPublic: true, editable: true, geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 3, owner: "alice" }] }),
    ),
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds", kind: "dataset", itemId: "ds-9" }, { status: 201 });
    }),
  );
  renderWithProviders(<NewItemButton />);

  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await userEvent.selectOptions(await screen.findByLabelText("Collection source"), "parcs");
  await userEvent.type(screen.getByLabelText("Titre"), "Parcs partagés");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));

  await waitFor(() => expect(body?.config?.dataset?.collectionId).toBe("parcs"));
  expect(mockNavigate).toHaveBeenCalledWith("/datasets/ds-9/edit");
});
```

(This step's exact imports/helpers depend on how the existing test suite wires `msw`/`react-router` mocks for this component — mirror whatever `map-editor`-equivalent unit test already does for `NewItemButton`, e.g. how `mockNavigate`/`renderWithProviders` are obtained elsewhere in `shell/src/shell/*.test.tsx`.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: FAIL — `"dataset"` is not a valid option in the Type select yet.

- [ ] **Step 3: Implement `NewItemButton`**

Replace the full content of `shell/src/shell/NewItemButton.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateItem, useCreateMap, useCreateDataset, useCollectionsAdmin } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";
import { TEMPLATES } from "../builder/templates";
import { isValidSlug, slugify } from "../lib/slug";

type Kind = "app" | "dashboard" | "map" | "site" | "dataset";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<Kind>("app");
  const [title, setTitle] = useState("");
  const [templateId, setTemplateId] = useState("");
  const [slug, setSlug] = useState("");
  const [slugTouched, setSlugTouched] = useState(false);
  const [collectionId, setCollectionId] = useState("");
  const { username } = useAuth();
  const navigate = useNavigate();
  const create = useCreateItem();
  const createMap = useCreateMap();
  const createDataset = useCreateDataset();
  const collectionsQuery = useCollectionsAdmin({ enabled: open && kind === "dataset" });

  // Slug auto-suivi du titre tant que l'utilisateur ne l'a pas édité lui-même.
  useEffect(() => {
    if (kind === "site" && !slugTouched) setSlug(slugify(title));
  }, [title, kind, slugTouched]);

  function close() {
    setOpen(false);
    setTitle("");
    setKind("app");
    setTemplateId("");
    setSlug("");
    setSlugTouched(false);
    setCollectionId("");
    create.reset();
    createMap.reset();
    createDataset.reset();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    if (kind === "site" && !isValidSlug(slug)) return;
    if (kind === "dataset" && !collectionId) return;
    try {
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : kind === "dataset"
            ? await createDataset.mutateAsync({ title: clean, owner: username ?? "", collectionId })
            : await create.mutateAsync({
                kind,
                title: clean,
                owner: username ?? "",
                templateId: templateId || undefined,
                slug: kind === "site" ? slug : undefined,
              });
      close();
      navigate(
        kind === "map" ? `/maps/${item.pk}` : kind === "dataset" ? `/datasets/${item.pk}/edit` : `/apps/${item.pk}/edit`,
      );
    } catch {
      // error surfaced via isError
    }
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Nouveau
      </Button>
      <Dialog open={open} onClose={close} title="Nouvel élément">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={kind}
              onChange={(e) => { setKind(e.target.value as Kind); setTemplateId(""); }}
            >
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
              <option value="site">Site</option>
              <option value="dataset">Dataset partagé</option>
            </select>
          </label>
          {kind !== "map" && kind !== "dataset" && (
            <label className="flex flex-col gap-1 text-sm">
              Modèle
              <select
                aria-label="Modèle"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                <option value="">Vide</option>
                {TEMPLATES.filter((t) => t.kind === kind).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
          )}
          {kind === "dataset" && (
            <label className="flex flex-col gap-1 text-sm">
              Collection source
              <select
                aria-label="Collection source"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={collectionId}
                onChange={(e) => setCollectionId(e.target.value)}
              >
                <option value="">Choisir…</option>
                {(collectionsQuery.data ?? []).map((c) => (
                  <option key={c.id} value={c.id}>{c.title}</option>
                ))}
              </select>
            </label>
          )}
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input
              aria-label="Titre"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {kind === "site" && (
            <label className="flex flex-col gap-1 text-sm">
              Slug
              <Input
                aria-label="Slug"
                value={slug}
                onChange={(e) => { setSlug(e.target.value); setSlugTouched(true); }}
              />
              {slug && !isValidSlug(slug) && (
                <span className="text-xs text-red-600">Slug invalide (minuscules, chiffres, tirets).</span>
              )}
            </label>
          )}
          {(create.isError || createMap.isError || createDataset.isError) && (
            <p role="alert" className="text-sm text-red-600">
              Échec de la création.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button
              type="submit"
              size="sm"
              disabled={
                create.isPending || createMap.isPending || createDataset.isPending ||
                (kind === "site" && !isValidSlug(slug)) ||
                (kind === "dataset" && !collectionId)
              }
            >
              Créer
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx
git commit -m "feat(shell): create a shared dataset from the catalogue (SP-14a)"
```

---

### Task 8: `DatasetEditPage` + routing

**Files:**
- Create: `shell/src/pages/DatasetEditPage.tsx`
- Test: `shell/src/pages/DatasetEditPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`, `shell/src/pages/ItemDetailPage.tsx`

**Interfaces:**
- Consumes: `useItem`, `useUpdateItem` (existing), `useDatasetConfig`, `useSaveDataset` (Task 6), `client.getCollectionSchema` (existing), `mergeDatasetSchema` (Task 5), `MetadataForm` (existing, `shell/src/ui/MetadataForm.tsx`).
- Produces: `DatasetEditPage({ pk }: { pk: string })`, route `/datasets/:pk/edit`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/DatasetEditPage.test.tsx` (mirror the msw/render setup used by `shell/src/pages/MapEditorPage.test.tsx` if it exists — same `server.use(...)` + render pattern as Task 4's client tests, applied at component level):

```tsx
// SPDX-License-Identifier: Apache-2.0
import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { test, expect } from "vitest";
import { server } from "../test/msw/server";
import { renderWithProviders } from "../test/renderWithProviders";
import { DatasetEditPage } from "./DatasetEditPage";

test("loads the dataset, shows merged columns, and saves an edited label", async () => {
  let putBody: any;
  server.use(
    http.get("https://core.test/items/ds-1", () =>
      HttpResponse.json({
        pk: "ds-1", resourceType: "dataset", title: "Parcs", abstract: "", owner: "alice",
        thumbnailUrl: null, date: "2026-01-01", configId: "cfg-ds1", isPublished: false, keywords: [],
      }),
    ),
    http.get("https://core.test/configs/by-item/ds-1", () =>
      HttpResponse.json({
        id: "cfg-ds1", itemId: "ds-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: {} } },
      }),
    ),
    http.get("https://core.test/collections/parcs/schema", () =>
      HttpResponse.json({
        collection: "parcs", pk: "id", geometry: null,
        fields: [{ name: "nom", type: "string", required: true }],
      }),
    ),
    http.put("https://core.test/configs/by-item/ds-1", async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json({ id: "cfg-ds1", itemId: "ds-1", kind: "dataset", dataset: putBody.dataset });
    }),
  );

  renderWithProviders(<DatasetEditPage pk="ds-1" />);

  await screen.findByText("nom");
  await userEvent.type(screen.getByLabelText("Libellé de nom"), "Nom du parc");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(putBody?.dataset?.columns?.nom?.label).toBe("Nom du parc"));
});
```

(If this project has no `shell/src/test/renderWithProviders.ts` helper, use whichever provider-wrapping render utility `MapEditorPage.test.tsx` or `AppBuilderPage.test.tsx` already imports instead.)

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx`
Expected: FAIL — `Cannot find module './DatasetEditPage'`.

- [ ] **Step 3: Implement `DatasetEditPage`**

Create `shell/src/pages/DatasetEditPage.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useDatasetConfig, useItem, useSaveDataset, useUpdateItem } from "../api/hooks";
import { useItemClient } from "../api/ItemClientProvider";
import type { DatasetColumnMeta, DatasetConfig } from "../api/types";
import { mergeDatasetSchema } from "../lib/datasetSchema";
import { MetadataForm } from "../ui/MetadataForm";
import { Button } from "../ui/button";

export function DatasetEditPage({ pk }: { pk: string }) {
  const itemQuery = useItem(pk);
  const configQuery = useDatasetConfig(pk);
  const save = useSaveDataset(pk);
  const updateItem = useUpdateItem(pk);
  const client = useItemClient();
  const [draft, setDraft] = useState<DatasetConfig | null>(null);

  useEffect(() => {
    if (configQuery.data) setDraft((d) => d ?? configQuery.data);
  }, [configQuery.data]);

  const schemaQuery = useQuery({
    queryKey: ["collection-schema", draft?.collectionId],
    queryFn: () => client.getCollectionSchema(draft!.collectionId),
    enabled: Boolean(draft?.collectionId),
  });

  if (itemQuery.isLoading || configQuery.isLoading || (!draft && !configQuery.isError))
    return <p role="status">Chargement…</p>;
  if (itemQuery.isError || configQuery.isError || !draft || !itemQuery.data)
    return (
      <p role="alert" className="text-sm text-red-600">
        Dataset introuvable.
      </p>
    );

  function setColumn(name: string, patch: DatasetColumnMeta) {
    setDraft((d) => (d ? { ...d, columns: { ...d.columns, [name]: { ...d.columns[name], ...patch } } } : d));
  }

  const merged = schemaQuery.data ? mergeDatasetSchema(schemaQuery.data, draft.columns) : [];

  return (
    <div className="flex flex-col gap-4 p-4">
      <h2 className="text-xl font-semibold">Dataset partagé — {itemQuery.data.title}</h2>
      <MetadataForm
        initial={{ title: itemQuery.data.title, abstract: itemQuery.data.abstract, keywords: itemQuery.data.keywords ?? [] }}
        onSubmit={(v) => updateItem.mutate(v)}
        onCancel={() => {}}
        pending={updateItem.isPending}
      />
      <div>
        <p className="mb-1 text-xs font-medium text-slate-500">Colonnes</p>
        {schemaQuery.isLoading && <p role="status">Chargement du schéma…</p>}
        {schemaQuery.isError && (
          <p role="alert" className="text-sm text-red-600">
            Collection source introuvable.
          </p>
        )}
        {merged.length > 0 && (
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-xs text-slate-500">
                <th className="p-1">Colonne</th>
                <th className="p-1">Libellé</th>
                <th className="p-1">Description</th>
                <th className="p-1">Format</th>
              </tr>
            </thead>
            <tbody>
              {merged.map((f) => (
                <tr key={f.name} className="border-t border-slate-200">
                  <td className="p-1 font-mono text-xs">{f.name}</td>
                  <td className="p-1">
                    <input aria-label={`Libellé de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.label ?? ""} onChange={(e) => setColumn(f.name, { label: e.target.value })} />
                  </td>
                  <td className="p-1">
                    <input aria-label={`Description de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.description ?? ""} onChange={(e) => setColumn(f.name, { description: e.target.value })} />
                  </td>
                  <td className="p-1">
                    <input aria-label={`Format de ${f.name}`} className="h-8 w-full rounded border border-slate-300 px-2 text-xs"
                      value={f.format ?? ""} onChange={(e) => setColumn(f.name, { format: e.target.value })} />
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
      <Button size="sm" className="w-fit" disabled={save.isPending} onClick={() => save.mutate(draft)}>
        Enregistrer
      </Button>
      {save.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de l'enregistrement.
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Wire the route**

In `shell/src/shell/routes.tsx`:

Add the import (after line 10, alongside the other page imports):
```tsx
import { DatasetEditPage } from "../pages/DatasetEditPage";
```

Add a route wrapper (after `AppBuilderRoute`, i.e. after line 48):
```tsx
function DatasetEditRoute() {
  const { pk } = useParams();
  return <DatasetEditPage pk={pk!} />;
}
```

Register the route inside `<ProtectedLayout>` (after line 87, `/apps/:pk/edit`):
```tsx
        <Route path="/datasets/:pk/edit" element={<DatasetEditRoute />} />
```

Update `CatalogRoute` (lines 17–26) so opening a dataset from the catalogue lands on its editor:
```tsx
function CatalogRoute() {
  const navigate = useNavigate();
  return (
    <CatalogPage
      onOpenItem={(pk, type) =>
        navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`)
      }
    />
  );
}
```

Update `ItemDetailRoute` (lines 28–38) the same way:
```tsx
function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`)}
    />
  );
}
```

In `shell/src/pages/ItemDetailPage.tsx`, extend the editor-availability check on line 29:
```tsx
      {["map", "app", "dashboard", "dataset"].includes(item.resourceType) ? (
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/pages/DatasetEditPage.test.tsx && npm run build`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/DatasetEditPage.tsx shell/src/pages/DatasetEditPage.test.tsx shell/src/shell/routes.tsx shell/src/pages/ItemDetailPage.tsx
git commit -m "feat(shell): dataset edit page and routing (SP-14a)"
```

---

### Task 9: `DataSourcePanel` — "Promote to shared dataset"

**Files:**
- Modify: `shell/src/builder/DataSourcePanel.tsx`, `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/DataSourcePanel.test.tsx` (extend if it exists, else create)

**Interfaces:**
- Consumes: `useCreateDataset` (Task 6), `useAuth` (existing).
- Produces: `DataSourcePanel` gains optional props `onPromote?: (id: string) => void; promotingId?: string | null;`; `AppBuilderPage` wires a `promoteSource` handler that creates the dataset and rewrites the matching `dataSources[]` entry in place (`datasetId` set, `layer` untouched).

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/DataSourcePanel.test.tsx` (create it if it doesn't exist, following the render pattern of a sibling test like `shell/src/builder/DatasetDownloadButtons.test.tsx`):

```tsx
test("promoting a features source calls onPromote and then shows it as shared", async () => {
  const onChange = vi.fn();
  const onPromote = vi.fn();
  const sources = [{ id: "s1", type: "features" as const, service: "core", layer: "parcs", query: {} }];
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} onPromote={onPromote} promotingId={null} />);

  await userEvent.click(screen.getByRole("button", { name: "Promouvoir en dataset partagé s1" }));
  expect(onPromote).toHaveBeenCalledWith("s1");

  rerender(
    <DataSourcePanel
      sources={[{ ...sources[0], datasetId: "ds-1" }]}
      onChange={onChange}
      onPromote={onPromote}
      promotingId={null}
    />,
  );
  expect(screen.getByText("Dataset partagé actif")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Promouvoir en dataset partagé s1" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx`
Expected: FAIL — no such button exists yet.

- [ ] **Step 3: Implement the promote UI in `DataSourcePanel`**

In `shell/src/builder/DataSourcePanel.tsx`, replace the props destructuring (lines 9–15):

```tsx
export function DataSourcePanel({
  sources,
  onChange,
  onPromote,
  promotingId,
}: {
  sources: DataSource[];
  onChange: (sources: DataSource[]) => void;
  onPromote?: (id: string) => void;
  promotingId?: string | null;
}) {
```

Then, right after the collection `<input>` block (lines 53–57), insert:

```tsx
            {s.type === "features" && onPromote && (
              s.datasetId ? (
                <p className="mt-1 text-xs text-emerald-700">Dataset partagé actif</p>
              ) : (
                <button type="button" aria-label={`Promouvoir en dataset partagé ${s.id}`}
                  className="mt-1 rounded border border-slate-300 px-2 py-0.5 text-xs hover:bg-slate-100 disabled:opacity-50"
                  disabled={!s.layer || promotingId === s.id}
                  onClick={() => onPromote(s.id)}>
                  {promotingId === s.id ? "Promotion…" : "Promouvoir en dataset partagé"}
                </button>
              )
            )}
```

- [ ] **Step 4: Wire it up in `AppBuilderPage`**

In `shell/src/pages/AppBuilderPage.tsx`, update the hooks import (line 4):
```tsx
import { useAppConfig, useCreateDataset, useSaveApp, useUploadThumbnail } from "../api/hooks";
```
Add, alongside the other top-level imports:
```tsx
import { useAuth } from "../auth/useAuth";
```

Add state and the promote handler, right after `const thumbnail = useUploadThumbnail(pk);` (line 33):
```tsx
  const { username } = useAuth();
  const createDataset = useCreateDataset();
  const [promotingId, setPromotingId] = useState<string | null>(null);
```

Add the handler function next to `setSources` (after line 122):
```tsx
  async function promoteSource(id: string) {
    if (!draft) return;
    const source = draft.dataSources.find((s) => s.id === id);
    if (!source || !source.layer) return;
    setPromotingId(id);
    try {
      const item = await createDataset.mutateAsync({
        title: source.layer, owner: username ?? "", collectionId: source.layer,
      });
      setSources(draft.dataSources.map((s) => (s.id === id ? { ...s, datasetId: item.pk } : s)));
    } catch {
      /* surfaced via createDataset.isError */
    } finally {
      setPromotingId(null);
    }
  }
```

Update the `<DataSourcePanel>` usage (line 185):
```tsx
            <DataSourcePanel sources={draft.dataSources} onChange={setSources} onPromote={promoteSource} promotingId={promotingId} />
            {createDataset.isError && <p role="alert" className="text-xs text-red-600">Échec de la promotion.</p>}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataSourcePanel.test.tsx src/pages/AppBuilderPage.test.tsx && npm run build`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/DataSourcePanel.tsx shell/src/builder/DataSourcePanel.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "feat(shell): promote an inline data source to a shared dataset (SP-14a)"
```

---

### Task 10: `DataSourceSelect` — list accessible shared datasets

**Files:**
- Create: `shell/src/builder/DataSourcesEditContext.tsx`
- Modify: `shell/src/builder/DataSourceSelect.tsx`, `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/builder/DataSourceSelect.test.tsx` (extend if it exists, else create)

**Interfaces:**
- Produces: `DataSourcesEditProvider({ onAdd, children })`, `useAddDataSource(): ((source: DataSource) => void) | null`. `DataSourceSelect` lists shared datasets in an `<optgroup>`; picking one calls `onAdd` (injecting a new inline `DataSource` with `datasetId` set) then `onChange` with its new id — **no widget file changes** (`chart.tsx`, `indicator.tsx`, `data.tsx`, `datasetCard.tsx` stay untouched; they only ever see the existing `onChange(id: string)` contract).

**Design note (why a context, not a new prop):** `DataProvider`/`DataContext.tsx` resolves every widget's data strictly from `draft.dataSources[]` (keyed by `DataSource.id`) — a value picked in `DataSourceSelect` that isn't already in that array can never produce data. Threading a "create a new inline source" callback through every widget's `PropsPanel({props, onChange, dataSources})` signature would touch all 4 widget files, contradicting the spec's "no widget changes." A React context read only inside `DataSourceSelect` (the single shared component all 4 widgets already use) avoids that: `AppBuilderPage` provides `onAdd`, `DataSourceSelect` consumes it — zero other file touches.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/builder/DataSourceSelect.test.tsx` (create it if it doesn't exist):

```tsx
test("picking a shared dataset not yet inline calls onAdd then onChange with the new source id", async () => {
  server.use(
    http.get("https://core.test/items*", ({ request }) => {
      const url = new URL(request.url);
      if (url.searchParams.get("type") !== "dataset") return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
      return HttpResponse.json({
        items: [{ pk: "ds-1", resourceType: "dataset", title: "Parcs partagés", abstract: "", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-ds1", isPublished: true }],
        total: 1, page: 1, pageSize: 12,
      });
    }),
  );
  const onChange = vi.fn();
  let added: any;
  render(
    <DataSourcesEditProvider onAdd={(s) => { added = s; }}>
      <DataSourceSelect value="" dataSources={[]} onChange={onChange} />
    </DataSourcesEditProvider>,
  );

  const select = await screen.findByLabelText("Source de données");
  await screen.findByRole("option", { name: "Parcs partagés" });
  await userEvent.selectOptions(select, "Parcs partagés");

  expect(added).toMatchObject({ type: "features", service: "core", layer: "", datasetId: "ds-1" });
  expect(onChange).toHaveBeenCalledWith(added.id);
});

test("a shared dataset already referenced inline is not listed twice", async () => {
  server.use(
    http.get("https://core.test/items*", () =>
      HttpResponse.json({
        items: [{ pk: "ds-1", resourceType: "dataset", title: "Parcs partagés", abstract: "", owner: "alice", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-ds1", isPublished: true }],
        total: 1, page: 1, pageSize: 12,
      }),
    ),
  );
  render(
    <DataSourcesEditProvider onAdd={() => {}}>
      <DataSourceSelect
        value="s1"
        dataSources={[{ id: "s1", type: "features", service: "core", layer: "", datasetId: "ds-1", query: {} }]}
        onChange={() => {}}
      />
    </DataSourcesEditProvider>,
  );
  expect(screen.queryByRole("option", { name: "Parcs partagés" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd shell && npx vitest run src/builder/DataSourceSelect.test.tsx`
Expected: FAIL — `Cannot find module './DataSourcesEditContext'`.

- [ ] **Step 3: Create the context**

Create `shell/src/builder/DataSourcesEditContext.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { createContext, useContext, type ReactNode } from "react";
import type { DataSource } from "../api/types";

type AddDataSource = (source: DataSource) => void;

const AddDataSourceContext = createContext<AddDataSource | null>(null);

export function DataSourcesEditProvider({
  onAdd,
  children,
}: {
  onAdd: AddDataSource;
  children: ReactNode;
}) {
  return <AddDataSourceContext.Provider value={onAdd}>{children}</AddDataSourceContext.Provider>;
}

export function useAddDataSource(): AddDataSource | null {
  return useContext(AddDataSourceContext);
}
```

- [ ] **Step 4: Extend `DataSourceSelect`**

Replace the full content of `shell/src/builder/DataSourceSelect.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useItems } from "../api/hooks";
import type { DataSource } from "../api/types";
import { useAddDataSource } from "./DataSourcesEditContext";

export function DataSourceSelect({
  value,
  dataSources,
  onChange,
}: {
  value: string;
  dataSources: DataSource[];
  onChange: (id: string) => void;
}) {
  const addDataSource = useAddDataSource();
  const datasetsQuery = useItems({ type: "dataset", pageSize: 100 }, { enabled: Boolean(addDataSource) });
  const boundDatasetIds = new Set(dataSources.map((s) => s.datasetId).filter((id): id is string => Boolean(id)));
  const sharedDatasets = (datasetsQuery.data?.items ?? []).filter((d) => !boundDatasetIds.has(d.pk));

  function handleChange(raw: string) {
    if (raw.startsWith("dataset:")) {
      const pk = raw.slice("dataset:".length);
      const source: DataSource = {
        id: crypto.randomUUID(), type: "features", service: "core", layer: "", datasetId: pk, query: {},
      };
      addDataSource?.(source);
      onChange(source.id);
      return;
    }
    onChange(raw);
  }

  return (
    <label className="flex flex-col gap-1 text-sm">
      Source de données
      <select
        aria-label="Source de données"
        className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
        value={value}
        onChange={(e) => handleChange(e.target.value)}
      >
        <option value="">Aucune</option>
        {dataSources.map((s) => (
          <option key={s.id} value={s.id}>{s.layer || s.id}</option>
        ))}
        {sharedDatasets.length > 0 && (
          <optgroup label="Datasets partagés">
            {sharedDatasets.map((d) => (
              <option key={d.pk} value={`dataset:${d.pk}`}>{d.title}</option>
            ))}
          </optgroup>
        )}
      </select>
    </label>
  );
}
```

- [ ] **Step 5: Wire the provider in `AppBuilderPage`**

In `shell/src/pages/AppBuilderPage.tsx`, import the provider (alongside the `DataSourcePanel` import, line 9):
```tsx
import { DataSourcesEditProvider } from "../builder/DataSourcesEditContext";
```

Wrap the component's top-level returned JSX (the `<div className="flex h-full flex-col">...</div>` block) with the provider:
```tsx
  return (
    <DataSourcesEditProvider onAdd={(source) => setSources([...draft.dataSources, source])}>
      <div className="flex h-full flex-col">
        {/* ...unchanged content... */}
      </div>
    </DataSourcesEditProvider>
  );
```

(`draft` is narrowed non-null by the earlier `if (query.isError || !draft || !activeLayout || !activePage) return ...;` guard, exactly as the existing `setSources`/`setMessages` closures already rely on.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `cd shell && npx vitest run src/builder/DataSourceSelect.test.tsx src/pages/AppBuilderPage.test.tsx src/builder/widgets/chart.test.tsx src/builder/widgets/datasetCard.test.tsx && npm run build`
Expected: PASS — including the pre-existing chart/datasetCard widget tests (regression check that no widget file needed to change).

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/DataSourcesEditContext.tsx shell/src/builder/DataSourceSelect.tsx shell/src/builder/DataSourceSelect.test.tsx shell/src/pages/AppBuilderPage.tsx
git commit -m "feat(shell): list shared datasets in DataSourceSelect (SP-14a)"
```

---

### Task 11: E2E — create, edit, promote

**Files:**
- Create: `shell/e2e/datasets-shared.spec.ts`
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: the full stack built in Tasks 1–10.
- Produces: one Playwright spec covering catalogue creation → column editing → promotion from an app's `DataSourcePanel`.

- [ ] **Step 1: Add a `kind === "dataset"` branch to the shared `/configs` mock**

In `shell/e2e/mocks.ts`, inside the `**/configs` POST handler (around line 109–130), add a new branch before the final `else`:

```ts
    } else if (body?.config?.kind === "dataset") {
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
    } else {
```

This is the only shared-fixture change — every other dataset-specific route is registered locally in the new spec file (layered on top of `mockCore(page)`, using `route.fallback()` for anything it doesn't own, exactly like the existing `kind === "site"`/`kind === "map"` branches already coexist with the generic app/dashboard branch).

- [ ] **Step 2: Write the spec**

Create `shell/e2e/datasets-shared.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("create a dataset, edit a column label, then promote an app's inline source", async ({ page }) => {
  await mockCore(page);

  let datasetCreated = false;
  let datasetColumns: Record<string, unknown> = {};
  let promotePostedCollectionId: string | null = null;

  await page.route("**/collections", async (route) => {
    if (route.request().method() !== "GET") return route.fallback();
    await route.fulfill({
      json: {
        collections: [
          { id: "parcs", title: "Parcs", description: "", tableName: "parcs", isPublic: true, editable: true, geometryType: "Point", srid: 4326, pkColumn: "id", canWrite: true, featureCount: 3, owner: "alice" },
        ],
      },
    });
  });

  await page.route("**/collections/parcs/schema", async (route) => {
    await route.fulfill({
      json: { collection: "parcs", pk: "id", geometry: null, fields: [{ name: "nom", type: "string", required: true }] },
    });
  });

  await page.route("**/configs/by-item/dataset-1", async (route) => {
    if (route.request().method() === "PUT") {
      const body = await route.request().postDataJSON();
      datasetColumns = body.dataset.columns;
      await route.fulfill({ json: { id: "cfg-dataset", itemId: "dataset-1", kind: "dataset", dataset: body.dataset } });
      return;
    }
    await route.fulfill({
      json: {
        id: "cfg-dataset", itemId: "dataset-1", kind: "dataset",
        config: { kind: "dataset", dataset: { source: "collection", collectionId: "parcs", columns: datasetColumns } },
      },
    });
  });

  await page.route("https://core.test/items/dataset-1", async (route) => {
    await route.fulfill({
      json: { pk: "dataset-1", resourceType: "dataset", title: "Parcs partagés", abstract: "", owner: "mockuser", thumbnailUrl: null, date: "2026-01-01", configId: "cfg-dataset", isPublished: false, keywords: [] },
    });
  });

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      datasetCreated = true;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset", kind: "dataset", itemId: "dataset-1" } });
      return;
    }
    return route.fallback();
  });

  // 1. Créer un Dataset partagé depuis le catalogue.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("dataset");
  await dialog.getByLabel("Collection source").selectOption("parcs");
  await dialog.getByLabel("Titre").fill("Parcs partagés");
  await dialog.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/datasets\/dataset-1\/edit$/);
  expect(datasetCreated).toBe(true);

  // 2. Éditer le libellé d'une colonne et sauvegarder.
  await page.getByLabel("Libellé de nom").fill("Nom du parc");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => datasetColumns).toMatchObject({ nom: { label: "Nom du parc" } });

  // 3. Promouvoir une source inline depuis un nouvel App.
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Titre").fill("Carte des parcs");
  await dialog.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind === "dataset") {
      promotePostedCollectionId = body.config.dataset.collectionId;
      await route.fulfill({ status: 201, json: { id: "cfg-dataset-2", kind: "dataset", itemId: "dataset-2" } });
      return;
    }
    return route.fallback();
  });

  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");
  await page.getByRole("button", { name: /Promouvoir en dataset partagé/ }).click();

  await expect(page.getByText("Dataset partagé actif")).toBeVisible();
  expect(promotePostedCollectionId).toBe("parcs");
});
```

- [ ] **Step 3: Run the spec to verify it fails, then implement, then pass**

Run: `cd shell && VITE_AUTH_MODE=mock npx playwright test datasets-shared.spec.ts`
Expected first run (before this task's mocks.ts edit from Step 1 lands): FAIL at the "Nouveau" dialog step, since `"dataset"` isn't a valid `<option>` yet if Tasks 7–10 weren't already applied. Since Tasks 1–10 are already implemented by this point in the plan, the realistic failure mode is a mock-wiring mismatch (route not matched, wrong field name) — iterate on the spec/mocks until green.

Expected final: PASS.

- [ ] **Step 4: Run the full E2E and unit suites for regressions**

Run: `cd shell && npm run test && VITE_AUTH_MODE=mock npm run e2e`
Expected: PASS — all pre-existing Vitest (398+) and Playwright (18+1 new) specs green.

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/datasets-shared.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): E2E — create, edit, promote a shared dataset (SP-14a)"
```

---

## Self-Review Summary

- **Spec coverage:** §2 naming discipline → Global Constraints + every UI label written as "Dataset partagé"/"Collection source" (Task 7/8/9), never bare "Dataset". §3 core model → Task 1. §4 API reuse (no `/datasets/*`) → Task 1/2, explicitly a Global Constraint. §5 permissions (dataset `can()` independent of collection RLS) → Task 2 validates readability at save time; RLS itself is pre-existing and untouched, called out in Global Constraints. §6 shell creation/promotion → Tasks 7 (catalogue) and 9 (promote from builder). §7 consumption (`datasetId`, resolution, `DataSourceSelect`) → Tasks 3, 4, 10. §8 catalogue/search → free, nothing to build (noted, no task needed — `resource_type="dataset"` items flow through the existing pgvector/sharing pipelines automatically). §9 compatibility & tests → additive types (Task 3), new E2E (Task 11), core validation tests (Task 2). §10 risks → naming collision addressed (§2/Global Constraints), broken-collection-reference handled by existing `error` state patterns in `DatasetEditPage`/`schemaQuery.isError` (Task 8) and `queryDataSource` rejecting cleanly (Task 4), over-engineering explicitly fenced by Global Constraints' out-of-scope list.
- **Placeholder scan:** none — every step has literal file paths and complete code.
- **Type consistency:** `DatasetConfig`/`DatasetColumnMeta` (Task 3) used identically in Tasks 4, 5, 6, 8; `createDatasetItem`/`getDatasetConfig`/`saveDatasetConfig` names match across Tasks 3, 4, 6, 7, 8; `useCreateDataset`/`useDatasetConfig`/`useSaveDataset` match across Tasks 6, 7, 8; `DataSource.datasetId` matches across Tasks 3, 4, 9, 10; `DataSourcePanel`'s `onPromote`/`promotingId` match between Tasks 9's component and `AppBuilderPage` wiring; `DataSourcesEditProvider`/`useAddDataSource` match between Task 10's new file and its two consumers.
