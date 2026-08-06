# SP-15b — Pipeline : canvas no-code — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship the SP-15b no-code canvas: a `PipelineBuilderPage` (React Flow)
with a draggable op palette, a JSON-Schema-driven node inspector, bounded
data preview, run + poll, and the shell wiring (`etlEnabled`, creation flow,
item-detail/editor routing) that SP-15a deliberately left undone — on top of
the headless pipeline engine SP-15a already shipped and reviewed clean.

**Architecture:** A new `shell/src/builder/pipeline/` module holds every
pipeline-editing building block as small, independently-testable units:
pure graph helpers (`graphOps.ts`, `validation.ts`), a collection picker
(`CollectionParamSelect.tsx`), a JSON-Schema-driven params form
(`PipelineNodeInspector.tsx`), the React Flow wrapper (`PipelineCanvas.tsx`),
the op palette (`PipelinePalette.tsx`), and the preview/run panels
(`PipelinePreviewPanel.tsx`, `PipelineRunPanel.tsx`). `shell/src/pages/
PipelineBuilderPage.tsx` composes all of them, in the same "dumb composition,
smart children" style as `DatasetEditPage.tsx`. The API surface is added to
the existing hand-written `ItemClient` interface/`itemClient.ts`/`hooks.ts`
trio — SP-15a's REST routes (`GET /pipelines/ops`, `POST/GET /pipelines/{id}/
run|runs`, `POST /pipelines/{id}/preview`) are consumed as-is, no core
endpoint changes except one additive JSON Schema hint.

**Tech Stack:** React 19, `@tanstack/react-query` 5, `react-router-dom` 6,
Vitest 3 + Testing Library + MSW (existing), Playwright 1.47 (existing),
**new dependency: `@xyflow/react` 12** (MIT). Core: FastAPI/Pydantic v2
(existing, `core/app/pipelines/` from SP-15a) — one additive `Field(...,
json_schema_extra=...)` change, no new Python dependency.

## Global Constraints

- **Reference spec:** `docs/superpowers/specs/2026-08-06-sp15b-canvas-nocode-design.md`
  — read it first. This plan implements it with one interaction refinement
  applied during planning: **"insert a transform between two connected
  nodes" is a click affordance, not a drag-onto-edge gesture.** Each edge
  renders a small "+" button at its midpoint (`EdgeLabelRenderer`); clicking
  it opens a short list of the 5 `transform.*` ops; picking one calls the
  pure `insertNodeOnEdge` helper. Dragging precisely onto a thin SVG edge
  path is fiddly to hit-test reliably and to test; a click-to-insert button
  achieves the same outcome (§3.3 of the spec) with a implementation that is
  both simpler and more discoverable. Dragging a palette op onto empty
  canvas space (creating a floating, manually-wired node) is unchanged from
  the spec.
- **No new item-listing surface**: `CatalogPage.tsx`'s type filter dropdown
  today only offers `app`/`dashboard`/`map` (verified by reading the file —
  `dataset` and `bookmark` were never added to it either). Pipelines are
  reachable exactly the way datasets already are: they appear in the
  unfiltered "Tous" catalog listing, and opening one routes to its editor via
  `useOpenItem`/`ItemDetailPage`'s existing `resourceType` switch. **Do not
  touch `CatalogPage.tsx`'s select** — this corrects an inaccuracy in spec §2.4.
- **Collection pickers reuse `listCollections()`/`useCollectionsAdmin()`
  verbatim** (`GET /collections`, already scoped to what the current user can
  see; `CollectionAdmin.canWrite` distinguishes the writable subset) — no new
  core endpoint for "collections I can read/write".
- **No `ajv` or any JSON-Schema-validation library added.** The op catalogue's
  JSON Schemas (`GET /pipelines/ops`) are only ever read for two shapes this
  plan actually needs: `properties[name].{type,format,enum,items}` and
  `required: string[]`. `validateNodeParamsShape` (Task 3) is a ~10-line hand
  rolled required-field presence check — shape-only, exactly mirroring the
  shape-vs-semantic boundary SP-15a already drew server-side (params shape
  checked at save time, expression semantics only at run time — unchanged,
  not re-litigated here).
- **Poll pattern**: run-status polling uses the exact recursive
  `for(;;) { …; await sleep(1500) }` idiom already in
  `shell/src/shell/ImportFileButton.tsx` (manual loop via `useItemClient()`
  directly, not a `react-query` `refetchInterval`) — consistent with the only
  existing async-job-polling precedent in this codebase.
- **`ResizeObserver` stub for React Flow tests**: `@xyflow/react` calls
  `ResizeObserver` unconditionally. Stub it locally (`vi.stubGlobal` in
  `beforeEach`/`vi.unstubAllGlobals` in `afterEach`) in every test file that
  renders `PipelineCanvas`, exactly like `shell/src/builder/EChart.test.tsx`
  already does for its own unconditional `ResizeObserver` call — **do not**
  add a global stub to `shell/src/test/setup.ts` (would silently change
  behavior for every other suite).
- **Every new/modified core file** keeps the `# SPDX-License-Identifier:
  Apache-2.0` header (already present in the one file this plan touches).
  **Every new shell file** keeps the `// SPDX-License-Identifier: Apache-2.0`
  header, matching every existing file in `shell/src/`.
- **French comments for non-obvious "why"**, English identifiers — matches
  the existing codebase exactly (do not translate existing comments).
- **Never commit with `--no-verify`**; run the exact test commands shown in
  each step before moving to the next step.

---

## Task 1: Core — `format: "collection-id"` hint on the 3 collection-referencing params

**Files:**
- Modify: `core/app/pipelines/ops/schemas.py`
- Test: `core/tests/test_pipeline_ops_schemas.py` (already exists from SP-15a — add to it)

**Interfaces:**
- Consumes: nothing new.
- Produces: `GET /pipelines/ops`'s `paramsSchema.properties.<field>.format ==
  "collection-id"` on `reader.collection.collectionId`,
  `writer.collection.collectionId`, `transform.join.withCollectionId` —
  consumed by Task 5 (`PipelineNodeInspector`) to pick which fields render a
  `CollectionParamSelect` instead of a bare text input.

- [ ] **Step 1: Write the failing test**

Append to `core/tests/test_pipeline_ops_schemas.py`:

```python
def test_collection_referencing_fields_carry_collection_id_format_hint():
    catalog = ops_catalog()
    assert catalog["reader.collection"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"
    assert catalog["writer.collection"]["paramsSchema"]["properties"]["collectionId"]["format"] == "collection-id"
    assert catalog["transform.join"]["paramsSchema"]["properties"]["withCollectionId"]["format"] == "collection-id"


def test_non_collection_fields_carry_no_format_hint():
    catalog = ops_catalog()
    assert "format" not in catalog["transform.filter"]["paramsSchema"]["properties"]["expr"]
    assert "format" not in catalog["transform.join"]["paramsSchema"]["properties"]["on"]
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: FAIL — `KeyError: 'format'` on the two new assertions.

- [ ] **Step 3: Add the hint**

In `core/app/pipelines/ops/schemas.py`, change the three fields:

```python
class ReaderCollectionParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
```

```python
class TransformJoinParams(BaseModel):
    withCollectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
    on: str
    how: Literal["inner", "left"] = "inner"
```

```python
class WriterCollectionParams(BaseModel):
    collectionId: str = Field(..., json_schema_extra={"format": "collection-id"})
```

(`Field` and `BaseModel` are already imported at the top of the file — no
new import needed.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd core && uv run pytest tests/test_pipeline_ops_schemas.py -v`
Expected: PASS (17 tests: the 15 pre-existing from SP-15a + 2 new).

- [ ] **Step 5: Run the wider pipeline test suite to check no regression**

Run: `cd core && uv run pytest tests/test_pipeline_config_validation.py tests/test_pipeline_node_validation.py tests/test_pipeline_config_schema.py -v`
Expected: PASS (unchanged — `json_schema_extra` never affects Pydantic
validation, only the emitted JSON Schema).

- [ ] **Step 6: Commit**

```bash
git add core/app/pipelines/ops/schemas.py core/tests/test_pipeline_ops_schemas.py
git commit -m "feat(core): expose collection-id format hint on pipeline op params"
```

---

## Task 2: Shell API layer — types, `ItemClient` methods, hooks

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/itemClient.test.ts` (already exists — add to it)

**Interfaces:**
- Consumes: nothing new (types are the foundation).
- Produces: `PipelineNode`, `PipelineEdge`, `PipelinePayload`,
  `PipelineOpParamProperty`, `PipelineOpEntry`, `PipelineOpsCatalog`,
  `PipelineRunStatus`, `PipelineRun` (types); `ResourceType` gains
  `"pipeline"`; `InstanceInfo` gains `etlEnabled: boolean`; `ItemClient`
  gains `createPipelineItem`, `getPipelineConfig`, `savePipelineConfig`,
  `getPipelineOps`, `runPipeline`, `getPipelineRuns`, `previewPipeline` —
  all implemented in `itemClient.ts`; `hooks.ts` gains
  `usePipelineConfig(pk, opts?)`, `useCreatePipeline()`,
  `useSavePipeline(pk)`, `usePipelineOps()`, `useRunPipeline(pk)`. Consumed
  by every later shell task.

- [ ] **Step 1: Add the types**

In `shell/src/api/types.ts`, change line 2:

```ts
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark" | "pipeline";
```

Change line 35:

```ts
export type InstanceInfo = { readOnly: boolean; etlEnabled: boolean };
```

Add at the end of the file:

```ts
export type PipelineNodeKind = "reader" | "transform" | "writer";

export type PipelineNode = {
  id: string;
  kind: PipelineNodeKind;
  op: string;
  x: number;
  y: number;
  params: Record<string, unknown>;
  title?: string | null;
};

// Wire-format alias "from" comes straight from the core's PipelineEdge
// (Pydantic Field(alias="from") — "from" is a reserved word in Python but a
// perfectly valid object-literal key in TS/JS, so no remapping is needed on
// either side of the wire (core/app/configs/schemas.py::PipelineEdge).
export type PipelineEdge = {
  id: string;
  from: string;
  to: string;
  when?: string | null;
};

export type PipelinePayload = {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
};

// Minimal typed subset of JSON Schema actually consumed by
// PipelineNodeInspector (builder/pipeline/PipelineNodeInspector.tsx) — not a
// general JSON Schema type, deliberately narrow to what
// core/app/pipelines/ops/schemas.py's model_json_schema() output is used for.
export type PipelineOpParamProperty = {
  type?: "string" | "number" | "integer" | "boolean" | "array" | "object";
  format?: string;
  enum?: string[];
  default?: unknown;
  items?: { type?: string };
};

export type PipelineOpEntry = {
  kind: PipelineNodeKind;
  paramsSchema: {
    properties: Record<string, PipelineOpParamProperty>;
    required?: string[];
  };
};

export type PipelineOpsCatalog = Record<string, PipelineOpEntry>;

export type PipelineRunStatus = "queued" | "running" | "succeeded" | "failed";

export type PipelineRun = {
  id: string;
  status: PipelineRunStatus;
  startedAt: string | null;
  finishedAt: string | null;
  error: string | null;
  nodeStats: Record<string, unknown>;
};
```

Add these seven method signatures to the `ItemClient` interface, right after
`getBookmarkConfig(pk: string): Promise<BookmarkPayload>;` (line 138):

```ts
  createPipelineItem(input: { title: string; owner: string; pipeline: PipelinePayload }): Promise<Item>;
  getPipelineConfig(pk: string): Promise<PipelinePayload>;
  savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void>;
  getPipelineOps(): Promise<PipelineOpsCatalog>;
  runPipeline(pk: string): Promise<{ runId: string }>;
  getPipelineRuns(pk: string): Promise<PipelineRun[]>;
  previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]>;
```

- [ ] **Step 2: Run the type check to verify it fails (missing implementation)**

Run: `cd shell && npx tsc --noEmit`
Expected: FAIL — `Property 'createPipelineItem' is missing in type ... ItemClient` (and 6 siblings) in `itemClient.ts`.

- [ ] **Step 3: Write the failing itemClient tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("createPipelineItem posts a pipeline payload and returns a pipeline Item", async () => {
  let body: any;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-p1", kind: "pipeline", itemId: "p-1" }, { status: 201 });
    }),
  );
  const payload = {
    nodes: [
      { id: "r1", kind: "reader" as const, op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" } },
      { id: "w1", kind: "writer" as const, op: "writer.collection", x: 200, y: 0, params: { collectionId: "villes_propres" } },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const item = await makeClient().createPipelineItem({ title: "Nettoyer villes", owner: "alice", pipeline: payload });
  expect(body.config).toEqual({ version: 1, kind: "pipeline", pipeline: payload });
  expect(item).toMatchObject({ pk: "p-1", resourceType: "pipeline", title: "Nettoyer villes", configId: "cfg-p1" });
});

test("getPipelineConfig reads the pipeline payload from the by-item config", async () => {
  const payload = {
    nodes: [{ id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" } }],
    edges: [],
  };
  server.use(
    http.get("https://core.test/configs/by-item/p-2", () =>
      HttpResponse.json({ id: "cfg-p2", itemId: "p-2", kind: "pipeline", config: { kind: "pipeline", pipeline: payload } }),
    ),
  );
  const cfg = await makeClient().getPipelineConfig("p-2");
  expect(cfg).toEqual(payload);
});

test("getPipelineConfig throws when the config has no pipeline payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/p-3", () =>
      HttpResponse.json({ id: "cfg-p3", itemId: "p-3", kind: "app", config: { kind: "app" } }),
    ),
  );
  await expect(makeClient().getPipelineConfig("p-3")).rejects.toThrow();
});

test("savePipelineConfig PUTs the pipeline payload wrapped in a kind=pipeline envelope", async () => {
  let method = "";
  let body: any;
  server.use(
    http.put("https://core.test/configs/by-item/p-4", async ({ request }) => {
      method = request.method;
      body = await request.json();
      return HttpResponse.json({});
    }),
  );
  const payload = { nodes: [], edges: [] };
  await makeClient().savePipelineConfig("p-4", payload);
  expect(method).toBe("PUT");
  expect(body).toEqual({ version: 1, kind: "pipeline", pipeline: payload });
});

test("getPipelineOps returns the op catalogue as-is", async () => {
  const catalog = { "reader.collection": { kind: "reader", paramsSchema: { properties: {}, required: [] } } };
  server.use(http.get("https://core.test/pipelines/ops", () => HttpResponse.json(catalog)));
  const result = await makeClient().getPipelineOps();
  expect(result).toEqual(catalog);
});

test("runPipeline posts with no body and returns the runId", async () => {
  server.use(
    http.post("https://core.test/pipelines/p-5/run", () => HttpResponse.json({ runId: "run-1" }, { status: 202 })),
  );
  const result = await makeClient().runPipeline("p-5");
  expect(result).toEqual({ runId: "run-1" });
});

test("getPipelineRuns returns the run history", async () => {
  const runs = [{ id: "run-1", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:05Z", error: null, nodeStats: {} }];
  server.use(http.get("https://core.test/pipelines/p-6/runs", () => HttpResponse.json(runs)));
  const result = await makeClient().getPipelineRuns("p-6");
  expect(result).toEqual(runs);
});

test("previewPipeline posts upTo as a query param and returns the row list", async () => {
  let url = "";
  server.use(
    http.post("https://core.test/pipelines/p-7/preview", ({ request }) => {
      url = request.url;
      return HttpResponse.json([{ id: 1, pop: 1200 }]);
    }),
  );
  const rows = await makeClient().previewPipeline("p-7", "r1");
  expect(url).toContain("upTo=r1");
  expect(rows).toEqual([{ id: 1, pop: 1200 }]);
});
```

- [ ] **Step 4: Run to verify the new tests fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `client.createPipelineItem is not a function` (and siblings).

- [ ] **Step 5: Implement the seven methods**

In `shell/src/api/itemClient.ts`, add `PipelineOpsCatalog`, `PipelinePayload`,
`PipelineRun` to the type-only import on line 2 (append to the existing
list). Then add the seven methods to the returned object, right after
`getBookmarkConfig` (after line 636):

```ts
    async createPipelineItem(input: { title: string; owner: string; pipeline: PipelinePayload }): Promise<Item> {
      const config = { version: 1, kind: "pipeline", pipeline: input.pipeline };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createPipelineItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "pipeline", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getPipelineConfig(pk: string): Promise<PipelinePayload> {
      const data = await request<{ config?: { pipeline?: PipelinePayload } }>(
        "GET", `/configs/by-item/${pk}`,
      );
      if (!data.config?.pipeline) throw new Error("getPipelineConfig: config has no pipeline payload");
      return data.config.pipeline;
    },

    async savePipelineConfig(pk: string, payload: PipelinePayload): Promise<void> {
      await request<void>("PUT", `/configs/by-item/${pk}`, { version: 1, kind: "pipeline", pipeline: payload });
    },

    async getPipelineOps(): Promise<PipelineOpsCatalog> {
      return request<PipelineOpsCatalog>("GET", "/pipelines/ops");
    },

    async runPipeline(pk: string): Promise<{ runId: string }> {
      return request<{ runId: string }>("POST", `/pipelines/${pk}/run`);
    },

    async getPipelineRuns(pk: string): Promise<PipelineRun[]> {
      return request<PipelineRun[]>("GET", `/pipelines/${pk}/runs`);
    },

    async previewPipeline(pk: string, upToNodeId: string): Promise<Record<string, unknown>[]> {
      return request<Record<string, unknown>[]>(
        "POST", `/pipelines/${pk}/preview?upTo=${encodeURIComponent(upToNodeId)}`,
      );
    },
```

- [ ] **Step 6: Run to verify the itemClient tests pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests, including the 7 new ones).

- [ ] **Step 7: Wire `etlEnabled` into `useInstanceInfo` and add the pipeline hooks**

In `shell/src/api/hooks.ts`, replace the `useInstanceInfo` body (lines 30-42)
to add the same fail-safe default for `etlEnabled` that already exists for
`readOnly`:

```ts
export function useInstanceInfo() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["instance"],
    // Même garde défensive pour etlEnabled que pour readOnly ci-dessus
    // (SP-15b) : un ItemClient de test qui ne l'implémente pas encore
    // résout silencieusement à false plutôt que de planter la query.
    queryFn: () => client.getInstanceInfo?.() ?? Promise.resolve({ readOnly: false, etlEnabled: false }),
  });
}
```

Add the type-only imports `PipelinePayload`, `PipelineOpsCatalog` to the
import line at the top of `hooks.ts` (append to the existing `import type {
...} from "./types"` list). Then add, after `useSaveDataset` (after line
248):

```ts
export function usePipelineConfig(pk: string, options?: { enabled?: boolean }) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline", pk],
    queryFn: () => client.getPipelineConfig(pk),
    enabled: options?.enabled ?? true,
  });
}

export function useCreatePipeline() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { title: string; owner: string; pipeline: PipelinePayload }) =>
      client.createPipelineItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useSavePipeline(pk: string) {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (payload: PipelinePayload) => client.savePipelineConfig(pk, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["pipeline", pk] });
    },
  });
}

export function usePipelineOps() {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-ops"],
    queryFn: () => client.getPipelineOps(),
    staleTime: Infinity, // catalogue statique côté serveur, jamais invalidé
  });
}

export function useRunPipeline(pk: string) {
  const client = useItemClientInternal();
  return useMutation({
    mutationFn: () => client.runPipeline(pk),
  });
}
```

(`usePipelinePreview` and the run-polling hook are added in Tasks 8 and 9,
alongside the components that are their only consumers.)

- [ ] **Step 8: Full-project type check and existing suite**

Run: `cd shell && npx tsc --noEmit && npx vitest run src/api`
Expected: PASS — no type errors anywhere in the project (every other
`ItemClient` implementer is `Partial<ItemClient>` in tests, so the new
required methods don't break any existing mock), all `src/api` tests green.

- [ ] **Step 9: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add pipeline CRUD/run/preview to ItemClient and hooks"
```

---

## Task 3: Pure graph helpers — `graphOps.ts` + `validation.ts`

**Files:**
- Create: `shell/src/builder/pipeline/graphOps.ts`
- Create: `shell/src/builder/pipeline/graphOps.test.ts`
- Create: `shell/src/builder/pipeline/validation.ts`
- Create: `shell/src/builder/pipeline/validation.test.ts`

**Interfaces:**
- Consumes: `PipelineNode`, `PipelineEdge`, `PipelinePayload`,
  `PipelineOpsCatalog` (Task 2).
- Produces: `genNodeId()`, `genEdgeId()`, `hasIncomingEdge(edges, nodeId)`,
  `wouldCreateCycle(nodes, edges, candidateEdge)`,
  `insertNodeOnEdge(nodes, edges, edgeId, newNode)` from `graphOps.ts`;
  `validatePipelineGraphLocally(nodes, edges, opsCatalog):
  PipelineValidationResult`, `isPipelineValid(result)` from `validation.ts`
  — consumed by Task 6 (`PipelineCanvas`'s connection guard and edge-insert
  button) and Task 10 (`PipelineBuilderPage`'s "Enregistrer" gating).

- [ ] **Step 1: Write the failing tests for `graphOps.ts`**

Create `shell/src/builder/pipeline/graphOps.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { PipelineEdge, PipelineNode } from "../../api/types";
import { genEdgeId, genNodeId, hasIncomingEdge, insertNodeOnEdge, wouldCreateCycle } from "./graphOps";

test("genNodeId and genEdgeId produce distinct, non-empty ids", () => {
  const a = genNodeId();
  const b = genNodeId();
  expect(a).not.toBe(b);
  expect(a.length).toBeGreaterThan(0);
  expect(genEdgeId().length).toBeGreaterThan(0);
});

test("hasIncomingEdge is true only for a node that is some edge's 'to'", () => {
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  expect(hasIncomingEdge(edges, "w1")).toBe(true);
  expect(hasIncomingEdge(edges, "r1")).toBe(false);
});

test("wouldCreateCycle detects a direct back-edge", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "a", to: "b" }];
  expect(wouldCreateCycle(nodes, edges, { from: "b", to: "a" })).toBe(true);
});

test("wouldCreateCycle detects a longer cycle through an intermediate node", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} },
    { id: "c", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "a", to: "b" },
    { id: "e2", from: "b", to: "c" },
  ];
  expect(wouldCreateCycle(nodes, edges, { from: "c", to: "a" })).toBe(true);
});

test("wouldCreateCycle is false for a candidate that keeps the graph acyclic", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  expect(wouldCreateCycle(nodes, [], { from: "a", to: "b" })).toBe(false);
});

test("insertNodeOnEdge splits the edge into two, wiring the new node between", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "w1", kind: "writer", op: "writer.collection", x: 200, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const newNode: PipelineNode = { id: "t1", kind: "transform", op: "transform.filter", x: 100, y: 0, params: {} };

  const result = insertNodeOnEdge(nodes, edges, "e1", newNode);

  expect(result.nodes).toEqual([...nodes, newNode]);
  expect(result.edges).toHaveLength(2);
  expect(result.edges.find((e) => e.from === "r1")?.to).toBe("t1");
  expect(result.edges.find((e) => e.from === "t1")?.to).toBe("w1");
  expect(result.edges.some((e) => e.id === "e1")).toBe(false);
});

test("insertNodeOnEdge is a no-op when the edge id does not exist", () => {
  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];
  const newNode: PipelineNode = { id: "t1", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} };
  const result = insertNodeOnEdge(nodes, edges, "missing", newNode);
  expect(result).toEqual({ nodes, edges });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/graphOps.test.ts`
Expected: FAIL — `Cannot find module './graphOps'`.

- [ ] **Step 3: Implement `graphOps.ts`**

Create `shell/src/builder/pipeline/graphOps.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode } from "../../api/types";

// Pas crypto.randomUUID() : évite toute dépendance à sa disponibilité dans
// l'environnement de test (jsdom) ou un navigateur ancien — un id
// suffisamment unique pour un graphe édité par un seul utilisateur en local.
function genId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function genNodeId(): string {
  return genId("n");
}

export function genEdgeId(): string {
  return genId("e");
}

export function hasIncomingEdge(edges: PipelineEdge[], nodeId: string): boolean {
  return edges.some((e) => e.to === nodeId);
}

// Miroir client de app/configs/pipeline_validation.py::_check_acyclic
// (SP-15a) — mêmes couleurs DFS, mais posée la question "ce candidat
// créerait-il un cycle ?" avant de l'ajouter, pour la garde de connexion
// interactive du canvas (Task 6).
export function wouldCreateCycle(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  candidate: { from: string; to: string },
): boolean {
  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) adjacency.get(e.from)?.push(e.to);
  adjacency.get(candidate.from)?.push(candidate.to);

  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<string, number>(nodes.map((n) => [n.id, WHITE]));

  function visit(nodeId: string): boolean {
    color.set(nodeId, GRAY);
    for (const next of adjacency.get(nodeId) ?? []) {
      if (color.get(next) === GRAY) return true;
      if (color.get(next) === WHITE && visit(next)) return true;
    }
    color.set(nodeId, BLACK);
    return false;
  }

  return nodes.some((n) => color.get(n.id) === WHITE && visit(n.id));
}

// Insertion d'un nœud "sur" une arête existante (SP-15b, clic sur le bouton
// "+" d'une arête, cf. plan Global Constraints — pas un drag-drop précis sur
// le tracé SVG) : retire l'arête from->to, ajoute le nœud, reconnecte
// from->nouveau->to.
export function insertNodeOnEdge(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  edgeId: string,
  newNode: PipelineNode,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const edge = edges.find((e) => e.id === edgeId);
  if (!edge) return { nodes, edges };
  const rest = edges.filter((e) => e.id !== edgeId);
  return {
    nodes: [...nodes, newNode],
    edges: [...rest, { id: genEdgeId(), from: edge.from, to: newNode.id }, { id: genEdgeId(), from: newNode.id, to: edge.to }],
  };
}
```

- [ ] **Step 4: Run to verify `graphOps.ts` tests pass**

Run: `cd shell && npx vitest run src/builder/pipeline/graphOps.test.ts`
Expected: PASS (7 tests).

- [ ] **Step 5: Write the failing tests for `validation.ts`**

Create `shell/src/builder/pipeline/validation.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
import { isPipelineValid, validatePipelineGraphLocally } from "./validation";

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

function reader(id: string, params: Record<string, unknown> = { collectionId: "villes" }): PipelineNode {
  return { id, kind: "reader", op: "reader.collection", x: 0, y: 0, params };
}
function writer(id: string, params: Record<string, unknown> = { collectionId: "villes_propres" }): PipelineNode {
  return { id, kind: "writer", op: "writer.collection", x: 0, y: 0, params };
}

test("a valid linear reader->writer graph has no errors", () => {
  const nodes = [reader("r1"), writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toEqual([]);
  expect(result.nodeErrors).toEqual({ r1: [], w1: [] });
  expect(isPipelineValid(result)).toBe(true);
});

test("a graph with no reader node is invalid", () => {
  const result = validatePipelineGraphLocally([writer("w1")], [], CATALOG);
  expect(result.graphErrors).toContain("Le pipeline doit contenir au moins une source.");
  expect(isPipelineValid(result)).toBe(false);
});

test("a graph with no writer node is invalid", () => {
  const result = validatePipelineGraphLocally([reader("r1")], [], CATALOG);
  expect(result.graphErrors).toContain("Le pipeline doit contenir au moins une écriture.");
});

test("a cyclic graph is invalid", () => {
  const nodes = [reader("r1"), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "w1" },
    { id: "e2", from: "w1", to: "r1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toContain("Le graphe contient un cycle.");
});

test("a node with more than one incoming edge is invalid", () => {
  const nodes = [reader("r1"), reader("r2"), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "w1" },
    { id: "e2", from: "r2", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toContain("Un nœud ne peut avoir qu'une seule arête entrante (w1).");
});

test("a node missing a required param is flagged on that node, not as a graph error", () => {
  const nodes = [reader("r1", {}), writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toEqual([]);
  expect(result.nodeErrors.r1).toEqual(["collectionId est requis."]);
  expect(isPipelineValid(result)).toBe(false);
});

test("a node whose op is not in the catalogue is flagged on that node", () => {
  const nodes = [{ ...reader("r1"), op: "reader.does-not-exist" }, writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.r1).toEqual(["Opération inconnue : reader.does-not-exist."]);
});

test("isPipelineValid is false when any node has errors even if graphErrors is empty", () => {
  const result = { graphErrors: [], nodeErrors: { r1: ["x est requis."] } };
  expect(isPipelineValid(result)).toBe(false);
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/validation.test.ts`
Expected: FAIL — `Cannot find module './validation'`.

- [ ] **Step 7: Implement `validation.ts`**

Create `shell/src/builder/pipeline/validation.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";

export type PipelineValidationResult = {
  graphErrors: string[];
  nodeErrors: Record<string, string[]>;
};

export function isPipelineValid(result: PipelineValidationResult): boolean {
  return result.graphErrors.length === 0 && Object.values(result.nodeErrors).every((errs) => errs.length === 0);
}

// Vérification de forme uniquement (présence des champs requis) — jamais la
// sémantique d'une expression SQL bornée, cf. plan Global Constraints et
// design SP-15a §5.1 (frontière déjà actée, non rouverte ici).
function validateNodeParamsShape(entry: PipelineOpsCatalog[string], params: Record<string, unknown>): string[] {
  const errors: string[] = [];
  for (const field of entry.paramsSchema.required ?? []) {
    const value = params[field];
    if (value === undefined || value === null || value === "") {
      errors.push(`${field} est requis.`);
    }
  }
  return errors;
}

// Miroir client des quatre vérifications structurelles de
// app/configs/pipeline_validation.py (SP-15a) + la forme des params de
// chaque nœud — retour rapide pour l'éditeur (§4.3 du design). Le serveur
// reste la garde définitive à chaque POST/PUT /configs, inchangé.
export function validatePipelineGraphLocally(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  opsCatalog: PipelineOpsCatalog,
): PipelineValidationResult {
  const graphErrors: string[] = [];
  const nodeErrors: Record<string, string[]> = {};

  const incomingCount = new Map<string, number>();
  for (const e of edges) incomingCount.set(e.to, (incomingCount.get(e.to) ?? 0) + 1);
  for (const [nodeId, count] of incomingCount) {
    if (count > 1) graphErrors.push(`Un nœud ne peut avoir qu'une seule arête entrante (${nodeId}).`);
  }

  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) adjacency.get(e.from)?.push(e.to);
  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<string, number>(nodes.map((n) => [n.id, WHITE]));
  function visit(nodeId: string): boolean {
    color.set(nodeId, GRAY);
    for (const next of adjacency.get(nodeId) ?? []) {
      if (color.get(next) === GRAY) return true;
      if (color.get(next) === WHITE && visit(next)) return true;
    }
    color.set(nodeId, BLACK);
    return false;
  }
  if (nodes.some((n) => color.get(n.id) === WHITE && visit(n.id))) {
    graphErrors.push("Le graphe contient un cycle.");
  }

  if (!nodes.some((n) => n.kind === "reader")) graphErrors.push("Le pipeline doit contenir au moins une source.");
  if (!nodes.some((n) => n.kind === "writer")) graphErrors.push("Le pipeline doit contenir au moins une écriture.");

  for (const node of nodes) {
    const entry = opsCatalog[node.op];
    nodeErrors[node.id] = entry
      ? validateNodeParamsShape(entry, node.params)
      : [`Opération inconnue : ${node.op}.`];
  }

  return { graphErrors, nodeErrors };
}
```

- [ ] **Step 8: Run to verify `validation.ts` tests pass**

Run: `cd shell && npx vitest run src/builder/pipeline/validation.test.ts`
Expected: PASS (8 tests).

- [ ] **Step 9: Commit**

```bash
git add shell/src/builder/pipeline/graphOps.ts shell/src/builder/pipeline/graphOps.test.ts \
  shell/src/builder/pipeline/validation.ts shell/src/builder/pipeline/validation.test.ts
git commit -m "feat(shell): add pure pipeline graph helpers (cycle check, edge insert, local validation)"
```

---

## Task 4: `CollectionParamSelect` — readable/writable collection picker

**Files:**
- Create: `shell/src/builder/pipeline/CollectionParamSelect.tsx`
- Create: `shell/src/builder/pipeline/CollectionParamSelect.test.tsx`

**Interfaces:**
- Consumes: `useCollectionsAdmin` (existing hook, Task 2 untouched),
  `CollectionAdmin` (existing type).
- Produces: `CollectionParamSelect({ value, onChange, variant, ariaLabel })`
  — consumed by Task 5 (`PipelineNodeInspector`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/pipeline/CollectionParamSelect.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { CollectionParamSelect } from "./CollectionParamSelect";

const COLLECTIONS: CollectionAdmin[] = [
  { id: "villes", title: "Villes", description: "", tableName: "villes", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 10, owner: "alice" },
  { id: "readonly_layer", title: "Lecture seule", description: "", tableName: "readonly_layer", isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id", canWrite: false, featureCount: 3, owner: "bob" },
];

function renderSelect(props: Partial<Parameters<typeof CollectionParamSelect>[0]> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve(COLLECTIONS) };
  const onChange = vi.fn();
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <CollectionParamSelect value="" onChange={onChange} variant="readable" ariaLabel="Collection" {...props} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange };
}

test("variant=readable lists every collection", async () => {
  renderSelect({ variant: "readable" });
  await waitFor(() => expect(screen.getByRole("option", { name: /Lecture seule/ })).toBeInTheDocument());
  expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument();
});

test("variant=writable excludes collections the user cannot write", async () => {
  renderSelect({ variant: "writable" });
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  expect(screen.queryByRole("option", { name: /Lecture seule/ })).not.toBeInTheDocument();
});

test("selecting an option calls onChange with the collection id", async () => {
  const { onChange } = renderSelect({ variant: "readable" });
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Collection"), "villes");
  expect(onChange).toHaveBeenCalledWith("villes");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/CollectionParamSelect.test.tsx`
Expected: FAIL — `Cannot find module './CollectionParamSelect'`.

- [ ] **Step 3: Implement the component**

Create `shell/src/builder/pipeline/CollectionParamSelect.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useCollectionsAdmin } from "../../api/hooks";

// Filtre d'affichage seulement (variant="writable" ne montre que les
// collections avec canWrite) — jamais une frontière de sécurité : la vraie
// vérification lisible/éditable a lieu côté serveur à la sauvegarde
// (app/pipelines/config_validation.py, SP-15a) et à nouveau à l'exécution.
// Réutilise useCollectionsAdmin() tel quel : GET /collections est déjà
// scopé à ce que l'utilisateur courant peut voir (design SP-15b §4.4).
export function CollectionParamSelect({
  value,
  onChange,
  variant,
  ariaLabel,
}: {
  value: string;
  onChange: (collectionId: string) => void;
  variant: "readable" | "writable";
  ariaLabel: string;
}) {
  const collectionsQuery = useCollectionsAdmin();
  const options = (collectionsQuery.data ?? []).filter((c) => variant === "readable" || c.canWrite);

  return (
    <select
      aria-label={ariaLabel}
      className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
      value={value}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">Choisir…</option>
      {options.map((c) => (
        <option key={c.id} value={c.id}>{c.title}</option>
      ))}
    </select>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/CollectionParamSelect.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/CollectionParamSelect.tsx shell/src/builder/pipeline/CollectionParamSelect.test.tsx
git commit -m "feat(shell): add readable/writable collection picker for pipeline node params"
```

---

## Task 5: `PipelineNodeInspector` — JSON-Schema-driven params form

**Files:**
- Create: `shell/src/builder/pipeline/PipelineNodeInspector.tsx`
- Create: `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`

**Interfaces:**
- Consumes: `CollectionParamSelect` (Task 4), `PipelineOpEntry`,
  `PipelineNode` (Task 2).
- Produces: `PipelineNodeInspector({ node, opEntry, errors, onChange })` —
  consumed by Task 10 (`PipelineBuilderPage`).

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/pipeline/PipelineNodeInspector.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient, PipelineNode, PipelineOpEntry } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineNodeInspector } from "./PipelineNodeInspector";

const COLLECTIONS: CollectionAdmin[] = [
  { id: "villes", title: "Villes", description: "", tableName: "villes", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 10, owner: "alice" },
];

function renderInspector(node: PipelineNode, opEntry: PipelineOpEntry, onChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve(COLLECTIONS) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineNodeInspector node={node} opEntry={opEntry} errors={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange };
}

test("a collection-id format field renders a CollectionParamSelect", async () => {
  const node: PipelineNode = { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "" } };
  const opEntry: PipelineOpEntry = { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } };
  const { onChange } = renderInspector(node, opEntry);
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("collectionId"), "villes");
  expect(onChange).toHaveBeenCalledWith({ collectionId: "villes" });
});

test("an enum field renders a plain select with its options", () => {
  const node: PipelineNode = { id: "j1", kind: "transform", op: "transform.join", x: 0, y: 0, params: { withCollectionId: "villes", on: "code", how: "inner" } };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: {
      properties: {
        withCollectionId: { type: "string", format: "collection-id" },
        on: { type: "string" },
        how: { type: "string", enum: ["inner", "left"] },
      },
      required: ["withCollectionId", "on"],
    },
  };
  renderInspector(node, opEntry);
  const select = screen.getByLabelText("how") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.value)).toEqual(["inner", "left"]);
});

test("a string field renders a text input", async () => {
  const node: PipelineNode = { id: "f1", kind: "transform", op: "transform.filter", x: 0, y: 0, params: { expr: "" } };
  const opEntry: PipelineOpEntry = { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.type(screen.getByLabelText("expr"), "pop > 1000");
  expect(onChange).toHaveBeenLastCalledWith({ expr: "pop > 1000" });
});

test("an array-of-string field renders a comma-separated input parsed to a string array", async () => {
  const node: PipelineNode = { id: "a1", kind: "transform", op: "transform.aggregate", x: 0, y: 0, params: { groupBy: [], metrics: {} } };
  const opEntry: PipelineOpEntry = { kind: "transform", paramsSchema: { properties: { groupBy: { type: "array", items: { type: "string" } }, metrics: { type: "object" } }, required: [] } };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.type(screen.getByLabelText("groupBy"), "region, departement");
  expect(onChange).toHaveBeenLastCalledWith({ groupBy: ["region", "departement"], metrics: {} });
});

test("an object field renders a key-value editor; adding a row updates the dict", async () => {
  const node: PipelineNode = { id: "a1", kind: "transform", op: "transform.aggregate", x: 0, y: 0, params: { groupBy: [], metrics: {} } };
  const opEntry: PipelineOpEntry = { kind: "transform", paramsSchema: { properties: { groupBy: { type: "array", items: { type: "string" } }, metrics: { type: "object" } }, required: [] } };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter metrics" }));
  await userEvent.type(screen.getByLabelText("metrics clé 1"), "total_pop");
  await userEvent.type(screen.getByLabelText("metrics valeur 1"), "sum(pop)");
  expect(onChange).toHaveBeenLastCalledWith({ groupBy: [], metrics: { total_pop: "sum(pop)" } });
});

test("passed-in errors render as alerts", () => {
  const node: PipelineNode = { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} };
  const opEntry: PipelineOpEntry = { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve([]) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineNodeInspector node={node} opEntry={opEntry} errors={["collectionId est requis."]} onChange={vi.fn()} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("collectionId est requis.");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx`
Expected: FAIL — `Cannot find module './PipelineNodeInspector'`.

- [ ] **Step 3: Implement the component**

Create `shell/src/builder/pipeline/PipelineNodeInspector.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import type { PipelineNode, PipelineOpEntry, PipelineOpParamProperty } from "../../api/types";
import { CollectionParamSelect } from "./CollectionParamSelect";

// Édite un dict[str, str] (transform.aggregate.metrics) ou dict[str, str|null]
// (transform.select.columns) sous forme de lignes clé/valeur. Convention
// MVP pour transform.select : une valeur vidée équivaut à `null` (supprime
// la colonne) au moment de la sauvegarde — cf. design SP-15b §4.4 et le
// manifeste TransformSelectParams.columns côté cœur.
function KeyValueField({
  name, value, onChange,
}: {
  name: string;
  value: Record<string, string | null>;
  onChange: (next: Record<string, string | null>) => void;
}) {
  const rows = Object.entries(value);
  return (
    <div className="flex flex-col gap-1">
      <span className="text-xs font-medium text-slate-600">{name}</span>
      {rows.map(([key, val], i) => (
        <div key={i} className="flex gap-1">
          <input
            aria-label={`${name} clé ${i + 1}`}
            className="h-8 w-1/2 rounded border border-slate-300 px-2 text-xs"
            value={key}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              delete next[key];
              next[e.target.value] = val;
              onChange(next);
            }}
          />
          <input
            aria-label={`${name} valeur ${i + 1}`}
            className="h-8 w-1/2 rounded border border-slate-300 px-2 text-xs"
            value={val ?? ""}
            onChange={(e) => {
              const next = Object.fromEntries(rows);
              next[key] = e.target.value === "" ? null : e.target.value;
              onChange(next);
            }}
          />
        </div>
      ))}
      <button
        type="button"
        className="w-fit text-xs text-blue-600 hover:underline"
        onClick={() => onChange({ ...value, "": "" })}
      >
        Ajouter {name}
      </button>
    </div>
  );
}

function StringListField({
  name, value, onChange,
}: {
  name: string;
  value: string[];
  onChange: (next: string[]) => void;
}) {
  return (
    <label className="flex flex-col gap-1 text-xs">
      {name}
      <input
        aria-label={name}
        className="h-8 rounded border border-slate-300 px-2"
        defaultValue={value.join(", ")}
        onChange={(e) =>
          onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
        }
      />
    </label>
  );
}

export function PipelineNodeInspector({
  node, opEntry, errors, onChange,
}: {
  node: PipelineNode;
  opEntry: PipelineOpEntry;
  errors: string[];
  onChange: (params: Record<string, unknown>) => void;
}) {
  function setField(name: string, value: unknown) {
    onChange({ ...node.params, [name]: value });
  }

  function renderField(name: string, prop: PipelineOpParamProperty) {
    if (prop.format === "collection-id") {
      return (
        <CollectionParamSelect
          key={name}
          ariaLabel={name}
          value={String(node.params[name] ?? "")}
          variant={node.kind === "writer" ? "writable" : "readable"}
          onChange={(id) => setField(name, id)}
        />
      );
    }
    if (prop.enum) {
      return (
        <label key={name} className="flex flex-col gap-1 text-xs">
          {name}
          <select
            aria-label={name}
            className="h-9 rounded-md border border-slate-300 bg-white px-2 text-sm"
            value={String(node.params[name] ?? prop.default ?? "")}
            onChange={(e) => setField(name, e.target.value)}
          >
            {prop.enum.map((v) => <option key={v} value={v}>{v}</option>)}
          </select>
        </label>
      );
    }
    if (prop.type === "boolean") {
      return (
        <label key={name} className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            aria-label={name}
            checked={Boolean(node.params[name])}
            onChange={(e) => setField(name, e.target.checked)}
          />
          {name}
        </label>
      );
    }
    if (prop.type === "array") {
      return (
        <StringListField
          key={name}
          name={name}
          value={(node.params[name] as string[] | undefined) ?? []}
          onChange={(v) => setField(name, v)}
        />
      );
    }
    if (prop.type === "object") {
      return (
        <KeyValueField
          key={name}
          name={name}
          value={(node.params[name] as Record<string, string | null> | undefined) ?? {}}
          onChange={(v) => setField(name, v)}
        />
      );
    }
    return (
      <label key={name} className="flex flex-col gap-1 text-xs">
        {name}
        <input
          type={prop.type === "number" || prop.type === "integer" ? "number" : "text"}
          aria-label={name}
          className="h-8 rounded border border-slate-300 px-2"
          value={String(node.params[name] ?? "")}
          onChange={(e) =>
            setField(name, prop.type === "number" || prop.type === "integer" ? Number(e.target.value) : e.target.value)
          }
        />
      </label>
    );
  }

  return (
    <div className="flex flex-col gap-2 p-2">
      {Object.entries(opEntry.paramsSchema.properties).map(([name, prop]) => renderField(name, prop))}
      {errors.map((err) => (
        <p key={err} role="alert" className="text-xs text-red-600">{err}</p>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineNodeInspector.test.tsx`
Expected: PASS (6 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineNodeInspector.tsx shell/src/builder/pipeline/PipelineNodeInspector.test.tsx
git commit -m "feat(shell): add JSON-Schema-driven pipeline node params inspector"
```

---

## Task 6: `PipelineCanvas` — React Flow wrapper

**Files:**
- Modify: `shell/package.json` (add `@xyflow/react`)
- Create: `shell/src/builder/pipeline/PipelineCanvas.tsx`
- Create: `shell/src/builder/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: `PipelineNode`, `PipelineEdge` (Task 2), `wouldCreateCycle`,
  `hasIncomingEdge`, `insertNodeOnEdge`, `genEdgeId` (Task 3).
- Produces: `PipelineCanvas({ nodes, edges, selectedNodeId, onSelectNode,
  onNodesChange, onEdgesChange, onInsertOnEdge })` — consumed by Task 10.

- [ ] **Step 1: Install the dependency**

Run: `cd shell && npm install @xyflow/react@^12`

- [ ] **Step 2: Write the failing test**

Create `shell/src/builder/pipeline/PipelineCanvas.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { PipelineEdge, PipelineNode } from "../../api/types";
import { PipelineCanvas } from "./PipelineCanvas";

// @xyflow/react appelle ResizeObserver sans garde — stub local à ce fichier
// uniquement, même patron que EChart.test.tsx (cf. plan Global Constraints).
beforeEach(() => {
  vi.stubGlobal("ResizeObserver", vi.fn().mockImplementation(() => ({
    observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn(),
  })));
});
afterEach(() => vi.unstubAllGlobals());

const NODES: PipelineNode[] = [
  { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
  { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
];
const EDGES: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];

test("renders one labeled element per node", () => {
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} />,
  );
  expect(screen.getByText("Villes")).toBeInTheDocument();
  expect(screen.getByText("Écriture")).toBeInTheDocument();
});

test("clicking a node calls onSelectNode with its id", () => {
  const onSelectNode = vi.fn();
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={onSelectNode}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={vi.fn()} />,
  );
  fireEvent.click(screen.getByText("Villes"));
  expect(onSelectNode).toHaveBeenCalledWith("r1");
});

test("the edge's insert button is present and triggers onInsertOnEdge with the edge id and a chosen op", () => {
  const onInsertOnEdge = vi.fn();
  render(
    <PipelineCanvas nodes={NODES} edges={EDGES} selectedNodeId={null} onSelectNode={vi.fn()}
      onNodesChange={vi.fn()} onEdgesChange={vi.fn()} onInsertOnEdge={onInsertOnEdge} />,
  );
  fireEvent.click(screen.getByRole("button", { name: "Insérer une étape sur cette arête" }));
  fireEvent.click(screen.getByRole("menuitem", { name: "Filtrer" }));
  expect(onInsertOnEdge).toHaveBeenCalledWith("e1", "transform.filter");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: FAIL — `Cannot find module './PipelineCanvas'`.

- [ ] **Step 4: Implement `PipelineCanvas.tsx`**

Create `shell/src/builder/pipeline/PipelineCanvas.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";
import {
  Background, Controls, EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider,
  getBezierPath,
  type Edge, type EdgeChange, type EdgeProps, type Node, type NodeChange, type NodeProps, type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PipelineEdge, PipelineNode } from "../../api/types";
import { genEdgeId, hasIncomingEdge, wouldCreateCycle } from "./graphOps";

// Les 5 op transform.* insérables sur une arête (cf. plan Task 6 — clic sur
// le "+" d'une arête, pas de drag-drop précis sur le tracé SVG).
const INSERTABLE_TRANSFORMS: { op: string; label: string }[] = [
  { op: "transform.filter", label: "Filtrer" },
  { op: "transform.select", label: "Sélectionner" },
  { op: "transform.derive", label: "Dériver" },
  { op: "transform.aggregate", label: "Agréger" },
  { op: "transform.join", label: "Joindre" },
];

const KIND_COLOR: Record<PipelineNode["kind"], string> = {
  reader: "border-emerald-500 bg-emerald-50",
  transform: "border-amber-500 bg-amber-50",
  writer: "border-sky-500 bg-sky-50",
};

function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as PipelineNode;
  return (
    <div className={`rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-blue-500" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="font-medium">{node.title ?? node.op}</div>
      <div className="text-[10px] text-slate-500">{node.op}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function InsertOnEdgeButton({ id, sourceX, sourceY, targetX, targetY, onInsert }: EdgeProps & { onInsert: (edgeId: string, op: string) => void }) {
  const [open, setOpen] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  return (
    <>
      <path id={id} className="react-flow__edge-path" d={edgePath} />
      <EdgeLabelRenderer>
        <div style={{ position: "absolute", transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: "all" }}>
          <button
            type="button"
            aria-label="Insérer une étape sur cette arête"
            className="h-5 w-5 rounded-full border border-slate-400 bg-white text-xs leading-none hover:bg-slate-100"
            onClick={() => setOpen((o) => !o)}
          >
            +
          </button>
          {open && (
            <ul role="menu" className="absolute z-10 mt-1 rounded border border-slate-300 bg-white text-xs shadow">
              {INSERTABLE_TRANSFORMS.map((t) => (
                <li key={t.op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-slate-100"
                    onClick={() => { onInsert(id, t.op); setOpen(false); }}
                  >
                    {t.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

function toFlowNode(n: PipelineNode, selected: boolean): Node {
  return { id: n.id, position: { x: n.x, y: n.y }, data: n as unknown as Record<string, unknown>, type: "pipelineNode", selected };
}
function toFlowEdge(e: PipelineEdge): Edge {
  return { id: e.id, source: e.from, target: e.to, type: "insertable" };
}

function PipelineCanvasInner({
  nodes, edges, selectedNodeId, onSelectNode, onNodesChange, onEdgesChange, onInsertOnEdge,
}: {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onNodesChange: (nodes: PipelineNode[]) => void;
  onEdgesChange: (edges: PipelineEdge[]) => void;
  onInsertOnEdge: (edgeId: string, op: string) => void;
}) {
  const nodeTypes = { pipelineNode: PipelineNodeBox };
  const edgeTypes = { insertable: (props: EdgeProps) => <InsertOnEdgeButton {...props} onInsert={onInsertOnEdge} /> };

  const onConnect: OnConnect = useCallback((connection) => {
    if (!connection.source || !connection.target) return;
    if (hasIncomingEdge(edges, connection.target)) return; // garde §3.4 : ≤ 1 arête entrante
    if (wouldCreateCycle(nodes, edges, { from: connection.source, to: connection.target })) return;
    onEdgesChange([...edges, { id: genEdgeId(), from: connection.source, to: connection.target }]);
  }, [nodes, edges, onEdgesChange]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    let next = nodes;
    for (const change of changes) {
      if (change.type === "position" && change.position) {
        next = next.map((n) => (n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n));
      }
      if (change.type === "remove") {
        next = next.filter((n) => n.id !== change.id);
      }
      // Ne réagit qu'à l'événement "sélectionné" (jamais "déselectionné") :
      // un clic sur un nouveau nœud émet deux changements dans un ordre non
      // garanti (ancien nœud selected:false, nouveau selected:true) — ne
      // traiter que selected:true rend la sélection robuste à cet ordre.
      // La désélection (clic sur le fond) passe par onPaneClick ci-dessous.
      if (change.type === "select" && change.selected) {
        onSelectNode(change.id);
      }
    }
    if (next !== nodes) onNodesChange(next);
  }, [nodes, onNodesChange, onSelectNode]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removedIds = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
    if (removedIds.size) onEdgesChange(edges.filter((e) => !removedIds.has(e.id)));
  }, [edges, onEdgesChange]);

  return (
    <div style={{ height: 480 }}>
      <ReactFlow
        nodes={nodes.map((n) => toFlowNode(n, n.id === selectedNodeId))}
        edges={edges.map(toFlowEdge)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onConnect={onConnect}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onPaneClick={() => onSelectNode(null)}
        deleteKeyCode={["Backspace", "Delete"]}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function PipelineCanvas(props: React.ComponentProps<typeof PipelineCanvasInner>) {
  return (
    <ReactFlowProvider>
      <PipelineCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineCanvas.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 6: Type check**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/package.json shell/package-lock.json shell/src/builder/pipeline/PipelineCanvas.tsx shell/src/builder/pipeline/PipelineCanvas.test.tsx
git commit -m "feat(shell): add PipelineCanvas (React Flow wrapper with connection guard and edge-insert)"
```

---

## Task 7: `PipelinePalette` — draggable op list

**Files:**
- Create: `shell/src/builder/pipeline/PipelinePalette.tsx`
- Create: `shell/src/builder/pipeline/PipelinePalette.test.tsx`

**Interfaces:**
- Consumes: `usePipelineOps` (Task 2).
- Produces: `PipelinePalette()` — renders draggable entries that set
  `dataTransfer` under MIME type `application/x-geostudio-pipeline-op`;
  consumed by Task 10, which reads that MIME type in `PipelineBuilderPage`'s
  canvas-pane `onDrop` handler.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/pipeline/PipelinePalette.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test } from "vitest";
import type { ItemClient, PipelineOpsCatalog } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelinePalette } from "./PipelinePalette";

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: {}, required: [] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: {}, required: [] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: {}, required: [] } },
};

function renderPalette() {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { getPipelineOps: () => Promise.resolve(CATALOG) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePalette />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("groups ops into three sections by kind", async () => {
  renderPalette();
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Transforms" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Écritures" })).toBeInTheDocument();
});

test("each entry is draggable and sets the op id on dragstart", async () => {
  renderPalette();
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  const entry = screen.getByText("reader.collection").closest("[draggable]") as HTMLElement;
  expect(entry).toHaveAttribute("draggable", "true");
  const dataTransfer = { setData: (type: string, value: string) => { (dataTransfer as any)[type] = value; }, effectAllowed: "" };
  fireEvent.dragStart(entry, { dataTransfer });
  expect((dataTransfer as any)["application/x-geostudio-pipeline-op"]).toBe("reader.collection");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx`
Expected: FAIL — `Cannot find module './PipelinePalette'`.

- [ ] **Step 3: Implement the component**

Create `shell/src/builder/pipeline/PipelinePalette.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";

export const PIPELINE_OP_DND_TYPE = "application/x-geostudio-pipeline-op";

const SECTION_LABEL: Record<PipelineNodeKind, string> = {
  reader: "Sources",
  transform: "Transforms",
  writer: "Écritures",
};

export function PipelinePalette() {
  const opsQuery = usePipelineOps();
  const catalog = opsQuery.data ?? {};
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) byKind[entry.kind].push(op);

  return (
    <div className="flex flex-col gap-3 p-2 text-xs">
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-slate-600">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => (
              <li key={op}>
                <div
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  className="cursor-grab rounded border border-slate-300 bg-white px-2 py-1 hover:bg-slate-50"
                >
                  {op}
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePalette.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelinePalette.tsx shell/src/builder/pipeline/PipelinePalette.test.tsx
git commit -m "feat(shell): add draggable pipeline op palette"
```

---

## Task 8: `PipelinePreviewPanel`

**Files:**
- Create: `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`
- Create: `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`

**Interfaces:**
- Consumes: `previewPipeline` (Task 2, via a new `usePipelinePreview` query
  hook added in this task's implementation step, `hooks.ts`).
- Produces: `PipelinePreviewPanel({ pipelineId, nodeId })` — consumed by
  Task 10.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelinePreviewPanel } from "./PipelinePreviewPanel";

function renderPanel(previewPipeline = vi.fn().mockResolvedValue([{ id: 1, pop: 1200 }])) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId="r1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { previewPipeline };
}

test("fetches the preview for the given node and renders it as a table", async () => {
  const { previewPipeline } = renderPanel();
  await waitFor(() => expect(screen.getByRole("cell", { name: "1200" })).toBeInTheDocument());
  expect(previewPipeline).toHaveBeenCalledWith("p-1", "r1");
});

test("shows nothing when no node is selected", () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { previewPipeline: vi.fn() };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePreviewPanel pipelineId="p-1" nodeId={null} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.queryByRole("table")).not.toBeInTheDocument();
});

test("surfaces a fetch error", async () => {
  renderPanel(vi.fn().mockRejectedValue(new Error("bad expr")));
  await waitFor(() => expect(screen.getByRole("alert")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx`
Expected: FAIL — `Cannot find module './PipelinePreviewPanel'`.

- [ ] **Step 3: Add `usePipelinePreview` and implement the component**

In `shell/src/api/hooks.ts`, add after `usePipelineOps` (from Task 2, Step 7):

```ts
export function usePipelinePreview(pipelineId: string, nodeId: string | null) {
  const client = useItemClientInternal();
  return useQuery({
    queryKey: ["pipeline-preview", pipelineId, nodeId],
    queryFn: () => client.previewPipeline(pipelineId, nodeId!),
    enabled: nodeId !== null,
  });
}
```

Create `shell/src/builder/pipeline/PipelinePreviewPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { usePipelinePreview } from "../../api/hooks";

export function PipelinePreviewPanel({ pipelineId, nodeId }: { pipelineId: string; nodeId: string | null }) {
  const previewQuery = usePipelinePreview(pipelineId, nodeId);

  if (nodeId === null) return null;
  if (previewQuery.isLoading) return <p role="status">Chargement de l'aperçu…</p>;
  if (previewQuery.isError) return <p role="alert" className="text-sm text-red-600">Aperçu indisponible.</p>;

  const rows = previewQuery.data ?? [];
  const columns = rows.length > 0 ? Object.keys(rows[0]) : [];

  return (
    <table className="w-full text-xs">
      <thead>
        <tr>{columns.map((c) => <th key={c} className="p-1 text-left">{c}</th>)}</tr>
      </thead>
      <tbody>
        {rows.map((row, i) => (
          <tr key={i} className="border-t border-slate-200">
            {columns.map((c) => <td key={c} className="p-1">{String(row[c])}</td>)}
          </tr>
        ))}
      </tbody>
    </table>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelinePreviewPanel.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/builder/pipeline/PipelinePreviewPanel.tsx shell/src/builder/pipeline/PipelinePreviewPanel.test.tsx
git commit -m "feat(shell): add bounded pipeline data preview panel"
```

---

## Task 9: `PipelineRunPanel` — run button + poll + history

**Files:**
- Create: `shell/src/builder/pipeline/PipelineRunPanel.tsx`
- Create: `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`

**Interfaces:**
- Consumes: `runPipeline`, `getPipelineRuns` (Task 2).
- Produces: `PipelineRunPanel({ pipelineId })` — consumed by Task 10.

- [ ] **Step 1: Write the failing test**

Create `shell/src/builder/pipeline/PipelineRunPanel.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, PipelineRun } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineRunPanel } from "./PipelineRunPanel";

function renderPanel(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([] as PipelineRun[]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

test("shows the run history from getPipelineRuns on mount", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-0", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null, nodeStats: {} },
    ]),
  });
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument());
});

test("clicking Exécuter runs the pipeline then polls until the run leaves queued/running", async () => {
  let call = 0;
  const getPipelineRuns = vi.fn().mockImplementation(() => {
    call += 1;
    const status = call < 2 ? "running" : "succeeded";
    return Promise.resolve([{ id: "run-1", status, startedAt: "2026-08-06T10:00:00Z", finishedAt: null, error: null, nodeStats: {} }]);
  });
  renderPanel({ getPipelineRuns });
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument(), { timeout: 5000 });
  expect(call).toBeGreaterThanOrEqual(2);
});

test("a failed run shows its error message", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-2", status: "failed", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:01Z", error: "collection introuvable", nodeStats: {} },
    ]),
  });
  await waitFor(() => expect(screen.getByText("collection introuvable")).toBeInTheDocument());
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx`
Expected: FAIL — `Cannot find module './PipelineRunPanel'`.

- [ ] **Step 3: Implement the component**

Create `shell/src/builder/pipeline/PipelineRunPanel.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useItemClient } from "../../api/hooks";
import type { PipelineRun } from "../../api/types";
import { Button } from "../../ui/button";

const STATUS_LABEL: Record<PipelineRun["status"], string> = {
  queued: "En attente", running: "En cours", succeeded: "succeeded", failed: "failed",
};

// Patron de poll identique à shell/src/shell/ImportFileButton.tsx (SP-6a) —
// boucle récursive manuelle via le client, pas un refetchInterval react-query
// (cf. plan Global Constraints).
export function PipelineRunPanel({ pipelineId }: { pipelineId: string }) {
  const client = useItemClient();
  const [runs, setRuns] = useState<PipelineRun[]>([]);
  const [running, setRunning] = useState(false);

  async function loadRuns() {
    setRuns(await client.getPipelineRuns(pipelineId));
  }

  useEffect(() => {
    loadRuns();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pipelineId]);

  async function poll() {
    for (;;) {
      const latest = await client.getPipelineRuns(pipelineId);
      setRuns(latest);
      const status = latest[0]?.status;
      if (status !== "queued" && status !== "running") {
        setRunning(false);
        return;
      }
      await new Promise((r) => setTimeout(r, 1500));
    }
  }

  async function onRun() {
    setRunning(true);
    await client.runPipeline(pipelineId);
    await poll();
  }

  return (
    <div className="flex flex-col gap-2">
      <Button size="sm" onClick={onRun} disabled={running}>
        {running ? "Exécution…" : "Exécuter"}
      </Button>
      <ul className="flex flex-col gap-1 text-xs">
        {runs.map((run) => (
          <li key={run.id} className="border-t border-slate-200 pt-1">
            <span>{STATUS_LABEL[run.status]}</span>
            {run.startedAt && <span className="ml-2 text-slate-500">{run.startedAt}</span>}
            {run.error && <p role="alert" className="text-red-600">{run.error}</p>}
          </li>
        ))}
      </ul>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pipeline/PipelineRunPanel.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/pipeline/PipelineRunPanel.tsx shell/src/builder/pipeline/PipelineRunPanel.test.tsx
git commit -m "feat(shell): add pipeline run button with poll and run history"
```

---

## Task 10: `PipelineBuilderPage` — composition, unsaved/persisted modes

**Files:**
- Create: `shell/src/pages/PipelineBuilderPage.tsx`
- Create: `shell/src/pages/PipelineBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `PipelineCanvas` (Task 6), `PipelinePalette` (Task 7),
  `PipelineNodeInspector` (Task 5), `PipelinePreviewPanel` (Task 8),
  `PipelineRunPanel` (Task 9), `validatePipelineGraphLocally`,
  `isPipelineValid`, `insertNodeOnEdge`, `genNodeId` (Task 3),
  `usePipelineConfig`, `useCreatePipeline`, `useSavePipeline`,
  `usePipelineOps` (Task 2), `PIPELINE_OP_DND_TYPE` (Task 7).
- Produces: `PipelineBuilderPage({ pk, initialTitle }: { pk: string | null;
  initialTitle?: string })` — `pk === null` is the unsaved-draft mode
  (`/pipelines/new`); a non-null `pk` is the persisted mode
  (`/pipelines/:pk/edit`). Consumed by Task 11's routes.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/pages/PipelineBuilderPage.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Item, ItemClient, PipelineOpsCatalog, PipelinePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { PipelineBuilderPage } from "./PipelineBuilderPage";

// PipelineBuilderPage calls useAuth() for `username` on save — same mock as
// shell/src/shell/NewItemButton.test.tsx, needed because the real hook calls
// react-oidc-context's useAuth(), which throws without an AuthProvider.
vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false, isAuthenticated: true, username: "alice",
    getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(), error: null,
  }),
}));

beforeEach(() => {
  vi.stubGlobal("ResizeObserver", vi.fn().mockImplementation(() => ({
    observe: vi.fn(), unobserve: vi.fn(), disconnect: vi.fn(),
  })));
});
afterEach(() => vi.unstubAllGlobals());

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

function renderPage(pk: string | null, overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(CATALOG),
    listCollections: () => Promise.resolve([]),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <PipelineBuilderPage pk={pk} initialTitle="Nettoyer villes" />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { client };
}

test("unsaved mode: Enregistrer is disabled on an empty graph", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled();
});

test("unsaved mode: Aperçu and Exécuter are absent (no pipelineId yet)", async () => {
  renderPage(null);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Exécuter" })).not.toBeInTheDocument();
});

test("persisted mode: loads the existing graph and shows Exécuter", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload) });
  await waitFor(() => expect(screen.getByText("Villes")).toBeInTheDocument());
  expect(screen.getByRole("button", { name: "Exécuter" })).toBeInTheDocument();
});

test("persisted mode: Enregistrer calls savePipelineConfig with the current graph", async () => {
  const payload: PipelinePayload = {
    nodes: [
      { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: { collectionId: "villes" }, title: "Villes" },
      { id: "w1", kind: "writer", op: "writer.collection", x: 300, y: 0, params: { collectionId: "villes_propres" }, title: "Écriture" },
    ],
    edges: [{ id: "e1", from: "r1", to: "w1" }],
  };
  const savePipelineConfig = vi.fn().mockResolvedValue(undefined);
  renderPage("p-1", { getPipelineConfig: () => Promise.resolve(payload), savePipelineConfig });
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(savePipelineConfig).toHaveBeenCalledWith("p-1", payload));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: FAIL — `Cannot find module './PipelineBuilderPage'`.

- [ ] **Step 3: Implement the page**

Create `shell/src/pages/PipelineBuilderPage.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreatePipeline, usePipelineConfig, usePipelineOps, useSavePipeline } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import type { PipelineEdge, PipelineNode, PipelinePayload } from "../api/types";
import { Button } from "../ui/button";
import { PipelineCanvas } from "../builder/pipeline/PipelineCanvas";
import { PipelineNodeInspector } from "../builder/pipeline/PipelineNodeInspector";
import { PipelinePalette, PIPELINE_OP_DND_TYPE } from "../builder/pipeline/PipelinePalette";
import { PipelinePreviewPanel } from "../builder/pipeline/PipelinePreviewPanel";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { genNodeId, insertNodeOnEdge } from "../builder/pipeline/graphOps";
import { isPipelineValid, validatePipelineGraphLocally } from "../builder/pipeline/validation";

const EMPTY_PAYLOAD: PipelinePayload = { nodes: [], edges: [] };

// pk === null : brouillon local (/pipelines/new, design SP-15b §2.2) —
// rien n'est persisté avant le premier "Enregistrer" (choix de session : le
// validateur serveur exige déjà ≥1 reader/≥1 writer, donc il n'existe pas de
// payload trivial à créer immédiatement comme pour app/dashboard/map/site).
export function PipelineBuilderPage({ pk, initialTitle }: { pk: string | null; initialTitle?: string }) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const opsQuery = usePipelineOps();
  const configQuery = usePipelineConfig(pk ?? "", { enabled: pk !== null });
  const createPipeline = useCreatePipeline();
  const savePipeline = useSavePipeline(pk ?? "");

  const [draft, setDraft] = useState<PipelinePayload>(EMPTY_PAYLOAD);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;
  if (opsQuery.isLoading || !opsQuery.data) return <p role="status">Chargement…</p>;

  const catalog = opsQuery.data;
  const validation = validatePipelineGraphLocally(draft.nodes, draft.edges, catalog);
  const valid = isPipelineValid(validation);
  const selectedNode = draft.nodes.find((n) => n.id === selectedNodeId) ?? null;

  function setNodes(nodes: PipelineNode[]) {
    setDraft((d) => ({ ...d, nodes }));
  }
  function setEdges(edges: PipelineEdge[]) {
    setDraft((d) => ({ ...d, edges }));
  }
  function updateSelectedNodeParams(params: Record<string, unknown>) {
    if (!selectedNode) return;
    setNodes(draft.nodes.map((n) => (n.id === selectedNode.id ? { ...n, params } : n)));
  }
  function onInsertOnEdge(edgeId: string, op: string) {
    const kind = catalog[op]?.kind ?? "transform";
    const result = insertNodeOnEdge(draft.nodes, draft.edges, edgeId, {
      id: genNodeId(), kind, op, x: 0, y: 0, params: {}, title: op,
    });
    setDraft(result);
  }
  function onDropOnCanvas(op: string, position: { x: number; y: number }) {
    const kind = catalog[op]?.kind ?? "transform";
    setNodes([...draft.nodes, { id: genNodeId(), kind, op, x: position.x, y: position.y, params: {}, title: op }]);
  }

  async function onSave() {
    if (pk === null) {
      const item = await createPipeline.mutateAsync({ title: initialTitle ?? "", owner: username ?? "", pipeline: draft });
      navigate(`/pipelines/${item.pk}/edit`, { replace: true });
      return;
    }
    await savePipeline.mutateAsync(draft);
  }

  return (
    <div
      className="flex gap-4"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const op = e.dataTransfer.getData(PIPELINE_OP_DND_TYPE);
        if (!op) return;
        onDropOnCanvas(op, { x: e.clientX, y: e.clientY });
      }}
    >
      <PipelinePalette />
      <div className="flex flex-1 flex-col gap-2">
        <div className="flex items-center justify-between">
          <h2 className="text-lg font-semibold">{initialTitle ?? "Pipeline"}</h2>
          <Button size="sm" onClick={onSave} disabled={!valid || createPipeline.isPending || savePipeline.isPending}>
            Enregistrer
          </Button>
        </div>
        <PipelineCanvas
          nodes={draft.nodes}
          edges={draft.edges}
          selectedNodeId={selectedNodeId}
          onSelectNode={setSelectedNodeId}
          onNodesChange={setNodes}
          onEdgesChange={setEdges}
          onInsertOnEdge={onInsertOnEdge}
        />
        {pk !== null && <PipelineRunPanel pipelineId={pk} />}
      </div>
      <div className="w-64 shrink-0 border-l border-slate-200 pl-4">
        {selectedNode && catalog[selectedNode.op] && (
          <>
            <PipelineNodeInspector
              node={selectedNode}
              opEntry={catalog[selectedNode.op]}
              errors={validation.nodeErrors[selectedNode.id] ?? []}
              onChange={updateSelectedNodeParams}
            />
            {pk !== null && <PipelinePreviewPanel pipelineId={pk} nodeId={selectedNode.id} />}
          </>
        )}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/PipelineBuilderPage.test.tsx`
Expected: PASS (4 tests).

- [ ] **Step 5: Type check and full component-test suite**

Run: `cd shell && npx tsc --noEmit && npx vitest run`
Expected: PASS — no regression across the whole Vitest suite (398+ pre-existing tests plus everything added in Tasks 1-10).

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/PipelineBuilderPage.tsx shell/src/pages/PipelineBuilderPage.test.tsx
git commit -m "feat(shell): add PipelineBuilderPage composing canvas/palette/inspector/preview/run"
```

---

## Task 11: Creation flow, routing, `etlEnabled` gating

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Modify: `shell/src/shell/NewItemButton.test.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Modify: `shell/src/pages/ItemDetailPage.tsx`
- Modify: `shell/src/pages/ItemDetailPage.test.tsx`

**Interfaces:**
- Consumes: `PipelineBuilderPage` (Task 10), `useInstanceInfo` (Task 2).
- Produces: `NewItemButton`'s `Kind` union gains `"pipeline"`; new routes
  `/pipelines/new` and `/pipelines/:pk/edit`; `useOpenItem`/`ItemDetailPage`
  route pipelines to their editor. No new exported interface consumed
  elsewhere — this is the final integration task.

- [ ] **Step 1: Write the failing `NewItemButton` tests**

`shell/src/shell/NewItemButton.test.tsx` has no shared render helper for the
"probe route" tests (the `Map`/`dataset`/`arcgis` tests each inline their own
`QueryClientProvider`/`ItemClientProvider`/`MemoryRouter` + probe component,
since each needs a different extra route). Append, following that exact
pattern, and using the file's existing `http`/`HttpResponse`/`server`
imports (already imported at the top of the file):

```tsx
test("the Pipeline option is absent from the Type select when etlEnabled is false (the MSW default)", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.queryByRole("option", { name: "Pipeline" })).not.toBeInTheDocument();
});

test("the Pipeline option is present when etlEnabled is true", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false, etlEnabled: true })),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(await screen.findByRole("option", { name: "Pipeline" })).toBeInTheDocument();
});

test("selecting Pipeline only asks for a title, and navigates to /pipelines/new with the title in route state, without calling the create API", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: false, etlEnabled: true })),
  );
  let configPosted = false;
  server.use(
    http.post("https://core.test/configs", () => {
      configPosted = true;
      return HttpResponse.json({ id: "cfg-x", kind: "app", itemId: "x" });
    }),
  );
  function PipelineNewProbe() {
    const location = useLocation();
    const state = location.state as { title?: string } | null;
    return <div>pipeline-new-{state?.title ?? ""}</div>;
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/apps/:pk/edit" element={<AppBuilderProbe />} />
            <Route path="/pipelines/new" element={<PipelineNewProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "pipeline");
  await userEvent.type(screen.getByLabelText("Titre"), "Nettoyer villes");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("pipeline-new-Nettoyer villes")).toBeInTheDocument();
  expect(configPosted).toBe(false);
});
```

Add `useLocation` to the existing `react-router-dom` import (line 5) — the
file already imports `MemoryRouter, Route, Routes, useParams` from it.

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: FAIL — `pipeline` is not a valid `<option>` value / `navigateSpy`
never called with `/pipelines/new`.

- [ ] **Step 3: Implement the `NewItemButton` changes**

In `shell/src/shell/NewItemButton.tsx`:

Add `useInstanceInfo` to the hooks import (line 4).

Change line 12:

```ts
type Kind = "app" | "dashboard" | "map" | "site" | "dataset" | "pipeline";
```

In the component body, add right after `const createDataset = useCreateDataset();` (line 28):

```ts
  const instanceQuery = useInstanceInfo();
  const etlEnabled = instanceQuery.data?.etlEnabled === true;
```

In `submit`, before the existing `kind === "map" ? ... : kind === "dataset" ? ...` ternary chain, add a pipeline branch that short-circuits before any API call:

```ts
  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    if (kind === "site" && !isValidSlug(slug)) return;
    if (kind === "dataset" && datasetSource === "collection" && !collectionId) return;
    if (kind === "dataset" && datasetSource === "arcgis" && !arcgisItemId) return;
    if (kind === "pipeline") {
      close();
      navigate("/pipelines/new", { state: { title: clean } });
      return;
    }
    try {
      // ...unchanged...
```

In the `<select>` for Type, add the option, guarded by `etlEnabled`:

```tsx
              <option value="dataset">Dataset partagé</option>
              {etlEnabled && <option value="pipeline">Pipeline</option>}
```

The "Modèle" block's condition (`kind !== "map" && kind !== "dataset"`)
needs `&& kind !== "pipeline"` added — a pipeline has no template:

```tsx
          {kind !== "map" && kind !== "dataset" && kind !== "pipeline" && (
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: PASS (all pre-existing tests + 3 new ones).

- [ ] **Step 5: Write the failing `ItemDetailPage` test**

In `shell/src/pages/ItemDetailPage.test.tsx`, add `http, HttpResponse` (from
`"msw"`), `server` (from `"../test/msw/server"`), and `userEvent` (from
`"@testing-library/user-event"`) to the imports at the top of the file, then
append:

```tsx
test("shows 'Ouvrir dans l'éditeur' for a pipeline item and calls onOpenEditor('pipeline')", async () => {
  server.use(
    http.get("https://core.test/items/7", () =>
      HttpResponse.json({
        pk: "7", resourceType: "pipeline", title: "Item 7", abstract: "Abstract 7",
        owner: "alice", thumbnailUrl: null, date: "2026-01-01T00:00:00Z", configId: null, isPublished: false,
      }),
    ),
  );
  const onOpenEditor = vi.fn();
  render(<ItemDetailPage pk="7" onOpenEditor={onOpenEditor} />, { wrapper });
  const button = await screen.findByRole("button", { name: /éditeur/i });
  expect(button).not.toBeDisabled();
  await userEvent.click(button);
  expect(onOpenEditor).toHaveBeenCalledWith("pipeline");
});
```

- [ ] **Step 6: Run to verify it fails, then fix `ItemDetailPage.tsx`**

Run: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx`
Expected: FAIL.

In `shell/src/pages/ItemDetailPage.tsx` line 29, add `"pipeline"`:

```ts
      {["map", "app", "dashboard", "dataset", "pipeline"].includes(item.resourceType) ? (
```

Run again: `cd shell && npx vitest run src/pages/ItemDetailPage.test.tsx`
Expected: PASS.

- [ ] **Step 7: Wire the routes**

In `shell/src/shell/routes.tsx`, add the import:

```ts
import { PipelineBuilderPage } from "../pages/PipelineBuilderPage";
```

Add `"pipeline"` handling to both navigation switches. In `useOpenItem`
(after the `type === "bookmark"` early-return block, before the final
`navigate(...)` line at 53):

```ts
    if (type === "pipeline") {
      navigate(`/pipelines/${pk}/edit`);
      return;
    }
```

And update the final fallback line to keep `"dataset"` and now exclude
`"pipeline"` from ever reaching the `/apps/:pk/edit` default (it already
returns above, so the line itself is unchanged — no edit needed there).

In `ItemDetailRoute` (line ~93), extend the ternary:

```tsx
      onOpenEditor={(type) => navigate(
        type === "map" ? `/maps/${pk}` :
        type === "dataset" ? `/datasets/${pk}/edit` :
        type === "pipeline" ? `/pipelines/${pk}/edit` :
        `/apps/${pk}/edit`
      )}
```

Add two new route components, mirroring `DatasetEditRoute` (after line 111):

```tsx
function PipelineNewRoute() {
  const location = useLocation();
  const title = (location.state as { title?: string } | null)?.title;
  return <PipelineBuilderPage pk={null} initialTitle={title} />;
}

function PipelineEditRoute() {
  const { pk } = useParams();
  return <PipelineBuilderPage pk={pk!} />;
}
```

Add `useLocation` to the `react-router-dom` import (line 3).

Register both routes inside `<Route element={<ProtectedLayout />}>`, right
after `/datasets/:pk/edit` (line 152):

```tsx
        <Route path="/pipelines/new" element={<PipelineNewRoute />} />
        <Route path="/pipelines/:pk/edit" element={<PipelineEditRoute />} />
```

- [ ] **Step 8: Run the full shell test suite and type check**

Run: `cd shell && npx tsc --noEmit && npx vitest run`
Expected: PASS — no regression anywhere.

- [ ] **Step 9: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx \
  shell/src/shell/routes.tsx shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx
git commit -m "feat(shell): wire pipeline creation flow, routing, and etlEnabled gating"
```

---

## Task 12: E2E spec — build, save, run a pipeline visually

**Files:**
- Create: `shell/e2e/pipeline-builder.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`e2e/mocks.ts`, existing) plus a local
  `mockPipelineFlow(page)` helper, following the exact layering pattern of
  `e2e/ingestion.spec.ts`'s `mockIngestionFlow`.
- Produces: nothing consumed elsewhere — the terminal deliverable of SP-15b.

- [ ] **Step 1: Write the spec**

Create `shell/e2e/pipeline-builder.spec.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect, type Page } from "@playwright/test";
import { mockCore } from "./mocks";

const OPS_CATALOG = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

async function mockPipelineFlow(page: Page) {
  await page.route("https://core.test/instance", async (route) => {
    await route.fulfill({ json: { readOnly: false, etlEnabled: true } });
  });
  await page.route("https://core.test/pipelines/ops", async (route) => {
    await route.fulfill({ json: OPS_CATALOG });
  });
  await page.route("https://core.test/collections*", async (route) => {
    await route.fulfill({
      json: { collections: [
        { id: "villes", title: "Villes", description: "", tableName: "villes", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 10, owner: "alice" },
        { id: "villes_propres", title: "Villes propres", description: "", tableName: "villes_propres", isPublic: true, editable: true, geometryType: null, srid: null, pkColumn: "id", canWrite: true, featureCount: 0, owner: "alice" },
      ] },
    });
  });
  await page.route("https://core.test/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    const body = await route.request().postDataJSON();
    if (body?.config?.kind !== "pipeline") return route.fallback();
    await route.fulfill({ status: 201, json: { id: "cfg-pipe1", kind: "pipeline", itemId: "pipe-1" } });
  });
  let runPolls = 0;
  await page.route("https://core.test/pipelines/pipe-1/run", async (route) => {
    await route.fulfill({ status: 202, json: { runId: "run-1" } });
  });
  await page.route("https://core.test/pipelines/pipe-1/runs", async (route) => {
    runPolls += 1;
    const status = runPolls < 2 ? "running" : "succeeded";
    await route.fulfill({
      json: [{ id: "run-1", status, startedAt: "2026-08-06T10:00:00Z", finishedAt: status === "succeeded" ? "2026-08-06T10:00:02Z" : null, error: null, nodeStats: {} }],
    });
  });
}

test("un utilisateur non-technicien construit, enregistre puis exécute un pipeline visuellement", async ({ page }) => {
  await mockCore(page);
  await mockPipelineFlow(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Type").selectOption("pipeline");
  await page.getByLabel("Titre").fill("Nettoyer villes");
  await page.getByRole("button", { name: "Créer" }).click();

  await expect(page).toHaveURL(/\/pipelines\/new$/);

  // Glisser un reader sur le canvas.
  const reader = page.getByText("reader.collection");
  const canvas = page.locator(".react-flow__pane");
  await reader.dragTo(canvas, { targetPosition: { x: 100, y: 100 } });

  // Glisser un writer sur le canvas.
  const writer = page.getByText("writer.collection");
  await writer.dragTo(canvas, { targetPosition: { x: 400, y: 100 } });

  // Relier reader -> writer (poignée droite du premier nœud vers la poignée
  // gauche du second — sélecteurs React Flow standard).
  const sourceHandle = page.locator(".react-flow__node").first().locator(".react-flow__handle-right");
  const targetHandle = page.locator(".react-flow__node").last().locator(".react-flow__handle-left");
  await sourceHandle.dragTo(targetHandle);

  // Renseigner les paramètres des deux nœuds.
  await page.locator(".react-flow__node").first().click();
  await page.getByLabel("collectionId").selectOption("villes");
  await page.locator(".react-flow__node").last().click();
  await page.getByLabel("collectionId").selectOption("villes_propres");

  await expect(page.getByRole("button", { name: "Enregistrer" })).toBeEnabled();
  await page.getByRole("button", { name: "Enregistrer" }).click();

  await expect(page).toHaveURL(/\/pipelines\/pipe-1\/edit$/);

  await page.getByRole("button", { name: "Exécuter" }).click();
  await expect(page.getByText("succeeded")).toBeVisible({ timeout: 10_000 });
});
```

- [ ] **Step 2: Run the spec**

Run: `cd shell && npx playwright test e2e/pipeline-builder.spec.ts`
Expected: PASS.

This is the first drag interaction in this E2E suite (no existing
`dragTo`/manual-DnD precedent to match — verified by grepping `e2e/*.spec.ts`
during planning). Playwright's `locator.dragTo()` (used above) drives both
kinds of drag this spec needs: the palette items are native
`draggable`/`dataTransfer` elements (Playwright synthesizes the
`DataTransfer` object and fires real `dragstart`/`dragover`/`drop`), and
React Flow's handles are plain pointer-driven elements (Playwright's
`dragTo` falls back to a hover → `mouse.down()` → move → `mouse.up()`
sequence for those) — both are supported without extra setup on Playwright
1.47. If a run proves flaky, increase the intermediate step count with
`{ sourcePosition, targetPosition, force: true }` options on `dragTo` before
resorting to manual `dispatchEvent` synthesis.

- [ ] **Step 3: Run the full E2E suite to confirm no regression**

Run: `cd shell && npm run e2e`
Expected: PASS — all 44 specs (43 pre-existing + this one) green.

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/pipeline-builder.spec.ts
git commit -m "test(e2e): add pipeline-builder spec (build, save, run visually)"
```

---

## Final check

- [ ] Run the complete verification sweep before declaring the branch done:

```bash
cd core && uv run pytest -v
cd ../shell && npx tsc --noEmit && npx vitest run && npm run e2e
```

Expected: all green — core (SP-15a's ~957 passed + this plan's 2 new),
shell Vitest (pre-existing + every test added in Tasks 2-11), Playwright
(43 pre-existing specs + `pipeline-builder.spec.ts`).
