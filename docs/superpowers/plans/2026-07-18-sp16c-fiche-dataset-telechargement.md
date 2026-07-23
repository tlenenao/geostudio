# SP-16c — fiche dataset + téléchargement + template galerie : plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship a `DatasetCard` widget + public `/public/datasets/:collectionId` page so an anonymous visitor can view a public collection's metadata/preview and download it (GeoJSON always, CSV under 10 000 rows), plus a "Portail de données" gallery template that pre-wires Hero+Gallery+DatasetCard. This closes SP-16 (jalon M13).

**Architecture:** Shell-only (no core changes — every endpoint used is already anonymous-readable for public collections, verified against `core/app/collections/routes.py` and `core/app/features/routes.py`). One new `ItemClient` method (`getCollection`), one framework-agnostic download util (`src/lib/datasetDownload.ts`), one shared download-buttons component reused by both the widget and the page, and the page's live preview is a `previewConfig` synthesized in memory and rendered by the existing single `AppRenderer(config, "runtime")` — no new rendering engine.

**Tech Stack:** React + TypeScript, `@tanstack/react-query`, Vitest, Playwright. No new dependencies.

## Global Constraints

- **No core (Python) changes at all.** Every read used (`GET /collections/{id}`, `GET /collections/{id}/schema`, `GET /collections/{id}/items`) is already anonymous-readable for a public collection via `get_current_user_optional` + `get_readable_collection` (404 before 403, non-leaking). Verified in `core/app/collections/routes.py:133-151,238-264,267-280` and `core/app/features/routes.py:124-151`.
- **`ItemClient` is the sas** (CLAUDE.md rule #1): no widget/page may call `fetch`/`coreUrl` directly. All network access goes through `ItemClient` methods (`getCollection`, `getCollectionSchema`, `queryDataSource`, `featuresUrl` — all pre-existing except `getCollection`).
- **OGC API Features server cap: `limit` is clamped to `MAX_LIMIT=1000`** (`core/app/features/routes.py:41,135`). This means: (a) the "always available" direct GeoJSON download link only returns the first 1000 features for collections larger than that — an accepted v1 limitation, not a bug, documented inline and in this plan's risk notes; (b) CSV export must paginate in pages of ≤1000 via `offset`/`limit`, never assume a single request returns everything.
- **CSV cap: 10 000 rows** (`CSV_ROW_CAP`). Above it, the CSV button is disabled with the exact message: `Jeu de données trop volumineux pour l'export CSV navigateur — export serveur à venir (SP-15).` GeoJSON stays available regardless.
- **CSV columns:** `[schema.pk, ...schema.fields.map(f => f.name), "geometry"]` — `schema.fields` already excludes pk/tenant_id/geometry columns (`core/app/collections/schema_json.py:8-11`), so no manual exclusion needed. Row values: pk from `record.id`, geometry as `JSON.stringify(record.geometry)`, everything else from `record.properties`.
- **CSV escaping:** RFC4180-style — a cell containing `"`, `,`, `\r` or `\n` is wrapped in double quotes with internal quotes doubled. Rows joined with `\r\n`.
- **Cross-origin `download` attribute — E2E-only wrinkle, not a production concern.** In this repo's E2E harness, the shell runs at `http://localhost:4173` while `VITE_CORE_URL=https://core.test` (`.env.e2e`) is a *different* origin, purely intercepted via Playwright's `page.route()`. Per the HTML spec, an `<a download href="...">` only forces a download for a same-origin URL, or a cross-origin one whose response carries `Content-Disposition: attachment` — otherwise the browser just navigates. In real deployments this never bites: `core` and `shell` share one `Host(${DOMAIN})` behind Traefik, `core` only distinguished by a `PathPrefix(/api)` (SP-9 "sécurité minimale"), i.e. same origin. Task 7 adds a `Content-Disposition` header to the mocked features response so the E2E download assertion is real (not a false pass from a same-origin coincidence), without touching the JSON body other pre-existing specs (`actions.spec.ts`, `data-widget.spec.ts`) already rely on.
- **jsdom in this repo's Vitest env does not implement `URL.createObjectURL`/`revokeObjectURL`, and clicking a real `<a>` inside jsdom triggers an unhandled "Not implemented: navigation" console error.** Any test that exercises the DOM-download side effect must (a) define `URL.createObjectURL`/`revokeObjectURL` via `Object.defineProperty` before use, and (b) `vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {})` to suppress real navigation. Verified empirically (jsdom 25.0.1) while writing this plan — see Task 1.
- **No new abstractions beyond what's specified**: reuse `DataSourceSelect`, `CollectionAdmin`, `CollectionSchema`, `DataRecord`, `queryDataSource`, `featuresUrl` as they already exist. Do not invent a second HTTP client or a second widget-context convention.
- Docs/UI copy in French; code/identifiers in English. Conventional commits (`feat(shell): …`).

---

## Task 1: `datasetDownload.ts` — framework-agnostic download util

**Files:**
- Create: `shell/src/lib/datasetDownload.ts`
- Test: `shell/src/lib/datasetDownload.test.ts`

**Interfaces:**
- Consumes: `CollectionSchema`, `DataRecord`, `DataSource`, `ItemClient` from `shell/src/api/types.ts` (all pre-existing).
- Produces (used by Tasks 3, 4, 5):
  - `csvAvailable(featureCount: number | null): boolean`
  - `geojsonDownloadUrl(client: Pick<ItemClient, "featuresUrl">, collectionId: string): string`
  - `fetchRecordsForCsv(queryPage: (offset: number, limit: number) => Promise<DataRecord[]>, totalCount: number): Promise<DataRecord[]>`
  - `recordsToCsv(schema: CollectionSchema, records: DataRecord[]): string`
  - `triggerCsvDownload(filename: string, csv: string): void`
  - `downloadCsv(opts: { client: Pick<ItemClient, "queryDataSource">; collectionId: string; schema: CollectionSchema; featureCount: number }): Promise<void>`

- [ ] **Step 1: Write the failing test file**

```typescript
// shell/src/lib/datasetDownload.test.ts
// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { CollectionSchema, DataRecord, ItemClient } from "../api/types";
import {
  csvAvailable,
  downloadCsv,
  fetchRecordsForCsv,
  geojsonDownloadUrl,
  recordsToCsv,
  triggerCsvDownload,
} from "./datasetDownload";

test.each([
  [10000, true],
  [10001, false],
  [0, true],
  [null, false],
])("csvAvailable(%s) = %s", (count, expected) => {
  expect(csvAvailable(count)).toBe(expected);
});

test("geojsonDownloadUrl delegates to client.featuresUrl with a synthetic features source capped at the server's max page size", () => {
  const client = { featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000") };
  const url = geojsonDownloadUrl(client, "parcs");
  expect(client.featuresUrl).toHaveBeenCalledWith({
    id: expect.any(String), type: "features", service: "core", layer: "parcs", query: { limit: 1000 },
  });
  expect(url).toBe("https://core.test/collections/parcs/items?limit=1000");
});

test("fetchRecordsForCsv stops after a single page when the server returns fewer rows than requested", async () => {
  const queryPage = vi.fn<(offset: number, limit: number) => Promise<DataRecord[]>>()
    .mockResolvedValueOnce([{ id: 1, properties: {}, geometry: null }]);
  const records = await fetchRecordsForCsv(queryPage, 10000);
  expect(records).toHaveLength(1);
  expect(queryPage).toHaveBeenCalledTimes(1);
  expect(queryPage).toHaveBeenCalledWith(0, 1000);
});

test("fetchRecordsForCsv paginates across multiple full pages until totalCount is reached", async () => {
  const page1: DataRecord[] = Array.from({ length: 1000 }, (_, i) => ({ id: i, properties: {}, geometry: null }));
  const page2: DataRecord[] = [{ id: 1000, properties: {}, geometry: null }];
  const queryPage = vi.fn<(offset: number, limit: number) => Promise<DataRecord[]>>()
    .mockResolvedValueOnce(page1)
    .mockResolvedValueOnce(page2);
  const records = await fetchRecordsForCsv(queryPage, 1001);
  expect(records).toHaveLength(1001);
  expect(queryPage).toHaveBeenNthCalledWith(1, 0, 1000);
  expect(queryPage).toHaveBeenNthCalledWith(2, 1000, 1);
});

test("fetchRecordsForCsv never fetches beyond the 10000-row CSV cap even when totalCount is larger", async () => {
  const bigPage: DataRecord[] = Array.from({ length: 1000 }, (_, i) => ({ id: i, properties: {}, geometry: null }));
  const queryPage = vi.fn<(offset: number, limit: number) => Promise<DataRecord[]>>().mockResolvedValue(bigPage);
  const records = await fetchRecordsForCsv(queryPage, 25000);
  expect(records).toHaveLength(10000);
  expect(queryPage).toHaveBeenCalledTimes(10);
  expect(queryPage).toHaveBeenLastCalledWith(9000, 1000);
});

const schema: CollectionSchema = {
  collection: "parcs", pk: "id", geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

test("recordsToCsv emits pk + schema fields + geometry columns, escaping commas/quotes/newlines", () => {
  const records: DataRecord[] = [
    { id: 1, properties: { nom: 'Parc, du "Test"' }, geometry: null },
    { id: 2, properties: { nom: "Bois" }, geometry: { type: "Point", coordinates: [1, 2] } },
  ];
  const csv = recordsToCsv(schema, records);
  expect(csv).toBe(
    'id,nom,geometry\r\n' +
    '1,"Parc, du ""Test""",\r\n' +
    '2,Bois,"{""type"":""Point"",""coordinates"":[1,2]}"',
  );
});

test("recordsToCsv renders an empty geometry cell when the record has no geometry", () => {
  const csv = recordsToCsv(schema, [{ id: 1, properties: { nom: "X" }, geometry: null }]);
  expect(csv).toBe("id,nom,geometry\r\n1,X,");
});

// jsdom (25.0.1) does not implement URL.createObjectURL/revokeObjectURL, and
// clicking a real <a> triggers jsdom's "Not implemented: navigation" — both
// must be stubbed before exercising the DOM-download side effect.
beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:mock"), writable: true, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true, configurable: true });
});
afterEach(() => {
  vi.restoreAllMocks();
});

test("triggerCsvDownload creates an object URL, clicks a download anchor, then revokes it", () => {
  const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  triggerCsvDownload("parcs.csv", "id,nom\r\n1,X");
  expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
  expect(clickSpy).toHaveBeenCalledTimes(1);
  expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:mock");
});

test("downloadCsv fetches bounded records via the client, builds the CSV, and triggers the download", async () => {
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
  const client: Pick<ItemClient, "queryDataSource"> = {
    queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "Parc du Test" }, geometry: null }]),
  };
  await downloadCsv({ client, collectionId: "parcs", schema, featureCount: 1 });
  expect(client.queryDataSource).toHaveBeenCalledWith({
    id: expect.any(String), type: "features", service: "core", layer: "parcs", query: { limit: 1, offset: 0 },
  });
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/lib/datasetDownload.test.ts`
Expected: FAIL — `Cannot find module './datasetDownload'`.

- [ ] **Step 3: Write the implementation**

```typescript
// shell/src/lib/datasetDownload.ts
// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema, DataRecord, DataSource, ItemClient } from "../api/types";

const PAGE_SIZE = 1000;
const CSV_ROW_CAP = 10000;

export function csvAvailable(featureCount: number | null): boolean {
  return featureCount !== null && featureCount <= CSV_ROW_CAP;
}

// OGC API Features caps `limit` server-side at 1000 (core/app/features/routes.py
// MAX_LIMIT, verified while writing this plan) — a direct browser download of a
// collection with more features than that only returns the first page. Accepted
// v1 limitation: full exports beyond 1000 features wait on SP-15's server-side
// export. GeoJSON stays "always available" (unlike CSV, never disabled).
export function geojsonDownloadUrl(client: Pick<ItemClient, "featuresUrl">, collectionId: string): string {
  const source: DataSource = {
    id: `dataset-geojson-${collectionId}`, type: "features", service: "core",
    layer: collectionId, query: { limit: PAGE_SIZE },
  };
  return client.featuresUrl(source);
}

export async function fetchRecordsForCsv(
  queryPage: (offset: number, limit: number) => Promise<DataRecord[]>,
  totalCount: number,
): Promise<DataRecord[]> {
  const cap = Math.min(totalCount, CSV_ROW_CAP);
  const out: DataRecord[] = [];
  let offset = 0;
  while (offset < cap) {
    const limit = Math.min(PAGE_SIZE, cap - offset);
    const page = await queryPage(offset, limit);
    out.push(...page);
    offset += page.length;
    if (page.length < limit) break; // fewer than requested: no more data upstream
  }
  return out;
}

function csvEscape(value: string): string {
  return /[",\r\n]/.test(value) ? `"${value.replace(/"/g, '""')}"` : value;
}

export function recordsToCsv(schema: CollectionSchema, records: DataRecord[]): string {
  const columns = [schema.pk, ...schema.fields.map((f) => f.name), "geometry"];
  const lines = [columns.map(csvEscape).join(",")];
  for (const r of records) {
    const cells = columns.map((col) => {
      if (col === schema.pk) return csvEscape(String(r.id));
      if (col === "geometry") return csvEscape(r.geometry ? JSON.stringify(r.geometry) : "");
      const v = r.properties[col];
      return csvEscape(v === null || v === undefined ? "" : String(v));
    });
    lines.push(cells.join(","));
  }
  return lines.join("\r\n");
}

export function triggerCsvDownload(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

export async function downloadCsv(opts: {
  client: Pick<ItemClient, "queryDataSource">;
  collectionId: string;
  schema: CollectionSchema;
  featureCount: number;
}): Promise<void> {
  const queryPage = (offset: number, limit: number) =>
    opts.client.queryDataSource({
      id: `dataset-csv-${opts.collectionId}`, type: "features", service: "core",
      layer: opts.collectionId, query: { limit, offset },
    });
  const records = await fetchRecordsForCsv(queryPage, opts.featureCount);
  const csv = recordsToCsv(opts.schema, records);
  triggerCsvDownload(`${opts.collectionId}.csv`, csv);
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/lib/datasetDownload.test.ts`
Expected: PASS (all cases).

- [ ] **Step 5: Commit**

```bash
git add shell/src/lib/datasetDownload.ts shell/src/lib/datasetDownload.test.ts
git commit -m "feat(shell): add datasetDownload util (GeoJSON link + bounded client-side CSV export)"
```

---

## Task 2: `ItemClient.getCollection` — anonymous single-collection metadata read

**Files:**
- Modify: `shell/src/api/types.ts` (add one line to the `ItemClient` interface)
- Modify: `shell/src/api/itemClient.ts` (add one method)
- Modify: `shell/src/api/itemClient.test.ts` (add tests, appended near `getCollectionPermission`)

**Interfaces:**
- Produces (used by Tasks 4, 5): `getCollection(collectionId: string): Promise<CollectionAdmin>` — reuses the existing `CollectionAdmin` type (`id, title, description, tableName, isPublic, editable, geometryType, srid, pkColumn, canWrite, featureCount, owner`), which already matches `GET /collections/{id}`'s JSON shape exactly (verified against `core/app/collections/routes.py:119-125,238-264`).

- [ ] **Step 1: Write the failing test**

Append to `shell/src/api/itemClient.test.ts` (near the existing `getCollectionPermission` tests):

```typescript
test("getCollection returns the full collection metadata for a single id", async () => {
  server.use(
    http.get("https://core.test/collections/parcs", () =>
      HttpResponse.json({
        id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
        isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
        canWrite: false, featureCount: 2, owner: null,
      }),
    ),
  );
  const col = await makeClient(undefined).getCollection("parcs");
  expect(col).toEqual({
    id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
    isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
    canWrite: false, featureCount: 2, owner: null,
  });
});

test("getCollection propagates a 404 for a non-public or unknown collection", async () => {
  server.use(
    http.get("https://core.test/collections/private-x", () =>
      HttpResponse.json({ detail: "collection not found" }, { status: 404 }),
    ),
  );
  await expect(makeClient(undefined).getCollection("private-x")).rejects.toThrow();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts -t getCollection`
Expected: FAIL — `client.getCollection is not a function`.

- [ ] **Step 3: Add the method to the `ItemClient` interface**

In `shell/src/api/types.ts`, right after the existing line:

```typescript
  getCollectionSchema(collectionId: string): Promise<CollectionSchema>;
```

add:

```typescript
  getCollection(collectionId: string): Promise<CollectionAdmin>;
```

- [ ] **Step 4: Implement it in `shell/src/api/itemClient.ts`**

Right after the existing `getCollectionSchema` method (around line 528-530):

```typescript
    async getCollectionSchema(collectionId: string): Promise<CollectionSchema> {
      return request<CollectionSchema>("GET", `/collections/${collectionId}/schema`);
    },

    async getCollection(collectionId: string): Promise<CollectionAdmin> {
      return request<CollectionAdmin>("GET", `/collections/${collectionId}`);
    },
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (entire file, no regression on the other ~90 tests).

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add ItemClient.getCollection (anonymous single-collection metadata read)"
```

---

## Task 3: `DatasetDownloadButtons` — shared download UI

**Files:**
- Create: `shell/src/builder/DatasetDownloadButtons.tsx`
- Test: `shell/src/builder/DatasetDownloadButtons.test.tsx`

**Interfaces:**
- Consumes: `csvAvailable`, `downloadCsv`, `geojsonDownloadUrl` from `../lib/datasetDownload` (Task 1); `useItemClient` from `../api/ItemClientProvider`; `ItemClient.getCollectionSchema` (pre-existing).
- Produces (used by Tasks 4, 5): `DatasetDownloadButtons({ collectionId, featureCount }: { collectionId: string; featureCount: number | null })` — a React component rendering a GeoJSON download link (always) and a CSV download button (disabled + explanatory message above the 10 000-row cap).

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/builder/DatasetDownloadButtons.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../api/types";
import { DatasetDownloadButtons } from "./DatasetDownloadButtons";

const schema: CollectionSchema = {
  collection: "parcs", pk: "id", geometry: null,
  fields: [{ name: "nom", type: "string", required: true }],
};

function renderButtons(featureCount: number | null, clientOverrides: Partial<ItemClient> = {}) {
  const client = {
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    queryDataSource: vi.fn().mockResolvedValue([]),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DatasetDownloadButtons collectionId="parcs" featureCount={featureCount} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

beforeEach(() => {
  Object.defineProperty(URL, "createObjectURL", { value: vi.fn(() => "blob:mock"), writable: true, configurable: true });
  Object.defineProperty(URL, "revokeObjectURL", { value: vi.fn(), writable: true, configurable: true });
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => vi.restoreAllMocks());

test("always renders a GeoJSON download link built from the client", () => {
  renderButtons(2);
  const link = screen.getByRole("link", { name: "Télécharger GeoJSON" });
  expect(link).toHaveAttribute("href", "https://core.test/collections/parcs/items?limit=1000");
  expect(link).toHaveAttribute("download", "parcs.geojson");
});

test("enables the CSV button once the schema loads, under the 10000-row cap", async () => {
  renderButtons(2);
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  expect(button).toBeEnabled();
  expect(screen.queryByText(/trop volumineux/)).not.toBeInTheDocument();
});

test("disables the CSV button above the 10000-row cap and shows the explanatory message", async () => {
  renderButtons(10001);
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  expect(button).toBeDisabled();
  expect(screen.getByText(/trop volumineux pour l'export CSV navigateur — export serveur à venir \(SP-15\)/)).toBeInTheDocument();
});

test("clicking the CSV button fetches records via the client and triggers a download", async () => {
  const client = renderButtons(1, { queryDataSource: vi.fn().mockResolvedValue([{ id: 1, properties: { nom: "X" }, geometry: null }]) });
  const button = await screen.findByRole("button", { name: "Télécharger CSV" });
  await userEvent.click(button);
  await vi.waitFor(() => expect(client.queryDataSource).toHaveBeenCalled());
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/DatasetDownloadButtons.test.tsx`
Expected: FAIL — `Cannot find module './DatasetDownloadButtons'`.

- [ ] **Step 3: Write the implementation**

```tsx
// shell/src/builder/DatasetDownloadButtons.tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { csvAvailable, downloadCsv, geojsonDownloadUrl } from "../lib/datasetDownload";

// Plain slate styling (not --gs-* theme vars): this component is reused both
// inside a themed AppRenderer (DatasetCard widget) and outside any theme root
// (DatasetPage's chrome) — see SP-16c plan Task 5 notes.
export function DatasetDownloadButtons({
  collectionId,
  featureCount,
}: {
  collectionId: string;
  featureCount: number | null;
}) {
  const client = useItemClient();
  const schemaQuery = useQuery({
    queryKey: ["dataset-schema", collectionId],
    queryFn: () => client.getCollectionSchema(collectionId),
  });
  const available = csvAvailable(featureCount);

  return (
    <div className="flex flex-wrap items-center gap-2">
      <a
        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 no-underline hover:bg-slate-100"
        href={geojsonDownloadUrl(client, collectionId)}
        download={`${collectionId}.geojson`}
      >
        Télécharger GeoJSON
      </a>
      <button
        type="button"
        className="rounded-md border border-slate-300 px-3 py-1.5 text-xs font-medium text-slate-700 hover:bg-slate-100 disabled:cursor-not-allowed disabled:opacity-50"
        disabled={!available || !schemaQuery.data}
        onClick={() => {
          if (!schemaQuery.data || featureCount === null) return;
          void downloadCsv({ client, collectionId, schema: schemaQuery.data, featureCount });
        }}
      >
        Télécharger CSV
      </button>
      {!available && (
        <p className="w-full text-[10px] text-slate-500">
          Jeu de données trop volumineux pour l'export CSV navigateur — export serveur à venir (SP-15).
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/DatasetDownloadButtons.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/DatasetDownloadButtons.tsx shell/src/builder/DatasetDownloadButtons.test.tsx
git commit -m "feat(shell): add DatasetDownloadButtons (GeoJSON link + capped CSV export button)"
```

---

## Task 4: `DatasetCard` widget

**Files:**
- Create: `shell/src/builder/widgets/datasetCard.tsx`
- Test: `shell/src/builder/widgets/datasetCard.test.tsx`
- Modify: `shell/src/builder/widgets/index.tsx` (register the widget)

**Interfaces:**
- Consumes: `registerWidget`, `DataSourceSelect`, `useItemClient`, `ItemClient.getCollection` (Task 2), `DatasetDownloadButtons` (Task 3).
- Produces: widget type `"datasetCard"` (label "Fiche jeu de données"), `defaultProps: { dataSourceId: "", showDownload: true, title: "" }`. Resolves its bound collection id from `ctx.data?.layer` (the `DataSourceState.layer` field already populated by `DataContext.tsx` for every configured data source — exactly how the `map`/`table` widgets resolve their own bound collection), **not** a raw `collectionId` prop — this keeps it wired through the existing `DataSourceSelect`/`DataSourcePanel` convention used by every other data-bound widget.

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/builder/widgets/datasetCard.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionAdmin, ItemClient } from "../../api/types";

beforeEach(() => { _resetRegistry(); registerBuiltinWidgets(); });

const collection: CollectionAdmin = {
  id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
  isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
  canWrite: false, featureCount: 2, owner: null,
};

function renderCard(props: Record<string, unknown>, clientOverrides: Partial<ItemClient> = {}, hasSource = true) {
  const client = {
    getCollection: vi.fn().mockResolvedValue(collection),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    ...clientOverrides,
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const DatasetCard = getWidget("datasetCard")!.Component;
  const ctx = { mode: "runtime", data: hasSource ? { loading: false, error: false, records: [], layer: "parcs" } : undefined } as WidgetContext;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <DatasetCard props={props} ctx={ctx} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

test("shows a discreet message when no data source is bound", () => {
  renderCard({}, {}, false);
  expect(screen.getByText(/Aucune source de données/)).toBeInTheDocument();
});

test("renders title, description, feature count, and a link to the dataset page", async () => {
  renderCard({ dataSourceId: "ds1", showDownload: true });
  expect(await screen.findByText("Parcs")).toBeInTheDocument();
  expect(screen.getByText("Parcs publics")).toBeInTheDocument();
  expect(screen.getByText(/2 entités/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Voir le jeu de données" })).toHaveAttribute("href", "/public/datasets/parcs");
});

test("an author-set title overrides the collection's own title", async () => {
  renderCard({ dataSourceId: "ds1", title: "Nos parcs" });
  expect(await screen.findByText("Nos parcs")).toBeInTheDocument();
  expect(screen.queryByText("Parcs")).not.toBeInTheDocument();
});

test("hides the download buttons when showDownload is false", async () => {
  renderCard({ dataSourceId: "ds1", showDownload: false });
  await screen.findByText("Parcs");
  expect(screen.queryByRole("link", { name: "Télécharger GeoJSON" })).not.toBeInTheDocument();
});

test("shows the download buttons by default", async () => {
  renderCard({ dataSourceId: "ds1" });
  expect(await screen.findByRole("link", { name: "Télécharger GeoJSON" })).toBeInTheDocument();
});

test("shows a discreet not-found message for a non-public or unknown collection, without leaking detail", async () => {
  renderCard({ dataSourceId: "ds1" }, { getCollection: vi.fn().mockRejectedValue(new Error("404")) });
  expect(await screen.findByText(/introuvable/i)).toBeInTheDocument();
  expect(screen.queryByText(/parcs/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/widgets/datasetCard.test.tsx`
Expected: FAIL — `getWidget("datasetCard")` is `undefined` (module doesn't exist yet, not registered).

- [ ] **Step 3: Write the widget**

```tsx
// shell/src/builder/widgets/datasetCard.tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { registerWidget } from "../registry";
import { DataSourceSelect } from "../DataSourceSelect";
import { DatasetDownloadButtons } from "../DatasetDownloadButtons";
import { useItemClient } from "../../api/ItemClientProvider";

export function registerDatasetCardWidget(): void {
  registerWidget({
    type: "datasetCard",
    label: "Fiche jeu de données",
    defaultProps: { dataSourceId: "", showDownload: true, title: "" },
    defaultSize: { w: 4, h: 4 },
    PropsPanel: ({ props, onChange, dataSources }) => (
      <div className="flex flex-col gap-2 text-sm">
        <DataSourceSelect
          value={String(props.dataSourceId ?? "")}
          dataSources={dataSources.filter((s) => s.type === "features")}
          onChange={(id) => onChange({ ...props, dataSourceId: id })}
        />
        <label className="flex flex-col gap-1">Titre (optionnel)
          <input aria-label="Titre (optionnel)" className="h-9 rounded-md border border-slate-300 px-2"
            value={String(props.title ?? "")} onChange={(e) => onChange({ ...props, title: e.target.value })} />
        </label>
        <label className="flex items-center gap-2">
          <input type="checkbox" aria-label="Afficher le téléchargement" checked={props.showDownload !== false}
            onChange={(e) => onChange({ ...props, showDownload: e.target.checked })} />
          Afficher le téléchargement
        </label>
      </div>
    ),
    Component: ({ props, ctx }) => {
      const client = useItemClient();
      const collectionId = ctx.data?.layer;
      const query = useQuery({
        queryKey: ["dataset-card", collectionId],
        queryFn: () => client.getCollection(collectionId!),
        enabled: Boolean(collectionId),
      });

      if (!collectionId) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Aucune source de données sélectionnée</p>;
      }
      if (query.isLoading) {
        return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      }
      if (query.isError || !query.data) {
        return <p role="alert" className="text-xs text-[var(--gs-color-muted)]">Jeu de données introuvable</p>;
      }
      const col = query.data;
      const showDownload = props.showDownload !== false;
      return (
        <div className="flex h-full flex-col gap-2 rounded-[var(--gs-radius)] border border-[var(--gs-color-border)] bg-[var(--gs-color-surface)] p-4">
          <h3 className="text-sm font-semibold text-[var(--gs-color-text)]">{String(props.title || col.title)}</h3>
          <p className="text-xs text-[var(--gs-color-muted)]">{col.description}</p>
          <p className="text-xs text-[var(--gs-color-muted)]">{col.featureCount ?? 0} entités</p>
          <a
            className="text-sm font-medium text-[var(--gs-color-primary)] underline"
            href={`/public/datasets/${collectionId}`}
          >
            Voir le jeu de données
          </a>
          {showDownload && <DatasetDownloadButtons collectionId={collectionId} featureCount={col.featureCount} />}
        </div>
      );
    },
  });
}
```

- [ ] **Step 4: Register it in `registerBuiltinWidgets`**

In `shell/src/builder/widgets/index.tsx`, add the import near the other content-widget imports:

```typescript
import { registerGalleryWidget } from "./gallery";
import { registerDatasetCardWidget } from "./datasetCard";
```

and add the call right after `registerGalleryWidget();`:

```typescript
  registerHeroWidget();
  registerRichSectionWidget();
  registerGalleryWidget();
  registerDatasetCardWidget();
}
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/widgets/datasetCard.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run the full shell unit suite to check for regressions**

Run: `cd shell && npm run test`
Expected: PASS, all files (previous count + this task's new tests).

- [ ] **Step 7: Commit**

```bash
git add shell/src/builder/widgets/datasetCard.tsx shell/src/builder/widgets/datasetCard.test.tsx shell/src/builder/widgets/index.tsx
git commit -m "feat(shell): add DatasetCard widget (collection summary + download, bound via DataSourceSelect)"
```

---

## Task 5: `/public/datasets/:collectionId` route + `DatasetPage`

**Files:**
- Create: `shell/src/pages/DatasetPage.tsx`
- Test: `shell/src/pages/DatasetPage.test.tsx`
- Modify: `shell/src/shell/routes.tsx`

**Interfaces:**
- Consumes: `useItemClient`, `ItemClient.getCollection` (Task 2), `DatasetDownloadButtons` (Task 3), `AppRenderer`, `registerBuiltinWidgets` (pre-existing, same pattern as `SitePublicPage`/`PublicItemPage`).
- Produces: `DatasetPage({ collectionId }: { collectionId: string })`, route `/public/datasets/:collectionId`.

- [ ] **Step 1: Write the failing test**

```tsx
// shell/src/pages/DatasetPage.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { DatasetPage } from "./DatasetPage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: false, username: null,
  error: null, getAccessToken: () => undefined, signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

const collection: CollectionAdmin = {
  id: "parcs", title: "Parcs", description: "Parcs publics", tableName: "parcs",
  isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
  canWrite: false, featureCount: 2, owner: null,
};

function renderPage(client: Partial<ItemClient>, collectionId = "parcs") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/public/datasets/${collectionId}`]}>
          <DatasetPage collectionId={collectionId} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("200: renders the collection's chrome, download buttons, and the AppRenderer preview", async () => {
  renderPage({
    getCollection: vi.fn().mockResolvedValue(collection),
    getCollectionSchema: vi.fn().mockResolvedValue({ collection: "parcs", pk: "id", geometry: null, fields: [] }),
    featuresUrl: vi.fn().mockReturnValue("https://core.test/collections/parcs/items?limit=1000"),
    queryDataSource: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByRole("heading", { name: "Parcs" })).toBeInTheDocument();
  expect(screen.getByText("Parcs publics")).toBeInTheDocument();
  expect(screen.getByText(/2 entités/)).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Télécharger GeoJSON" })).toBeInTheDocument();
});

test("404: shows a not-found message without leaking whether the collection exists", async () => {
  renderPage({ getCollection: vi.fn().mockRejectedValue(new Error("404")) }, "private-x");
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/private-x/i);
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/pages/DatasetPage.test.tsx`
Expected: FAIL — `Cannot find module './DatasetPage'`.

- [ ] **Step 3: Write `DatasetPage`**

```tsx
// shell/src/pages/DatasetPage.tsx
// SPDX-License-Identifier: Apache-2.0
import { useQuery } from "@tanstack/react-query";
import { useItemClient } from "../api/ItemClientProvider";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";
import { DatasetDownloadButtons } from "../builder/DatasetDownloadButtons";
import type { AppConfig } from "../api/types";

registerBuiltinWidgets();

// Synthesized in memory, never persisted — the read-only preview reuses the
// single AppRenderer(config, "runtime") runtime (A31), never a bespoke
// map/table pairing.
function previewConfig(collectionId: string): AppConfig {
  const dataSourceId = "dataset-preview";
  return {
    kind: "app",
    theme: {},
    dataSources: [{ id: dataSourceId, type: "features", service: "core", layer: collectionId, query: {} }],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [
        { id: "dataset-preview-map", widget: "map", x: 0, y: 0, w: 6, h: 6, props: { dataSourceId } },
        { id: "dataset-preview-table", widget: "table", x: 6, y: 0, w: 6, h: 6, props: { dataSourceId, columns: [], pageSize: 10 } },
      ],
    },
  };
}

export function DatasetPage({ collectionId }: { collectionId: string }) {
  const client = useItemClient();
  const query = useQuery({
    queryKey: ["public-dataset", collectionId],
    queryFn: () => client.getCollection(collectionId),
    retry: false,
  });

  if (query.isLoading) {
    return <p role="status">Chargement…</p>;
  }
  if (query.isError || !query.data) {
    return (
      <div className="p-8 text-center">
        <p role="alert" className="text-sm text-slate-600">Jeu de données introuvable.</p>
      </div>
    );
  }
  const col = query.data;
  return (
    <div className="flex h-full w-full flex-col gap-4 p-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-bold text-slate-900">{col.title}</h1>
        <p className="text-sm text-slate-600">{col.description}</p>
        <p className="text-xs text-slate-500">{col.featureCount ?? 0} entités</p>
      </header>
      <DatasetDownloadButtons collectionId={collectionId} featureCount={col.featureCount} />
      <div className="h-[480px] w-full">
        <AppRenderer config={previewConfig(collectionId)} mode="runtime" />
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Wire the route**

In `shell/src/shell/routes.tsx`, add the import:

```typescript
import { DatasetPage } from "../pages/DatasetPage";
```

add the route component next to `PublicItemRoute`:

```typescript
function DatasetRoute() {
  const { collectionId } = useParams();
  return <DatasetPage collectionId={collectionId!} />;
}
```

and add the route entry, outside `ProtectedLayout`, next to `/public/items/:pk`:

```tsx
      <Route path="/sites/:slug" element={<SitePublicRoute />} />
      <Route path="/public/items/:pk" element={<PublicItemRoute />} />
      <Route path="/public/datasets/:collectionId" element={<DatasetRoute />} />
    </Routes>
```

- [ ] **Step 5: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/pages/DatasetPage.test.tsx`
Expected: PASS.

- [ ] **Step 6: Run `tsc --noEmit` to catch route-typing drift**

Run: `cd shell && npx tsc --noEmit`
Expected: no errors.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/DatasetPage.tsx shell/src/pages/DatasetPage.test.tsx shell/src/shell/routes.tsx
git commit -m "feat(shell): add /public/datasets/:collectionId route + DatasetPage (metadata + read-only preview + download)"
```

---

## Task 6: Template "Portail de données"

**Files:**
- Modify: `shell/src/builder/templates.ts`
- Modify: `shell/src/builder/templates.test.ts`

**Interfaces:**
- Consumes: widget types `"hero"`, `"gallery"`, `"datasetCard"`, `"map"`, `"table"` (all pre-existing/Task 4); `Template` type (widened).
- Produces: `getTemplate("portail-de-donnees")`, selectable in `NewItemButton` for `kind === "site"` (no changes needed there — it already does `TEMPLATES.filter((t) => t.kind === kind)`, which only needed `Template.kind` to allow `"site"`).

- [ ] **Step 1: Write the failing test**

In `shell/src/builder/templates.test.ts`, change the existing count assertion and add a dedicated test:

```typescript
test("exposes the expected number of templates per kind", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(3);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(1);
  expect(TEMPLATES.filter((t) => t.kind === "site")).toHaveLength(1);
});
```

Append a new test:

```typescript
test("portail-de-donnees template wires Hero, Gallery, DatasetCard, and a Carte/Table demo on the same public collection", () => {
  const tpl = getTemplate("portail-de-donnees")!;
  expect(tpl.kind).toBe("site");
  expect(tpl.dataSources).toHaveLength(1);
  const ds = tpl.dataSources![0];
  expect(ds).toMatchObject({ type: "features", service: "core", layer: "incidents" });
  const widgetTypes = tpl.layout.items.map((i) => i.widget).sort();
  expect(widgetTypes).toEqual(["datasetCard", "gallery", "hero", "map", "table"]);
  for (const item of tpl.layout.items) {
    if (item.widget === "datasetCard" || item.widget === "map" || item.widget === "table") {
      expect(item.props.dataSourceId).toBe(ds.id);
    }
  }
});
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd shell && npx vitest run src/builder/templates.test.ts`
Expected: FAIL — count assertion fails (0 site templates), `getTemplate("portail-de-donnees")` is `undefined`.

- [ ] **Step 3: Widen `Template.kind` and add the template**

In `shell/src/builder/templates.ts`, change:

```typescript
export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
```

to:

```typescript
export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard" | "site";
```

Add, after the story-cartographique block and before `export const TEMPLATES`:

```typescript
const PORTAL_DATA_SOURCE_ID = "tpl-portal-ds";

const PORTAL_DATA_SOURCES: DataSource[] = [
  { id: PORTAL_DATA_SOURCE_ID, type: "features", service: "core", layer: "incidents", query: {} },
];

const PORTAL_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    {
      id: "tpl-portal-hero", widget: "hero", x: 0, y: 0, w: 12, h: 3,
      props: {
        title: "Portail de données", subtitle: "Explorez et téléchargez nos jeux de données ouverts.",
        backgroundImageUrl: "", ctaLabel: "", ctaHref: "", align: "left",
      },
    },
    {
      id: "tpl-portal-gallery", widget: "gallery", x: 0, y: 3, w: 12, h: 4,
      props: { type: "", tag: "", limit: 12, columns: 3 },
    },
    {
      id: "tpl-portal-dataset-card", widget: "datasetCard", x: 0, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID, showDownload: true, title: "" },
    },
    {
      id: "tpl-portal-map", widget: "map", x: 4, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID },
    },
    {
      id: "tpl-portal-table", widget: "table", x: 8, y: 7, w: 4, h: 4,
      props: { dataSourceId: PORTAL_DATA_SOURCE_ID, columns: [], pageSize: 10 },
    },
  ],
};
```

Add the entry to `TEMPLATES`:

```typescript
export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
  {
    id: "application-de-saisie", name: "Application de saisie", kind: "app",
    layout: INCIDENT_APP_LAYOUT, dataSources: INCIDENT_APP_DATA_SOURCES, messages: INCIDENT_APP_MESSAGES,
  },
  {
    id: "story-cartographique", name: "Story cartographique", kind: "app",
    layout: STORY_PAGES[0].layout, pages: STORY_PAGES, navigationMode: "story",
  },
  {
    id: "portail-de-donnees", name: "Portail de données", kind: "site",
    layout: PORTAL_LAYOUT, dataSources: PORTAL_DATA_SOURCES,
  },
];
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd shell && npx vitest run src/builder/templates.test.ts`
Expected: PASS.

- [ ] **Step 5: Run the full shell suite + build**

Run: `cd shell && npm run test && npm run build`
Expected: PASS, no `tsc` errors (the widened `Template.kind` union must still satisfy `NewItemButton.tsx`'s existing `TEMPLATES.filter((t) => t.kind === kind)`, which already compares against the `"app"|"dashboard"|"map"|"site"` union — no code change needed there).

- [ ] **Step 6: Commit**

```bash
git add shell/src/builder/templates.ts shell/src/builder/templates.test.ts
git commit -m "feat(shell): add \"Portail de données\" site template (Hero+Gallery+DatasetCard+Carte/Table demo)"
```

---

## Task 7: E2E spec + mock fixtures

**Files:**
- Modify: `shell/e2e/mocks.ts` (add a public-collection detail + schema fixture for `parcs`)
- Create: `shell/e2e/sites-portal-dataset.spec.ts`

**Interfaces:**
- Consumes: the existing `**/collections/parcs/items*` mock (already present, 2 features: `{id:1,properties:{nom:"Parc du Test"}}`, `{id:2,properties:{nom:"Bois Test"}}`, no geometry) — reused as-is, not duplicated.

- [ ] **Step 1: Add the `Content-Disposition` header to the existing `parcs/items` mock, then add the `parcs` detail + schema mocks**

In `shell/e2e/mocks.ts`, the existing block (around line 272-283) reads:

```typescript
  // Cœur items endpoint for the "parcs" collection — filters by the `nom`
  // query param so setFilter can be observed end-to-end.
  await page.route("**/collections/parcs/items*", async (route) => {
    const url = new URL(route.request().url());
    const nom = url.searchParams.get("nom");
    const all = [
      { id: 1, properties: { nom: "Parc du Test" } },
      { id: 2, properties: { nom: "Bois Test" } },
    ];
    const features = nom ? all.filter((f) => f.properties.nom === nom) : all;
    await route.fulfill({ json: { type: "FeatureCollection", features } });
  });
```

Change the final `route.fulfill` call to add a `Content-Disposition` header (harmless for the JS-`fetch()` consumers — Table/Map preview, CSV export — that already rely on this exact route; needed so a direct `<a download href="https://core.test/...">` click, cross-origin from the E2E app's own `http://localhost:4173`, actually forces a download instead of navigating — see this plan's Global Constraints note):

```typescript
    await route.fulfill({
      headers: { "Content-Disposition": 'attachment; filename="parcs.geojson"' },
      json: { type: "FeatureCollection", features },
    });
```

Then, right after that block:

```typescript
  // Collection detail + schema for "parcs" (SP-16c) — a genuinely public
  // collection (unlike "incidents", kept private above for the incident-form
  // scenario), reusing the existing "**/collections/parcs/items*" fixture.
  await page.route("**/collections/parcs", async (route) => {
    await route.fulfill({
      json: {
        id: "parcs", title: "Parcs", description: "Parcs publics de la ville", tableName: "parcs",
        isPublic: true, editable: false, geometryType: null, srid: null, pkColumn: "id",
        canWrite: false, featureCount: 2,
      },
    });
  });

  await page.route("**/collections/parcs/schema", async (route) => {
    await route.fulfill({
      json: {
        collection: "parcs", pk: "id", geometry: null,
        fields: [{ name: "nom", type: "string", required: true }],
      },
    });
  });
```

- [ ] **Step 2: Write the E2E spec**

```typescript
// shell/e2e/sites-portal-dataset.spec.ts
// SPDX-License-Identifier: Apache-2.0
import { test, expect } from "@playwright/test";
import { mockCore } from "./mocks";

test("créer un site, y ajouter un DatasetCard lié à une collection publique, publier, consulter et télécharger en anonyme", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  // 1. Créer un Site.
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("site");
  await page.getByLabel("Titre").fill("Portail Parcs");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/site-1\/edit$/);

  // 2. Source de données -> collection publique "parcs".
  await page.getByRole("button", { name: "Ajouter une source" }).click();
  await page.getByLabel(/Collection de la source/).fill("parcs");

  // 3. Ajouter la Fiche jeu de données, la lier à la source.
  await page.getByRole("button", { name: "Fiche jeu de données" }).click();
  await page.getByLabel("Source de données").selectOption({ index: 1 });

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // 4. Publier.
  await page.goto("/items/site-1");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 5. Consultation anonyme du site : la fiche affiche titre + nombre d'entités.
  await page.goto("/sites/portail-parcs");
  await expect(page.getByText("Parcs")).toBeVisible();
  await expect(page.getByText(/2 entités/)).toBeVisible();

  // 6. Clic "Voir le jeu de données" -> page dataset publique complète.
  await page.getByRole("link", { name: "Voir le jeu de données" }).click();
  await expect(page).toHaveURL(/\/public\/datasets\/parcs$/);
  await expect(page.getByRole("heading", { name: "Parcs" })).toBeVisible();
  await expect(page.getByText("Parcs publics de la ville")).toBeVisible();
  await expect(page.getByText("Parc du Test")).toBeVisible(); // aperçu Table

  // 7. Téléchargement GeoJSON (lien direct, toujours disponible).
  const [geojsonDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("link", { name: "Télécharger GeoJSON" }).click(),
  ]);
  expect(geojsonDownload.suggestedFilename()).toBe("parcs.geojson");

  // 8. Téléchargement CSV (sous le seuil de 10000 -> bouton actif).
  const [csvDownload] = await Promise.all([
    page.waitForEvent("download"),
    page.getByRole("button", { name: "Télécharger CSV" }).click(),
  ]);
  expect(csvDownload.suggestedFilename()).toBe("parcs.csv");
});

test("une collection non publique via /public/datasets/:id rend « introuvable », sans fuite d'existence", async ({ page }) => {
  await mockCore(page);
  await page.route("**/collections/incidents", async (route) => {
    // "incidents" est privée dans la fixture partagée (isPublic:false) — même
    // route que get_readable_collection retournerait pour un visiteur anonyme:
    // 404, jamais 403.
    await route.fulfill({ status: 404, json: { detail: "collection not found" } });
  });
  await page.goto("/public/datasets/incidents");
  await expect(page.getByRole("alert")).toHaveTextContent(/introuvable/i);
});
```

- [ ] **Step 3: Run the new spec**

Run: `cd shell && npx playwright test sites-portal-dataset.spec.ts`
Expected: PASS (both tests).

- [ ] **Step 4: Run the full E2E suite to confirm no regression**

Run: `cd shell && npm run e2e`
Expected: PASS, all specs (previous 41/41 + this task's new file).

- [ ] **Step 5: Regenerate/verify OpenAPI-derived types are untouched**

This sub-phase adds no core route or field, so no drift is expected. Confirm:

Run: `cd core && uv run python -c "import app.main" && git status --porcelain core/openapi.json shell/src/api/generated/core-schema.d.ts`
Expected: empty output (no uncommitted diff) — if non-empty, investigate before proceeding (would indicate an unexpected drift, not something this plan intends to cause).

- [ ] **Step 6: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/sites-portal-dataset.spec.ts
git commit -m "test(e2e): sites-portal-dataset — DatasetCard/DatasetPage end to end, incl. non-leaking 404"
```

---

## Final verification (whole branch)

- [ ] `cd shell && npm run test` — full unit suite green.
- [ ] `cd shell && npm run build` — `tsc --noEmit` + vite build clean.
- [ ] `cd shell && npm run e2e` — all specs green (41 pre-existing + `sites-portal-dataset.spec.ts`).
- [ ] `cd core && uv run pytest` — unchanged (no core files touched), confirms no accidental core edit.
- [ ] Manually re-read the security note (spec §6): confirm `DatasetCard`/`DatasetPage` never call anything except `getCollection`/`getCollectionSchema`/`queryDataSource`/`featuresUrl` — all of which route through the anonymous-safe `get_readable_collection` 404-before-403 path, with no new core surface introduced.
- [ ] Update `CLAUDE.md` §État with an SP-16c entry once the branch is merged (closes SP-16, jalon M13).
