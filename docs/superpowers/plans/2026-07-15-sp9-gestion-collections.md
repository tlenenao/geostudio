# SP-9 — Gestion des collections (UI admin) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An admin manages the full lifecycle of a collection (list, register a candidate PostGIS table, edit, share, unregister) from the shell — a UI façade over already-authorized, already-audited core routes, with zero new permission model.

**Architecture:** One new core endpoint (`GET /collections/candidates`, admin-only, reusing the existing `Introspector`) plus one extension of an existing endpoint (`GET /collections` gains an `owner` field). Everything else needed already exists in the core (`POST/GET/PATCH/DELETE /collections`, `GET/PUT /collections/{id}/sharing`). On the shell side: 7 new `ItemClient` methods/hooks following the exact patterns already used for extensions admin (SP-8c) and item sharing, one new admin page (`/admin/collections`), three dialogs, and a nav-link split (the single "Administration" link becomes "Extensions" + "Collections").

**Tech Stack:** FastAPI/SQLAlchemy (core), React/TypeScript/react-query/Vite (shell), pytest (core tests), Vitest + MSW (shell unit tests), Playwright (E2E, `VITE_AUTH_MODE=mock`).

## Global Constraints

- Spec of record: `docs/superpowers/specs/2026-07-13-sp9-gestion-collections-design.md`. Where this plan deviates from that spec's wording, the deviation is called out explicitly in the task text — it follows conventions established in the codebase *after* the spec was written (SP-8c, same day), which take precedence per "follow existing patterns."
- No new permission model. The frontier of security stays the existing server-side `403`s (`_require_admin` in `core/app/collections/routes.py` and `core/app/auth/routes.py`). All client-side admin gating (`isAdmin` check) is a fail-open UX convenience, never enforced as a security boundary.
- `GET /me` already returns `isAdmin` (delivered in SP-8c) — do not re-implement it. Verify it, don't touch it.
- Every new/changed file must keep the existing test suites green: **384 core tests / 445 shell tests / 34 E2E specs** (baseline before this plan; exact numbers will grow task by task — verify by running the full suite at the end of each task, not just the new file).
- Core: SQLite fixtures for unit/authorization tests (existing `env` pattern in `core/tests/test_collections_routes.py`); real PostGIS for anything that needs genuine `information_schema` introspection or cross-tenant isolation (`@pytest.mark.postgis`, `CORE_TEST_DATABASE_URL`).
- Shell: MSW for `itemClient.ts`/hook tests, React Testing Library for component tests, Playwright with `mockCore` + per-spec `page.route` overrides for E2E (host-scoped routes for anything that also matches a shell client-side path, e.g. `/admin/collections` itself — see Task 7).

---

## File Structure

**Core:**
- `core/app/collections/introspection_pg.py` — add `list_public_tables(session) -> list[str]`.
- `core/app/collections/routes.py` — add `get_table_lister` dependency, `GET /collections/candidates` route (declared **before** `GET /collections/{collection_id}` to avoid Starlette matching `candidates` as a path param), extend `_collection_json`/`list_collections` with an `owner` field.
- `core/tests/test_introspection_pg.py` — unit test for `list_public_tables` (real Postgres).
- `core/tests/test_collections_routes.py` — SQLite unit tests for the new route (admin guard, registrable/unsupported, owner field on `GET /collections`).
- `core/tests/test_collections_candidates_integration.py` (new) — real-Postgres end-to-end test (real introspection, cross-tenant isolation).

**Shell:**
- `shell/src/api/types.ts` — `CollectionAdmin`, `CandidateTable` types; extend `ItemClient` interface.
- `shell/src/api/itemClient.ts` — implement the 7 new methods.
- `shell/src/api/itemClient.test.ts` — MSW tests for the 7 new methods.
- `shell/src/api/hooks.ts` — 7 new hooks.
- `shell/src/api/hooks.test.tsx` — tests for the 3 query hooks (mutations are covered indirectly through the dialogs that use them, matching this file's existing convention).
- `shell/src/pages/CollectionsAdminPage.tsx` (new) + `CollectionsAdminPage.test.tsx` (new).
- `shell/src/shell/RegisterCollectionDialog.tsx` (new) + test.
- `shell/src/shell/EditCollectionDialog.tsx` (new) + test.
- `shell/src/shell/CollectionShareDialog.tsx` (new) + test.
- `shell/src/shell/routes.tsx` — add `/admin/collections` route.
- `shell/src/shell/AppLayout.tsx` + `AppLayout.test.tsx` — split the "Administration" link into "Extensions" + "Collections".
- `shell/e2e/admin-extensions.spec.ts` — update the two `"Administration"` link assertions to `"Extensions"` (renamed, not removed).
- `shell/e2e/admin-collections.spec.ts` (new).

---

### Task 1: Core — `GET /collections/candidates` + owner field on `GET /collections`

**Files:**
- Modify: `core/app/collections/introspection_pg.py`
- Modify: `core/app/collections/routes.py`
- Test: `core/tests/test_introspection_pg.py`
- Test: `core/tests/test_collections_routes.py`
- Test: `core/tests/test_collections_candidates_integration.py` (new)

**Interfaces:**
- Produces: `list_public_tables(session: Session) -> list[str]` (in `introspection_pg.py`) — every base table in schema `public`, alphabetically ordered.
- Produces: `GET /collections/candidates` → `{"candidates": [{"tableName": str, "registrable": true, "geometryType": str|None, "srid": int|None, "columnCount": int} | {"tableName": str, "registrable": false, "reason": str}]}`.
- Produces: `GET /collections` items gain `"owner": str | None` (the owning user's `username`, `None` only if the owner row is somehow missing — should not happen in practice).

- [ ] **Step 1: Write the failing test for `list_public_tables`**

Append to `core/tests/test_introspection_pg.py`:

```python
from app.collections.introspection_pg import introspect_table, list_public_tables


def test_lists_public_base_tables_only(pg_session, pg_engine):
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS t_extra"))
        conn.execute(text("DROP VIEW IF EXISTS t_a_view"))
        conn.execute(text("CREATE TABLE t_extra (id serial PRIMARY KEY)"))
        conn.execute(text("CREATE VIEW t_a_view AS SELECT id FROM t_extra"))
    try:
        names = list_public_tables(pg_session)
        assert "t_incidents" in names  # from the pg_session fixture
        assert "t_extra" in names
        assert "t_a_view" not in names  # views are excluded
    finally:
        with pg_engine.begin() as conn:
            conn.execute(text("DROP VIEW IF EXISTS t_a_view"))
            conn.execute(text("DROP TABLE IF EXISTS t_extra"))
```

(`introspect_table` was already imported at the top of the file — this adds `list_public_tables` to the same import line.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_introspection_pg.py::test_lists_public_base_tables_only -v`
Expected: FAIL with `ImportError: cannot import name 'list_public_tables'`.

- [ ] **Step 3: Implement `list_public_tables`**

Add to `core/app/collections/introspection_pg.py` (after the existing imports, before `_TYPE_MAP`):

```python
def list_public_tables(session: Session) -> list[str]:
    rows = session.execute(text(
        "SELECT table_name FROM information_schema.tables "
        "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
        "ORDER BY table_name"
    )).scalars().all()
    return list(rows)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_introspection_pg.py -v`
Expected: PASS (all tests in the file, including the new one).

- [ ] **Step 5: Write the failing SQLite tests for the route and the owner field**

In `core/tests/test_collections_routes.py`, change the import line at the top:

```python
from app.collections.introspection import ColumnInfo, TableInfo, TableNotFound, UnsupportedTable
```

Append at the end of the file:

```python
def test_candidates_requires_admin(env):
    app, client, _, admin, regular, _ddl = env
    _as(app, regular)
    assert client.get("/collections/candidates").status_code == 403


def test_candidates_lists_registrable_and_unsupported_excludes_core_and_registered(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})  # already registered

    def fake_lister(session):
        return ["incidents", "widgets", "items"]  # "items" is a core table

    def fake_introspector_2(session, table_name):
        if table_name == "incidents":
            return INCIDENTS
        if table_name == "widgets":
            raise UnsupportedTable("table has no primary key")
        raise TableNotFound(table_name)

    app.dependency_overrides[collections_routes.get_table_lister] = lambda: fake_lister
    app.dependency_overrides[collections_routes.get_introspector] = lambda: fake_introspector_2

    r = client.get("/collections/candidates")
    assert r.status_code == 200
    assert r.json()["candidates"] == [
        {"tableName": "widgets", "registrable": False, "reason": "table has no primary key"},
    ]


def test_list_collections_includes_owner_username(env):
    app, client, _, admin, _regular, _ddl = env
    _as(app, admin)
    client.post("/collections", json={"tableName": "incidents"})
    body = client.get("/collections").json()
    assert body["collections"][0]["owner"] == "admin"
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v -k "candidates or owner_username"`
Expected: FAIL — `test_candidates_requires_admin` and the other candidates test fail with 404 (route doesn't exist yet, `collections_routes.get_table_lister` also doesn't exist → `AttributeError`); `test_list_collections_includes_owner_username` fails with `KeyError: 'owner'`.

- [ ] **Step 7: Implement the route and the owner field**

In `core/app/collections/routes.py`, change the top-level import line:

```python
from sqlalchemy import select
```
(add this new import line right after `from fastapi import APIRouter, Depends, HTTPException, Request`)

Modify `_collection_json` to accept an optional `owner`:

```python
def _collection_json(col, can_write: bool, owner: str | None = None) -> dict:
    return {
        "id": col.id, "title": col.title, "description": col.description,
        "tableName": col.table_name, "isPublic": col.is_public, "editable": col.editable,
        "geometryType": col.geometry_type, "srid": col.srid, "pkColumn": col.pk_column,
        "canWrite": can_write, "featureCount": col.feature_count, "owner": owner,
    }
```

Add a new dependency right after `get_ddl_applier`:

```python
def get_table_lister() -> Callable[[Session], list[str]]:  # overridé en test
    from app.collections.introspection_pg import list_public_tables
    return list_public_tables
```

Replace the body of `list_collections` (around line 179-190) to resolve owner usernames in bulk:

```python
@router.get("/collections")
def list_collections(
    q: str | None = None,
    user=Depends(get_current_user_optional), session: Session = Depends(get_session),
):
    from app.tenants.repository import get_or_create_default_tenant
    from app.users.models import User
    tenant_id = user.tenant_id if user else get_or_create_default_tenant(session).id
    cols = repo.list_visible_collections(
        session, tenant_id=tenant_id, user_id=user.id if user else None,
        is_admin=bool(user and user.is_admin), q=q,
    )
    owner_ids = {c.owner_id for c in cols}
    owners = dict(session.execute(
        select(User.id, User.username).where(User.id.in_(owner_ids))
    ).all()) if owner_ids else {}
    return {"collections": [
        _collection_json(c, _can_write_collection(session, user, c), owner=owners.get(c.owner_id))
        for c in cols
    ]}
```

Insert the new route **immediately after** `list_collections` and **before** `get_collection` (i.e. before the `@router.get("/collections/{collection_id}")` line — this ordering is load-bearing: Starlette matches routes in registration order, and a `{collection_id}` route declared first would swallow `/collections/candidates` as `collection_id="candidates"`):

```python
@router.get("/collections/candidates")
def list_candidate_tables(
    user=Depends(get_current_user), session: Session = Depends(get_session),
    list_tables: Callable[[Session], list[str]] = Depends(get_table_lister),
    introspect: Introspector = Depends(get_introspector),
):
    _require_admin(user)
    core = _core_tables()
    candidates = []
    for table_name in list_tables(session):
        if table_name in core:
            continue
        if repo.get_collection(session, tenant_id=user.tenant_id, collection_id=table_name) is not None:
            continue
        try:
            info = introspect(session, table_name)
        except UnsupportedTable as exc:
            candidates.append({"tableName": table_name, "registrable": False, "reason": exc.reason})
            continue
        except TableNotFound:
            continue  # can't happen by construction: table_name came from list_tables itself
        candidates.append({
            "tableName": table_name, "registrable": True,
            "geometryType": info.geometry_type, "srid": info.srid,
            "columnCount": len(info.columns),
        })
    return {"candidates": candidates}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd core && uv run pytest tests/test_collections_routes.py -v`
Expected: PASS (all tests in the file — the new ones plus all pre-existing ones, unaffected).

- [ ] **Step 9: Write and run the real-Postgres integration test**

Create `core/tests/test_collections_candidates_integration.py`:

```python
"""Bout en bout sur PostGIS réel : /collections/candidates avec la vraie
introspection Postgres (information_schema.tables), pas de fake — même
patron que test_features_integration.py (Base.metadata.create_all sur
pg_engine, teardown TRUNCATE + DROP des tables jetables)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import db
from app.auth.dependency import get_current_user, get_current_user_optional
from app.db import Base, init_db, make_session_factory, request_scoped_session
from app.main import create_app
from app.tenants.models import Tenant
from app.tenants.repository import get_or_create_default_tenant
from app.users.repository import get_or_create_user

pytestmark = pytest.mark.postgis


@pytest.fixture()
def pg_app(pg_engine):
    Base.metadata.create_all(pg_engine)
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS cand_points"))
        conn.execute(text("DROP TABLE IF EXISTS cand_no_pk"))
        conn.execute(text(
            "CREATE TABLE cand_points (id serial PRIMARY KEY, "
            "titre text NOT NULL, geom geometry(Point, 4326))"))
        conn.execute(text("CREATE TABLE cand_no_pk (a int, b int)"))
    Session = make_session_factory(pg_engine)
    with Session() as s:
        tenant_a = get_or_create_default_tenant(s)
        admin_a = get_or_create_user(s, tenant_id=tenant_a.id, oidc_sub="a", username="admin-a",
                                     email=None, first_name="", last_name="", bootstrap_admin=True)
        tenant_b = Tenant(id="tenant-b-candidates", slug="tenant-b-candidates", name="Tenant B")
        s.add(tenant_b)
        s.flush()
        admin_b = get_or_create_user(s, tenant_id=tenant_b.id, oidc_sub="b", username="admin-b",
                                     email=None, first_name="", last_name="", bootstrap_admin=True)
        s.commit()
    app = create_app()

    def override_session():
        with request_scoped_session(Session) as session:
            yield session

    app.dependency_overrides[db.get_session] = override_session
    client = TestClient(app)
    yield client, app, admin_a, admin_b
    with pg_engine.begin() as conn:
        conn.execute(text("DROP TABLE IF EXISTS cand_points"))
        conn.execute(text("DROP TABLE IF EXISTS cand_no_pk"))
        conn.execute(text(
            "TRUNCATE collection_shares, collections, audit_log, users, tenants CASCADE"))


def _as(app, user):
    app.dependency_overrides[get_current_user] = lambda: user
    app.dependency_overrides[get_current_user_optional] = lambda: user


def test_candidates_real_introspection_and_tenant_isolation(pg_app):
    client, app, admin_a, admin_b = pg_app
    _as(app, admin_a)
    body = client.get("/collections/candidates").json()["candidates"]
    by_name = {c["tableName"]: c for c in body}
    assert by_name["cand_points"]["registrable"] is True
    assert by_name["cand_points"]["geometryType"] == "Point"
    assert by_name["cand_no_pk"]["registrable"] is False
    assert by_name["cand_no_pk"]["reason"] == "table has no primary key"

    assert client.post("/collections", json={"tableName": "cand_points"}).status_code == 201
    body_a = client.get("/collections/candidates").json()["candidates"]
    assert "cand_points" not in {c["tableName"] for c in body_a}

    _as(app, admin_b)
    body_b = client.get("/collections/candidates").json()["candidates"]
    assert "cand_points" in {c["tableName"] for c in body_b}
```

Run: `cd core && CORE_TEST_DATABASE_URL=<url> uv run pytest tests/test_collections_candidates_integration.py -v`
Expected: PASS.

- [ ] **Step 10: Run the full core suite and lint-imports**

Run: `cd core && uv run pytest && uv run lint-imports`
Expected: all pass (SQLite run — the postgis-marked tests skip without `CORE_TEST_DATABASE_URL`, that's expected locally; re-run once more with `CORE_TEST_DATABASE_URL` set to confirm the postgis subset too).

- [ ] **Step 11: Commit**

```bash
git add core/app/collections/introspection_pg.py core/app/collections/routes.py \
        core/tests/test_introspection_pg.py core/tests/test_collections_routes.py \
        core/tests/test_collections_candidates_integration.py
git commit -m "feat(core): GET /collections/candidates + owner field on GET /collections"
```

---

### Task 2: Shell — `CollectionAdmin`/`CandidateTable` types + `ItemClient` data layer

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts`

**Interfaces:**
- Consumes: Task 1's `GET /collections` (now includes `owner`), `GET /collections/candidates`, and the pre-existing `POST/PATCH/DELETE /collections`, `GET/PUT /collections/{id}/sharing`.
- Produces (for Task 3+): `ItemClient.listCollections(): Promise<CollectionAdmin[]>`, `.listCandidateTables(): Promise<CandidateTable[]>`, `.createCollection(input): Promise<CollectionAdmin>`, `.updateCollection(id, patch): Promise<CollectionAdmin>`, `.deleteCollection(id): Promise<void>`, `.getCollectionSharing(id): Promise<Sharing>`, `.setCollectionSharing(id, sharing): Promise<void>`.

- [ ] **Step 1: Add the types**

In `shell/src/api/types.ts`, add after `export type AdminExtension = ExtensionManifest & { enabled: boolean };`:

```ts
export type CollectionAdmin = {
  id: string;
  title: string;
  description: string;
  tableName: string;
  isPublic: boolean;
  editable: boolean;
  geometryType: string | null;
  srid: number | null;
  pkColumn: string;
  canWrite: boolean;
  featureCount: number | null;
  owner: string | null;
};

export type CandidateTable =
  | { tableName: string; registrable: true; geometryType: string | null; srid: number | null; columnCount: number }
  | { tableName: string; registrable: false; reason: string };

export type CollectionCreateInput = {
  tableName: string;
  title?: string;
  description?: string;
  isPublic?: boolean;
};

export type CollectionPatchInput = {
  title?: string;
  description?: string;
  isPublic?: boolean;
  editable?: boolean;
};
```

Extend the `ItemClient` interface (add after the `setExtensionEnabled` line):

```ts
  listCollections(): Promise<CollectionAdmin[]>;
  listCandidateTables(): Promise<CandidateTable[]>;
  createCollection(input: CollectionCreateInput): Promise<CollectionAdmin>;
  updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin>;
  deleteCollection(id: string): Promise<void>;
  getCollectionSharing(id: string): Promise<Sharing>;
  setCollectionSharing(id: string, sharing: Sharing): Promise<void>;
```

- [ ] **Step 2: Write the failing MSW tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("listCollections returns the admin collection shape including owner", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
  );
  const result = await makeClient().listCollections();
  expect(result).toEqual([
    {
      id: "incidents", title: "Incidents", description: "", tableName: "incidents",
      isPublic: false, editable: true, geometryType: "Point", srid: 4326,
      pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
    },
  ]);
});

test("listCandidateTables returns the candidates array as-is", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
        ],
      }),
    ),
  );
  const result = await makeClient().listCandidateTables();
  expect(result).toEqual([
    { tableName: "widgets", registrable: false, reason: "table has no primary key" },
    { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
  ]);
});

test("createCollection POSTs the input and returns the created collection", async () => {
  let body: unknown;
  server.use(
    http.post("https://core.test/collections", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "Points d'intérêt", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  const result = await makeClient().createCollection({ tableName: "points_interet", title: "Points d'intérêt" });
  expect(body).toEqual({ tableName: "points_interet", title: "Points d'intérêt" });
  expect(result.id).toBe("points_interet");
});

test("updateCollection PATCHes the patch and returns the updated collection", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "incidents", title: "Incidents (v2)", description: "", tableName: "incidents",
        isPublic: true, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
      });
    }),
  );
  const result = await makeClient().updateCollection("incidents", { title: "Incidents (v2)", isPublic: true });
  expect(body).toEqual({ title: "Incidents (v2)", isPublic: true });
  expect(result.title).toBe("Incidents (v2)");
});

test("deleteCollection DELETEs the collection", async () => {
  let called = false;
  server.use(
    http.delete("https://core.test/collections/incidents", () => {
      called = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteCollection("incidents");
  expect(called).toBe(true);
});

test("getCollectionSharing passes through the core's Sharing shape directly", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [{ groupId: "g1", role: "editor" }] }),
    ),
  );
  const result = await makeClient().getCollectionSharing("incidents");
  expect(result).toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
});

test("setCollectionSharing PUTs the sharing object as-is", async () => {
  let body: unknown;
  server.use(
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ public: false, groups: [] });
    }),
  );
  await makeClient().setCollectionSharing("incidents", { public: false, groups: [{ groupId: "g1", role: "viewer" }] });
  expect(body).toEqual({ public: false, groups: [{ groupId: "g1", role: "viewer" }] });
});
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `cd shell && npm run test -- itemClient.test.ts`
Expected: FAIL with `TypeError: makeClient(...).listCollections is not a function` (and equivalents for the other 6).

- [ ] **Step 4: Implement the 7 methods**

In `shell/src/api/itemClient.ts`, update the top import line to include the new types:

```ts
import type { ActionMessage, AdminExtension, AppConfig, CandidateTable, CollectionAdmin, CollectionCreateInput, CollectionPatchInput, CollectionSchema, CreateKind, DataRecord, DataSource, ExtensionManifest, FieldError, GeoJSONFeatureInput, Group, Item, ItemClient, ItemPage, LayerSource, ListItemsParams, MapConfig, MapLayer, Me, Page, ResourceType, Sharing, Theme, UpdatePatch, Variable } from "./types";
```

Add the 7 methods to the returned object, right after `setExtensionEnabled` (around line 383):

```ts
    async listCollections(): Promise<CollectionAdmin[]> {
      const data = await request<{ collections: CollectionAdmin[] }>("GET", `/collections`);
      return data.collections ?? [];
    },

    async listCandidateTables(): Promise<CandidateTable[]> {
      const data = await request<{ candidates: CandidateTable[] }>("GET", `/collections/candidates`);
      return data.candidates ?? [];
    },

    async createCollection(input: CollectionCreateInput): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("POST", `/collections`, input);
    },

    async updateCollection(id: string, patch: CollectionPatchInput): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("PATCH", `/collections/${id}`, patch);
    },

    async deleteCollection(id: string): Promise<void> {
      await request<void>("DELETE", `/collections/${id}`);
    },

    async getCollectionSharing(id: string): Promise<Sharing> {
      return request<Sharing>("GET", `/collections/${id}/sharing`);
    },

    async setCollectionSharing(id: string, sharing: Sharing): Promise<void> {
      await request<void>("PUT", `/collections/${id}/sharing`, sharing);
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npm run test -- itemClient.test.ts`
Expected: PASS (all tests in the file — new ones plus pre-existing, unaffected).

- [ ] **Step 6: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all pass, `tsc --noEmit` clean.

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): ItemClient collections-admin methods (list/candidates/create/update/delete/sharing)"
```

---

### Task 3: Shell — react-query hooks

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Modify: `shell/src/api/hooks.test.tsx`

**Interfaces:**
- Consumes: Task 2's 7 `ItemClient` methods.
- Produces (for Task 4+): `useCollectionsAdmin(options?)`, `useCandidateTables(options?)`, `useCreateCollection()`, `useUpdateCollection(id)`, `useDeleteCollection()`, `useCollectionSharing(id, options?)`, `useSetCollectionSharing(id)`.

- [ ] **Step 1: Write the failing tests for the 3 query hooks**

In `shell/src/api/hooks.test.tsx`, extend the import line:

```ts
import { useAppConfig, useCandidateTables, useCollectionSharing, useCollectionsAdmin, useCreateItem, useCreateMap, useDeleteItem, useGroups, useItems, useMapConfig, useMe, useSaveApp, useSaveMap, useSharing, useUpdateItem } from "./hooks";
```

Append at the end of the file:

```ts
test("useCollectionsAdmin returns the mapped collections", async () => {
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
  );
  const { result } = renderHook(() => useCollectionsAdmin(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]?.owner).toBe("admin");
});

test("useCandidateTables returns the candidates list", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "widgets", registrable: false, reason: "table has no primary key" }],
      }),
    ),
  );
  const { result } = renderHook(() => useCandidateTables(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual([
    { tableName: "widgets", registrable: false, reason: "table has no primary key" },
  ]);
});

test("useCollectionSharing returns the collection's sharing", async () => {
  server.use(
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: true, groups: [] }),
    ),
  );
  const { result } = renderHook(() => useCollectionSharing("incidents"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data).toEqual({ public: true, groups: [] });
});
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npm run test -- hooks.test.tsx`
Expected: FAIL — `useCollectionsAdmin`/`useCandidateTables`/`useCollectionSharing` are not exported from `./hooks`.

- [ ] **Step 3: Implement the 7 hooks**

Add to `shell/src/api/hooks.ts`, at the end of the file (after `useSetExtensionEnabled`). Extend the top type import to add `CollectionCreateInput, CollectionPatchInput`:

```ts
import type { AppConfig, CollectionCreateInput, CollectionPatchInput, CreateKind, Item, ItemPage, ListItemsParams, MapConfig, Sharing, UpdatePatch } from "./types";
```

```ts
export function useCollectionsAdmin(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collections", "admin"],
    queryFn: () => client.listCollections(),
    enabled: options?.enabled ?? true,
  });
}

export function useCandidateTables(options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collections", "candidates"],
    queryFn: () => client.listCandidateTables(),
    enabled: options?.enabled ?? true,
  });
}

export function useCreateCollection() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CollectionCreateInput) => client.createCollection(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useUpdateCollection(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: CollectionPatchInput) => client.updateCollection(id, patch),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
    },
  });
}

export function useDeleteCollection() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => client.deleteCollection(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collections", "admin"] });
      queryClient.invalidateQueries({ queryKey: ["collections", "candidates"] });
    },
  });
}

export function useCollectionSharing(id: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["collection-sharing", id],
    queryFn: () => client.getCollectionSharing(id),
    enabled: options?.enabled ?? true,
  });
}

export function useSetCollectionSharing(id: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sharing: Sharing) => client.setCollectionSharing(id, sharing),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["collection-sharing", id] });
    },
  });
}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npm run test -- hooks.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all pass, clean typecheck.

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): collections-admin react-query hooks"
```

---

### Task 4: Shell — `CollectionsAdminPage` (list) + `RegisterCollectionDialog` (create flow)

**Files:**
- Create: `shell/src/shell/RegisterCollectionDialog.tsx`
- Create: `shell/src/shell/RegisterCollectionDialog.test.tsx`
- Create: `shell/src/pages/CollectionsAdminPage.tsx`
- Create: `shell/src/pages/CollectionsAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useMe`, `useCollectionsAdmin`, `useCandidateTables`, `useCreateCollection` (Task 3); `CollectionAdmin`, `CandidateTable` (Task 2); `Dialog`, `Button`, `Input` (`shell/src/ui/`).
- Produces (for Task 5+): `CollectionsAdminPage` (default export style not used in this codebase — named export, matches `AdminExtensionsPage`), `RegisterCollectionDialog({ open, onClose })`.

- [ ] **Step 1: Write the failing test for `RegisterCollectionDialog`**

Create `shell/src/shell/RegisterCollectionDialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { RegisterCollectionDialog } from "./RegisterCollectionDialog";

function Harness({ open = true, onClose = () => {} }: { open?: boolean; onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <RegisterCollectionDialog open={open} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an empty-state message when there are no candidate tables", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByText(/Aucune table à enregistrer/)).toBeInTheDocument(),
  );
});

test("disables a non-registrable candidate and shows its reason", async () => {
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
        ],
      }),
    ),
  );
  render(<Harness />);
  // findByLabelText itself polls until the <select> mounts, which only
  // happens once candidatesQuery.data is populated with both options — by
  // the time this resolves, both <option> elements are already rendered.
  await screen.findByLabelText("Table");
  const widgetsOption = screen.getByRole("option", { name: /widgets.*table has no primary key/ });
  expect(widgetsOption).toBeDisabled();
  const poiOption = screen.getByRole("option", { name: "points_interet" });
  expect(poiOption).not.toBeDisabled();
});

test("submits the chosen table and closes on success", async () => {
  let body: unknown;
  server.use(
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.post("https://core.test/collections", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "Points d'intérêt", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.type(screen.getByLabelText("Titre"), "Points d'intérêt");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  // isPublic is always sent (a real `false`, not `undefined`, so
  // JSON.stringify keeps the key) — only title/description drop out when
  // left blank, since `"".trim() || undefined` turns an empty string into
  // an actually-undefined value.
  expect(body).toEqual({ tableName: "points_interet", title: "Points d'intérêt", isPublic: false });
});
```

(`vi` is imported explicitly from `"vitest"` above even though `globals: true` makes `test`/`expect`/`describe` ambient — this matches the existing convention in `shell/src/shell/ItemActions.test.tsx:4`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- RegisterCollectionDialog.test.tsx`
Expected: FAIL — cannot find module `./RegisterCollectionDialog`.

- [ ] **Step 3: Implement `RegisterCollectionDialog`**

Create `shell/src/shell/RegisterCollectionDialog.tsx`:

```tsx
import { useState } from "react";
import { useCandidateTables, useCreateCollection } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function RegisterCollectionDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
  const candidatesQuery = useCandidateTables({ enabled: open });
  const createCollection = useCreateCollection();
  const [tableName, setTableName] = useState("");
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [isPublic, setIsPublic] = useState(false);

  function close() {
    setTableName("");
    setTitle("");
    setDescription("");
    setIsPublic(false);
    createCollection.reset();
    onClose();
  }

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!tableName) return;
    try {
      await createCollection.mutateAsync({
        tableName,
        title: title.trim() || undefined,
        description: description.trim() || undefined,
        isPublic,
      });
      close();
    } catch {
      // surfaced via createCollection.isError
    }
  }

  return (
    <Dialog open={open} onClose={close} title="Enregistrer une table">
      {candidatesQuery.isLoading && <p role="status">Chargement…</p>}
      {candidatesQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des tables candidates.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length === 0 && (
        <p className="text-sm text-slate-600">
          Aucune table à enregistrer — toutes les tables éligibles du schéma
          public sont déjà des collections, ou importez un fichier depuis le
          catalogue.
        </p>
      )}
      {candidatesQuery.data && candidatesQuery.data.length > 0 && (
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Table
            <select
              aria-label="Table"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={tableName}
              onChange={(e) => setTableName(e.target.value)}
            >
              <option value="" />
              {candidatesQuery.data.map((c) => (
                <option key={c.tableName} value={c.tableName} disabled={!c.registrable}>
                  {c.registrable ? c.tableName : `${c.tableName} (${c.reason})`}
                </option>
              ))}
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Description
            <Input aria-label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
          </label>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public
          </label>
          {createCollection.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec de l'enregistrement.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={close}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={!tableName || createCollection.isPending}>
              Enregistrer
            </Button>
          </div>
        </form>
      )}
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- RegisterCollectionDialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing test for `CollectionsAdminPage`**

Create `shell/src/pages/CollectionsAdminPage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CollectionsAdminPage } from "./CollectionsAdminPage";

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <CollectionsAdminPage />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows an access-denied message and never calls /collections when the user is not admin", async () => {
  let collectionsCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: false }),
    ),
    http.get("https://core.test/collections", () => {
      collectionsCalled = true;
      return HttpResponse.json({ collections: [] });
    }),
  );
  render(<Harness />);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Accès réservé aux administrateurs."),
  );
  expect(collectionsCalled).toBe(false);
});

test("lists collections and registers a new one via the dialog", async () => {
  let posted: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () =>
      HttpResponse.json({
        candidates: [{ tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 }],
      }),
    ),
    http.post("https://core.test/collections", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        id: "points_interet", title: "points_interet", description: "", tableName: "points_interet",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 0, owner: "admin",
      });
    }),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  expect(screen.getByText("admin")).toBeInTheDocument(); // owner column

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  // No title typed here — isPublic is still always sent (a real `false`,
  // never dropped by JSON.stringify), only the untouched title/description
  // fields drop out (empty string → undefined via `.trim() || undefined`).
  await waitFor(() => expect(posted).toEqual({ tableName: "points_interet", isPublic: false }));
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: FAIL — cannot find module `./CollectionsAdminPage`.

- [ ] **Step 7: Implement `CollectionsAdminPage`**

Create `shell/src/pages/CollectionsAdminPage.tsx`:

```tsx
import { useState } from "react";
import { useCollectionsAdmin, useMe } from "../api/hooks";
import { Button } from "../ui/button";
import { RegisterCollectionDialog } from "../shell/RegisterCollectionDialog";

export function CollectionsAdminPage() {
  const meQuery = useMe();
  const collectionsQuery = useCollectionsAdmin({ enabled: meQuery.data?.isAdmin === true });
  const [registerOpen, setRegisterOpen] = useState(false);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">Collections</h1>
        <Button size="sm" onClick={() => setRegisterOpen(true)}>
          Enregistrer une table
        </Button>
      </div>
      {collectionsQuery.isLoading && <p role="status">Chargement…</p>}
      {collectionsQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des collections.
        </p>
      )}
      {collectionsQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Titre</th>
              <th className="py-2">Table</th>
              <th className="py-2">Public</th>
              <th className="py-2">Éditable</th>
              <th className="py-2">Entités</th>
              <th className="py-2">Propriétaire</th>
            </tr>
          </thead>
          <tbody>
            {collectionsQuery.data.map((col) => (
              <tr key={col.id} className="border-b border-slate-100">
                <td className="py-2">{col.title}</td>
                <td className="py-2 text-xs text-slate-500">{col.tableName}</td>
                <td className="py-2">{col.isPublic ? "Oui" : "Non"}</td>
                <td className="py-2">{col.editable ? "Oui" : "Non"}</td>
                <td className="py-2">{col.featureCount ?? "—"}</td>
                <td className="py-2">{col.owner ?? "—"}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RegisterCollectionDialog open={registerOpen} onClose={() => setRegisterOpen(false)} />
    </div>
  );
}
```

- [ ] **Step 8: Run test to verify it passes**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: PASS.

- [ ] **Step 9: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all pass, clean typecheck.

- [ ] **Step 10: Commit**

```bash
git add shell/src/shell/RegisterCollectionDialog.tsx shell/src/shell/RegisterCollectionDialog.test.tsx \
        shell/src/pages/CollectionsAdminPage.tsx shell/src/pages/CollectionsAdminPage.test.tsx
git commit -m "feat(shell): CollectionsAdminPage list + RegisterCollectionDialog (create flow)"
```

---

### Task 5: Shell — `EditCollectionDialog` + delete via `ConfirmDialog`

**Files:**
- Create: `shell/src/shell/EditCollectionDialog.tsx`
- Create: `shell/src/shell/EditCollectionDialog.test.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useUpdateCollection`, `useDeleteCollection` (Task 3); `CollectionAdmin` (Task 2); `ConfirmDialog` (`shell/src/ui/ConfirmDialog.tsx`, pre-existing, unmodified).
- Produces: `EditCollectionDialog({ collection, open, onClose })`.

- [ ] **Step 1: Write the failing test for `EditCollectionDialog`**

Create `shell/src/shell/EditCollectionDialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionAdmin } from "../api/types";
import { EditCollectionDialog } from "./EditCollectionDialog";

const COLLECTION: CollectionAdmin = {
  id: "incidents", title: "Incidents", description: "Signalements", tableName: "incidents",
  isPublic: false, editable: true, geometryType: "Point", srid: 4326,
  pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
};

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <EditCollectionDialog collection={COLLECTION} open={true} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("pre-fills the form from the collection and PATCHes the edited fields on submit", async () => {
  let body: unknown;
  server.use(
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ ...COLLECTION, title: "Incidents (v2)", isPublic: true });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  const titleInput = screen.getByLabelText("Titre") as HTMLInputElement;
  expect(titleInput.value).toBe("Incidents");
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(body).toEqual({
    title: "Incidents (v2)", description: "Signalements", isPublic: true, editable: true,
  });
});

test("surfaces an alert when the PATCH fails", async () => {
  server.use(
    http.patch("https://core.test/collections/incidents", () => HttpResponse.json({}, { status: 500 })),
  );
  render(<Harness />);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour."),
  );
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- EditCollectionDialog.test.tsx`
Expected: FAIL — cannot find module `./EditCollectionDialog`.

- [ ] **Step 3: Implement `EditCollectionDialog`**

Create `shell/src/shell/EditCollectionDialog.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useUpdateCollection } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";

export function EditCollectionDialog({
  collection,
  open,
  onClose,
}: {
  collection: CollectionAdmin;
  open: boolean;
  onClose: () => void;
}) {
  const updateCollection = useUpdateCollection(collection.id);
  const [title, setTitle] = useState(collection.title);
  const [description, setDescription] = useState(collection.description);
  const [isPublic, setIsPublic] = useState(collection.isPublic);
  const [editable, setEditable] = useState(collection.editable);

  useEffect(() => {
    if (!open) return;
    setTitle(collection.title);
    setDescription(collection.description);
    setIsPublic(collection.isPublic);
    setEditable(collection.editable);
    updateCollection.reset();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, collection]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    try {
      await updateCollection.mutateAsync({ title, description, isPublic, editable });
      onClose();
    } catch {
      // surfaced via updateCollection.isError
    }
  }

  return (
    <Dialog open={open} onClose={onClose} title={`Éditer ${collection.title}`}>
      <form onSubmit={submit} className="flex flex-col gap-3">
        <label className="flex flex-col gap-1 text-sm">
          Titre
          <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="flex flex-col gap-1 text-sm">
          Description
          <Input aria-label="Description" value={description} onChange={(e) => setDescription(e.target.value)} />
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Public"
            checked={isPublic}
            onChange={(e) => setIsPublic(e.target.checked)}
          />
          Public
        </label>
        <label className="flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            aria-label="Éditable"
            checked={editable}
            onChange={(e) => setEditable(e.target.checked)}
          />
          Éditable
        </label>
        {updateCollection.isError && (
          <p role="alert" className="text-sm text-red-600">
            Échec de la mise à jour.
          </p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="outline" size="sm" onClick={onClose}>
            Annuler
          </Button>
          <Button type="submit" size="sm" disabled={updateCollection.isPending}>
            Enregistrer
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- EditCollectionDialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing test for edit+delete wired into `CollectionsAdminPage`**

Append to `shell/src/pages/CollectionsAdminPage.test.tsx`:

```tsx
test("edits a collection via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.patch("https://core.test/collections/incidents", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({
        id: "incidents", title: "Incidents (v2)", description: "", tableName: "incidents",
        isPublic: false, editable: true, geometryType: "Point", srid: 4326,
        pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
      });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  const titleInput = await screen.findByLabelText("Titre");
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ title: "Incidents (v2)" }));
});

test("deletes a collection after confirming", async () => {
  let deleteCalled = false;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.delete("https://core.test/collections/incidents", () => {
      deleteCalled = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleteCalled).toBe(true));
});
```

(the row-action "Supprimer" button and the `ConfirmDialog`'s own confirm button share the exact same accessible name once the dialog is open — `getByRole` would then throw on "found multiple elements". Scope the second query with `within(dialog)`, the same pattern already used in this codebase's `src/shell/ItemActions.test.tsx:73-74` for the identical `ConfirmDialog` collision on item deletion.)

- [ ] **Step 6: Add the `within` import**

At the top of `shell/src/pages/CollectionsAdminPage.test.tsx`, change:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
```

to:

```tsx
import { render, screen, waitFor, within } from "@testing-library/react";
```

- [ ] **Step 7: Run tests to verify they fail**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: FAIL — no "Éditer"/"Supprimer" buttons exist yet in the table rows.

- [ ] **Step 8: Wire edit + delete into `CollectionsAdminPage`**

Replace the full contents of `shell/src/pages/CollectionsAdminPage.tsx`:

```tsx
import { useState } from "react";
import { useCollectionsAdmin, useDeleteCollection, useMe } from "../api/hooks";
import type { CollectionAdmin } from "../api/types";
import { Button } from "../ui/button";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { EditCollectionDialog } from "../shell/EditCollectionDialog";
import { RegisterCollectionDialog } from "../shell/RegisterCollectionDialog";

export function CollectionsAdminPage() {
  const meQuery = useMe();
  const collectionsQuery = useCollectionsAdmin({ enabled: meQuery.data?.isAdmin === true });
  const deleteCollection = useDeleteCollection();
  const [registerOpen, setRegisterOpen] = useState(false);
  const [editing, setEditing] = useState<CollectionAdmin | null>(null);
  const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);

  if (meQuery.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (meQuery.data?.isAdmin !== true) {
    return (
      <p role="alert" className="text-sm text-red-600">
        Accès réservé aux administrateurs.
      </p>
    );
  }

  async function confirmDelete() {
    if (!deleting) return;
    try {
      await deleteCollection.mutateAsync(deleting.id);
      setDeleting(null);
    } catch {
      // surfaced via deleteCollection.isError
    }
  }

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="text-lg font-bold">Collections</h1>
        <Button size="sm" onClick={() => setRegisterOpen(true)}>
          Enregistrer une table
        </Button>
      </div>
      {collectionsQuery.isLoading && <p role="status">Chargement…</p>}
      {collectionsQuery.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec du chargement des collections.
        </p>
      )}
      {deleteCollection.isError && (
        <p role="alert" className="text-sm text-red-600">
          Échec de la suppression.
        </p>
      )}
      {collectionsQuery.data && (
        <table className="w-full text-left text-sm">
          <thead>
            <tr className="border-b border-slate-200">
              <th className="py-2">Titre</th>
              <th className="py-2">Table</th>
              <th className="py-2">Public</th>
              <th className="py-2">Éditable</th>
              <th className="py-2">Entités</th>
              <th className="py-2">Propriétaire</th>
              <th className="py-2">Actions</th>
            </tr>
          </thead>
          <tbody>
            {collectionsQuery.data.map((col) => (
              <tr key={col.id} className="border-b border-slate-100">
                <td className="py-2">{col.title}</td>
                <td className="py-2 text-xs text-slate-500">{col.tableName}</td>
                <td className="py-2">{col.isPublic ? "Oui" : "Non"}</td>
                <td className="py-2">{col.editable ? "Oui" : "Non"}</td>
                <td className="py-2">{col.featureCount ?? "—"}</td>
                <td className="py-2">{col.owner ?? "—"}</td>
                <td className="py-2 flex gap-2">
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(col)}>
                    Éditer
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(col)}>
                    Supprimer
                  </Button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <RegisterCollectionDialog open={registerOpen} onClose={() => setRegisterOpen(false)} />
      {editing && (
        <EditCollectionDialog collection={editing} open={true} onClose={() => setEditing(null)} />
      )}
      <ConfirmDialog
        open={!!deleting}
        title="Supprimer la collection"
        message={deleting ? `Désenregistrer « ${deleting.title} » ? La table PostGIS ne sera pas supprimée.` : ""}
        confirmLabel="Supprimer"
        pending={deleteCollection.isPending}
        onCancel={() => setDeleting(null)}
        onConfirm={confirmDelete}
      />
    </div>
  );
}
```

- [ ] **Step 9: Run tests to verify they pass**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 10: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all pass, clean typecheck.

- [ ] **Step 11: Commit**

```bash
git add shell/src/shell/EditCollectionDialog.tsx shell/src/shell/EditCollectionDialog.test.tsx \
        shell/src/pages/CollectionsAdminPage.tsx shell/src/pages/CollectionsAdminPage.test.tsx
git commit -m "feat(shell): EditCollectionDialog + delete (ConfirmDialog) wired into CollectionsAdminPage"
```

---

### Task 6: Shell — `CollectionShareDialog`

**Files:**
- Create: `shell/src/shell/CollectionShareDialog.tsx`
- Create: `shell/src/shell/CollectionShareDialog.test.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.tsx`
- Modify: `shell/src/pages/CollectionsAdminPage.test.tsx`

**Interfaces:**
- Consumes: `useGroups` (pre-existing), `useCollectionSharing`, `useSetCollectionSharing` (Task 3); `ShareRole` (`api/types.ts`, pre-existing).
- Produces: `CollectionShareDialog({ collectionId, open, onClose })`.

This is a near-duplicate of `shell/src/shell/ShareDialog.tsx`, adapted to `collectionId` instead of `item.pk` — same deliberate duplication already documented in the spec (§3.3), same rationale already used elsewhere in this codebase for other single-caller echoes (`ExtensionManifest`↔`WcWidgetManifest`, CEL/Python mapping).

- [ ] **Step 1: Write the failing test**

Create `shell/src/shell/CollectionShareDialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { CollectionShareDialog } from "./CollectionShareDialog";

function Harness({ onClose = () => {} }: { onClose?: () => void }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <CollectionShareDialog collectionId="incidents" open={true} onClose={onClose} />
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("pre-fills sharing state and PUTs the chosen roles on submit", async () => {
  let body: unknown;
  server.use(
    http.get("https://core.test/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
    }),
  );
  const onClose = vi.fn();
  render(<Harness onClose={onClose} />);
  await userEvent.click(await screen.findByLabelText("Groupe Équipe terrain"));
  await userEvent.selectOptions(screen.getByLabelText("Rôle Équipe terrain"), "editor");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  expect(body).toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- CollectionShareDialog.test.tsx`
Expected: FAIL — cannot find module `./CollectionShareDialog`.

- [ ] **Step 3: Implement `CollectionShareDialog`**

Create `shell/src/shell/CollectionShareDialog.tsx`:

```tsx
import { useEffect, useState } from "react";
import { useCollectionSharing, useGroups, useSetCollectionSharing } from "../api/hooks";
import type { ShareRole } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";

export function CollectionShareDialog({
  collectionId,
  open,
  onClose,
}: {
  collectionId: string;
  open: boolean;
  onClose: () => void;
}) {
  const groupsQuery = useGroups({ enabled: open });
  const sharingQuery = useCollectionSharing(collectionId, { enabled: open });
  const setSharing = useSetCollectionSharing(collectionId);

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});

  useEffect(() => {
    if (!open || !sharingQuery.data) return;
    setIsPublic(sharingQuery.data.public);
    const map: Record<string, ShareRole> = {};
    sharingQuery.data.groups.forEach((g) => {
      map[g.groupId] = g.role;
    });
    setRoles(map);
  }, [open, sharingQuery.data]);

  async function submit() {
    setSharing.reset();
    const groups = Object.entries(roles)
      .filter(([, role]) => role)
      .map(([groupId, role]) => ({ groupId, role: role as ShareRole }));
    try {
      await setSharing.mutateAsync({ public: isPublic, groups });
      onClose();
    } catch {
      /* surfaced via setSharing.isError */
    }
  }

  const loading = groupsQuery.isLoading || sharingQuery.isLoading;
  const failed = groupsQuery.isError || sharingQuery.isError;
  const ready = groupsQuery.isSuccess && sharingQuery.isSuccess;

  return (
    <Dialog open={open} onClose={onClose} title="Partager la collection">
      {loading && <p role="status">Chargement…</p>}
      {failed && (
        <p role="alert" className="text-sm text-red-600">
          Erreur de chargement.
        </p>
      )}
      {ready && (
        <div className="flex flex-col gap-3">
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              aria-label="Public"
              checked={isPublic}
              onChange={(e) => setIsPublic(e.target.checked)}
            />
            Public (visible par tous)
          </label>

          <div className="flex flex-col gap-2">
            {groupsQuery.data.map((g) => (
              <div key={g.id} className="flex items-center justify-between gap-2 text-sm">
                <label className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    aria-label={`Groupe ${g.title}`}
                    checked={!!roles[g.id]}
                    onChange={(e) =>
                      setRoles((r) => ({
                        ...r,
                        [g.id]: e.target.checked ? (r[g.id] ?? "viewer") : undefined,
                      }))
                    }
                  />
                  {g.title}
                </label>
                <select
                  aria-label={`Rôle ${g.title}`}
                  className="h-8 rounded-md border border-slate-300 bg-white px-2 text-sm"
                  disabled={!roles[g.id]}
                  value={roles[g.id] ?? "viewer"}
                  onChange={(e) =>
                    setRoles((r) => ({ ...r, [g.id]: e.target.value as ShareRole }))
                  }
                >
                  <option value="viewer">Lecteur</option>
                  <option value="editor">Éditeur</option>
                </select>
              </div>
            ))}
          </div>

          {setSharing.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec du partage.
            </p>
          )}

          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={onClose}>
              Annuler
            </Button>
            <Button type="button" size="sm" disabled={setSharing.isPending} onClick={submit}>
              Enregistrer
            </Button>
          </div>
        </div>
      )}
    </Dialog>
  );
}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- CollectionShareDialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Write the failing test for share wired into `CollectionsAdminPage`**

Append to `shell/src/pages/CollectionsAdminPage.test.tsx`:

```tsx
test("shares a collection via the row action", async () => {
  let putBody: unknown;
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "admin", firstName: "Admin", lastName: "Root", isAdmin: true }),
    ),
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "incidents", title: "Incidents", description: "", tableName: "incidents",
            isPublic: false, editable: true, geometryType: "Point", srid: 4326,
            pkColumn: "id", canWrite: true, featureCount: 3, owner: "admin",
          },
        ],
      }),
    ),
    http.get("https://core.test/collections/candidates", () => HttpResponse.json({ candidates: [] })),
    http.get("https://core.test/groups", () => HttpResponse.json([{ id: "g1", name: "Équipe terrain" }])),
    http.get("https://core.test/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/collections/incidents/sharing", async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json({ public: true, groups: [] });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await userEvent.click(await screen.findByLabelText("Public"));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(putBody).toEqual({ public: true, groups: [] }));
});
```

- [ ] **Step 6: Run test to verify it fails**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: FAIL — no "Partager" button exists in the row actions yet.

- [ ] **Step 7: Wire share into `CollectionsAdminPage`**

In `shell/src/pages/CollectionsAdminPage.tsx`, add the import:

```tsx
import { CollectionShareDialog } from "../shell/CollectionShareDialog";
```

Add state right after `const [deleting, setDeleting] = useState<CollectionAdmin | null>(null);`:

```tsx
  const [sharing, setSharing] = useState<CollectionAdmin | null>(null);
```

Add the "Partager" button between "Éditer" and "Supprimer" in the actions cell:

```tsx
                  <Button type="button" variant="outline" size="sm" onClick={() => setEditing(col)}>
                    Éditer
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setSharing(col)}>
                    Partager
                  </Button>
                  <Button type="button" variant="outline" size="sm" onClick={() => setDeleting(col)}>
                    Supprimer
                  </Button>
```

Add the dialog render right after the `EditCollectionDialog` block:

```tsx
      {sharing && (
        <CollectionShareDialog collectionId={sharing.id} open={true} onClose={() => setSharing(null)} />
      )}
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npm run test -- CollectionsAdminPage.test.tsx`
Expected: PASS (all tests in the file).

- [ ] **Step 9: Run the full shell suite and typecheck**

Run: `cd shell && npm run test && npm run build`
Expected: all pass, clean typecheck.

- [ ] **Step 10: Commit**

```bash
git add shell/src/shell/CollectionShareDialog.tsx shell/src/shell/CollectionShareDialog.test.tsx \
        shell/src/pages/CollectionsAdminPage.tsx shell/src/pages/CollectionsAdminPage.test.tsx
git commit -m "feat(shell): CollectionShareDialog wired into CollectionsAdminPage"
```

---

### Task 7: Shell — `/admin/collections` route + nav link split

**Files:**
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/AppLayout.test.tsx`
- Modify: `shell/e2e/admin-extensions.spec.ts`

**Interfaces:**
- Consumes: `CollectionsAdminPage` (Task 4).
- Note: deviates from the design spec's wording ("nouveau lien de nav « Administration »" + "garde `isAdmin`… redirection vers `/`") — the codebase already has an "Administration" nav link (added in SP-8c, the same day the spec was written, and not yet reflected in it) pointing to `/admin/extensions`, and `AdminExtensionsPage` guards inline (no redirect) rather than via a route wrapper. This task follows the *established* pattern (inline guard, already proven in the page components from Tasks 4-6) and turns the single link into two: "Extensions" and "Collections" — both under the same `isAdmin` gate, no route-level wrapper added (none exists for `/admin/extensions` either).

- [ ] **Step 1: Write the failing test for the split nav links**

In `shell/src/shell/AppLayout.test.tsx`, replace the two admin-link tests:

```tsx
test("shows the Extensions and Collections admin links only when the current user is admin", async () => {
  server.use(
    http.get("https://core.test/me", () =>
      HttpResponse.json({ id: "u1", username: "alice", firstName: "Alice", lastName: "Martin", isAdmin: true }),
    ),
  );
  renderLayout();
  expect(await screen.findByRole("link", { name: "Extensions" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Collections" })).toBeInTheDocument();
});

test("hides the admin links for a non-admin user", async () => {
  renderLayout();
  await screen.findByText("GeoStudio");
  expect(screen.queryByRole("link", { name: "Extensions" })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Collections" })).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npm run test -- AppLayout.test.tsx`
Expected: FAIL — no link named "Extensions" or "Collections" (still named "Administration").

- [ ] **Step 3: Implement the route and the nav split**

In `shell/src/shell/routes.tsx`, add the import:

```tsx
import { CollectionsAdminPage } from "../pages/CollectionsAdminPage";
```

Add the route right after `/admin/extensions`:

```tsx
        <Route path="/admin/extensions" element={<AdminExtensionsPage />} />
        <Route path="/admin/collections" element={<CollectionsAdminPage />} />
```

In `shell/src/shell/AppLayout.tsx`, replace the single admin link block:

```tsx
          {meQuery.data?.isAdmin === true && (
            <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
              Administration
            </Link>
          )}
```

with:

```tsx
          {meQuery.data?.isAdmin === true && (
            <>
              <Link to="/admin/extensions" className="mt-2 block text-sm font-medium hover:underline">
                Extensions
              </Link>
              <Link to="/admin/collections" className="mt-1 block text-sm font-medium hover:underline">
                Collections
              </Link>
            </>
          )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npm run test -- AppLayout.test.tsx`
Expected: PASS.

- [ ] **Step 5: Fix the now-stale E2E assertions**

In `shell/e2e/admin-extensions.spec.ts`, change both occurrences of:

```ts
  await expect(page.getByRole("link", { name: "Administration" })).toBeVisible();
```
and
```ts
  expect(await page.getByRole("link", { name: "Administration" }).count()).toBe(0);
```

to:

```ts
  await expect(page.getByRole("link", { name: "Extensions" })).toBeVisible();
```
and
```ts
  expect(await page.getByRole("link", { name: "Extensions" }).count()).toBe(0);
```

respectively (same test intent, renamed link).

- [ ] **Step 6: Run the full shell suite, typecheck, and the affected E2E spec**

Run: `cd shell && npm run test && npm run build && npm run e2e -- admin-extensions.spec.ts`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add shell/src/shell/routes.tsx shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx \
        shell/e2e/admin-extensions.spec.ts
git commit -m "feat(shell): /admin/collections route, split Administration nav link into Extensions/Collections"
```

---

### Task 8: E2E — `admin-collections.spec.ts`

**Files:**
- Create: `shell/e2e/admin-collections.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`shell/e2e/mocks.ts`, pre-existing, unmodified — its own `**/collections*` catch-all mock stays as-is; this spec adds a more specific `**/collections/candidates` route registered *after* `mockCore(page)`, which Playwright matches with priority over the earlier, broader `mockCore` registration — same rationale already documented in `mocks.ts` for the `**/collections/villes/items*`-style specific routes).

- [ ] **Step 1: Write the E2E spec**

Create `shell/e2e/admin-collections.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("un admin gère le cycle de vie complet d'une collection depuis le shell", async ({ page }) => {
  await mockCore(page);
  await page.route("**/me", async (route) => {
    await route.fulfill({
      json: {
        id: "u-mock", username: "mockuser", firstName: "Mock", lastName: "User",
        email: null, tenantId: "t-mock", isAdmin: true,
      },
    });
  });

  let registered: unknown = null;
  let patchedTitle: string | null = null;
  let sharedBody: unknown = null;
  let deleted = false;

  // Host-scoped (not "**/collections*"): the shell's own client-side route to
  // this very page is "/admin/collections" — a path-only glob would also
  // intercept the browser's document navigation and break rendering (same
  // rationale as "/items/1"/"/items/9" and "/admin/extensions" elsewhere in
  // this suite). Registered after mockCore(page), so its more specific
  // pattern wins over mockCore's own "**/collections*" catch-all.
  await page.route("https://core.test/collections/candidates", async (route) => {
    await route.fulfill({
      json: {
        candidates: [
          { tableName: "points_interet", registrable: true, geometryType: "Point", srid: 4326, columnCount: 3 },
        ],
      },
    });
  });

  await page.route("https://core.test/collections", async (route) => {
    if (route.request().method() === "POST") {
      registered = await route.request().postDataJSON();
      await route.fulfill({
        status: 201,
        json: {
          id: "points_interet", title: "Points d'intérêt", description: "", tableName: "points_interet",
          isPublic: false, editable: true, geometryType: "Point", srid: 4326,
          pkColumn: "id", canWrite: true, featureCount: 0, owner: "mockuser",
        },
      });
      return;
    }
    await route.fulfill({
      json: {
        collections: registered
          ? [{
              id: "points_interet", title: patchedTitle ?? "Points d'intérêt", description: "",
              tableName: "points_interet", isPublic: false, editable: true, geometryType: "Point",
              srid: 4326, pkColumn: "id", canWrite: true, featureCount: 0, owner: "mockuser",
            }]
          : deleted ? [] : [],
      },
    });
  });

  await page.route("https://core.test/collections/points_interet**", async (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const body = await route.request().postDataJSON();
      patchedTitle = body.title ?? patchedTitle;
      await route.fulfill({
        json: {
          id: "points_interet", title: patchedTitle, description: "", tableName: "points_interet",
          isPublic: false, editable: true, geometryType: "Point", srid: 4326,
          pkColumn: "id", canWrite: true, featureCount: 0, owner: "mockuser",
        },
      });
      return;
    }
    if (method === "DELETE") {
      deleted = true;
      await route.fulfill({ status: 204, body: "" });
      return;
    }
    if (route.request().url().endsWith("/sharing")) {
      if (method === "PUT") {
        sharedBody = await route.request().postDataJSON();
        await route.fulfill({ json: sharedBody });
        return;
      }
      await route.fulfill({ json: { public: false, groups: [] } });
      return;
    }
    await route.fallback();
  });

  await page.route("https://core.test/groups", async (route) => {
    await route.fulfill({ json: [{ id: "g1", name: "Équipe terrain" }] });
  });

  await page.goto("/admin/collections");
  await expect(page.getByRole("link", { name: "Collections" })).toBeVisible();

  await page.getByRole("button", { name: "Enregistrer une table" }).click();
  await page.getByLabel("Table").selectOption("points_interet");
  await page.getByLabel("Titre").fill("Points d'intérêt");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => registered).toEqual({ tableName: "points_interet", title: "Points d'intérêt", isPublic: false });
  await expect(page.getByText("Points d'intérêt")).toBeVisible();

  await page.getByRole("button", { name: "Éditer" }).click();
  const titleInput = page.getByLabel("Titre");
  await titleInput.fill("");
  await titleInput.fill("POI (édité)");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => patchedTitle).toBe("POI (édité)");

  await page.getByRole("button", { name: "Partager" }).click();
  await page.getByLabel("Groupe Équipe terrain").click();
  await page.getByLabel("Rôle Équipe terrain").selectOption("editor");
  await page.getByRole("button", { name: "Enregistrer" }).click();
  await expect.poll(() => sharedBody).toEqual({ public: false, groups: [{ groupId: "g1", role: "editor" }] });

  await page.getByRole("button", { name: "Supprimer" }).click();
  // The row-action button and the ConfirmDialog's confirm button share the
  // exact same accessible name once the dialog is open — Playwright's
  // strict mode would reject an unscoped getByRole here. Scope to the
  // dialog, same fix as CollectionsAdminPage.test.tsx (Task 5, Step 5).
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect.poll(() => deleted).toBe(true);
});

test("un utilisateur non-admin ne voit pas le lien Collections et une navigation forcée affiche un message d'accès refusé", async ({ page }) => {
  await mockCore(page);
  let collectionsAdminCalled = false;
  await page.route("https://core.test/collections", async (route) => {
    collectionsAdminCalled = true;
    await route.fulfill({ json: { collections: [] } });
  });

  await page.goto("/admin/collections");
  await expect(page.getByRole("alert")).toHaveText("Accès réservé aux administrateurs.");
  expect(await page.getByRole("link", { name: "Collections" }).count()).toBe(0);
  expect(collectionsAdminCalled).toBe(false);
});
```

- [ ] **Step 2: Run the new spec**

Run: `cd shell && npm run e2e -- admin-collections.spec.ts`
Expected: PASS (2/2 tests). If the first test is flaky on the `PATCH`/route-ordering logic, re-check the `**/collections/points_interet**` route's method branching against actual request logs (`DEBUG=pw:api npx playwright test admin-collections.spec.ts`) rather than adding retries.

- [ ] **Step 3: Run the complete E2E suite**

Run: `cd shell && npm run e2e`
Expected: all 36 specs pass (34 existing + `admin-collections.spec.ts` + no new spec files besides this one — confirm the exact count by listing `shell/e2e/*.spec.ts` before asserting a number in any commit message).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/admin-collections.spec.ts
git commit -m "test(e2e): admin collections lifecycle (register/edit/share/delete) + non-admin guard"
```

---

## Final Verification

- [ ] Run `cd core && uv run pytest && uv run lint-imports` (and again with `CORE_TEST_DATABASE_URL` set, for the postgis-marked tests) — all green.
- [ ] Run `cd shell && npm run test && npm run e2e && npm run build` — all green.
- [ ] Re-read `docs/superpowers/specs/2026-07-13-sp9-gestion-collections-design.md` §6 (Critères d'acceptation) line by line and confirm each is met by a task above:
  - Admin registers a collection without typing a table name by hand → Task 4.
  - Admin edits/shares/unregisters an existing collection → Tasks 5, 6.
  - Non-admin sees neither the link nor the page; forced navigation fails cleanly → Task 7 (link), Tasks 4/8 (page guard + E2E).
  - The 30 pre-existing E2E specs stay green → Task 8 Step 3 (now 34+1 baseline, not 30 — the spec's number is stale as of 2026-07-13; verify against the actual current count, not the spec's literal text).
