# Catalog Scope Filter (SP-0b.3-b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a "Portée" filter to the catalog — Tous / Mes éléments / Partagés avec moi / Publics — so a user can narrow the item list by ownership/visibility.

**Architecture:** Front-only. Extend `item-client.listItems` with a `scope` (+ `me`) parameter that maps to GeoNode query filters (`mine` → owner filter; `public` → published filter; `shared` → visible-and-not-owned, filtered in the façade; `all` → no filter). Add a "Portée" `<select>` to `CatalogPage`, wired to `useItems` with `me` from `useMe`. Extend the Playwright E2E.

**Tech Stack:** React 19, TypeScript, @tanstack/react-query, Vitest + Testing Library + MSW, Playwright. (No new dependencies.)

## Global Constraints

- Work under `shell/`; run from `shell/`: `npm test`, `npm run build`, `npm run e2e`.
- All network access via `item-client`; no GeoNode URL/import outside the façade; clean MSW output.
- `ItemScope = "all" | "mine" | "shared" | "public"`.
- Scope→GeoNode mapping (best-effort, isolated in the façade, defined by the mock): `mine` ⇒ `filter{owner.username.in}={me}`; `public` ⇒ `filter{is_published}=true`; `shared` ⇒ no reliable server param — the façade drops items whose `owner === me` from the page (page-local, documented limitation); `all` ⇒ nothing.
- `Item`/`ItemClient`/`ListItemsParams` extend, not break; existing `listItems` calls (no scope) behave exactly as before.

---

### Task 1: `listItems` scope + `me` mapping

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Test: `shell/src/api/itemClient.test.ts` (add cases)

**Interfaces:**
- Produces in `types.ts`: `export type ItemScope = "all" | "mine" | "shared" | "public";` and `ListItemsParams` gains `scope?: ItemScope; me?: string`.
- `itemClient.listItems` maps: `scope === "mine" && me` ⇒ set `filter{owner.username.in}={me}`; `scope === "public"` ⇒ set `filter{is_published}=true`; after fetching, `scope === "shared" && me` ⇒ drop items with `owner === me` and reduce `total` by the number dropped on this page; `scope === "all"`/undefined ⇒ no change.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts`:

```ts
test("listItems scope=mine sends the owner filter", async () => {
  let url = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ scope: "mine", me: "alice" });
  expect(new URL(url).searchParams.get("filter{owner.username.in}")).toBe("alice");
});

test("listItems scope=public sends the published filter", async () => {
  let url = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      url = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  await makeClient().listItems({ scope: "public" });
  expect(new URL(url).searchParams.get("filter{is_published}")).toBe("true");
});

test("listItems scope=shared drops items owned by me", async () => {
  server.use(
    http.get("https://geonode.test/api/v2/resources", () =>
      HttpResponse.json({
        total: 2,
        page: 1,
        page_size: 12,
        resources: [
          { pk: "1", resource_type: "app", title: "Mine", owner: { username: "alice" }, date: "" },
          { pk: "2", resource_type: "app", title: "Theirs", owner: { username: "bob" }, date: "" },
        ],
      }),
    ),
  );
  const page = await makeClient().listItems({ scope: "shared", me: "alice" });
  expect(page.items.map((i) => i.pk)).toEqual(["2"]);
  expect(page.total).toBe(1);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: FAIL — scope not handled (owner/published params absent; shared not filtered).

- [ ] **Step 3: Extend `ListItemsParams` in `shell/src/api/types.ts`**

```ts
export type ItemScope = "all" | "mine" | "shared" | "public";

export type ListItemsParams = {
  q?: string;
  type?: ResourceType;
  page?: number;
  pageSize?: number;
  scope?: ItemScope;
  me?: string;
};
```

(Replace the existing `ListItemsParams` definition; keep the existing fields.)

- [ ] **Step 4: Update `listItems` in `shell/src/api/itemClient.ts`**

Replace the body of `listItems` with:

```ts
    async listItems(params: ListItemsParams = {}): Promise<ItemPage> {
      const q = new URLSearchParams();
      if (params.q) q.set("search", params.q);
      if (params.type) q.set("filter{resource_type.in}", params.type);
      if (params.scope === "mine" && params.me) {
        q.set("filter{owner.username.in}", params.me);
      }
      if (params.scope === "public") {
        q.set("filter{is_published}", "true");
      }
      q.set("page", String(params.page ?? 1));
      q.set("page_size", String(params.pageSize ?? 12));
      const data = await get<{
        total: number;
        page: number;
        page_size: number;
        resources: GeoNodeResource[];
      }>(`/api/v2/resources?${q.toString()}`);
      let items = data.resources.map(toItem);
      let total = data.total;
      if (params.scope === "shared" && params.me) {
        const before = items.length;
        items = items.filter((i) => i.owner !== params.me);
        total = total - (before - items.length);
      }
      return { items, total, page: data.page, pageSize: data.page_size };
    },
```

- [ ] **Step 5: Run to verify they pass**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: PASS (existing + 3 new).

- [ ] **Step 6: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add listItems scope filter (mine/shared/public)"
```

---

### Task 2: "Portée" select in `CatalogPage`

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Test: `shell/src/pages/CatalogPage.test.tsx` (add a case)

**Interfaces:**
- Consumes: `useMe` (`../api/hooks`), `ItemScope` (`../api/types`).
- Produces: `CatalogPage` gains a scope `<select>` (`aria-label="Portée"`, options Tous/Mes éléments/Partagés avec moi/Publics). Local `scope` state (default `"all"`); `me` from `useMe().data?.username`. `useItems` is called with `{ ..., scope, me }`. Changing scope resets `page` to 1.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/pages/CatalogPage.test.tsx`:

```tsx
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";

test("filters the catalog by scope", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://geonode.test/api/v2/resources", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ total: 0, page: 1, page_size: 12, resources: [] });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} />, { wrapper });
  await userEvent.selectOptions(screen.getByLabelText("Portée"), "mine");
  await waitFor(() =>
    expect(new URL(lastUrl).searchParams.get("filter{owner.username.in}")).toBe("alice"),
  );
});
```

(The global MSW `/users/me` handler returns username `alice`, so `useMe` supplies `me="alice"`.)

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/pages/CatalogPage.test.tsx`
Expected: FAIL — no "Portée" control / scope not sent.

- [ ] **Step 3: Update `shell/src/pages/CatalogPage.tsx`**

Add imports:

```tsx
import { useItems, useMe } from "../api/hooks";
import type { ItemScope, ResourceType } from "../api/types";
```

(Replace the existing `useItems` import line and the `ResourceType` type import accordingly.)

Add scope + me state and pass them to `useItems`:

```tsx
  const [scope, setScope] = useState<ItemScope>("all");
  const me = useMe();

  const query = useItems({
    q: q || undefined,
    type: type || undefined,
    page,
    pageSize: PAGE_SIZE,
    scope,
    me: me.data?.username,
  });
```

Add the "Portée" select next to the existing Type select (inside the same filter row):

```tsx
        <label className="flex flex-col gap-1 text-sm">
          Portée
          <select
            aria-label="Portée"
            className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
            value={scope}
            onChange={(e) => {
              setScope(e.target.value as ItemScope);
              setPage(1);
            }}
          >
            <option value="all">Tous</option>
            <option value="mine">Mes éléments</option>
            <option value="shared">Partagés avec moi</option>
            <option value="public">Publics</option>
          </select>
        </label>
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/pages/CatalogPage.test.tsx`
Expected: PASS (existing + new).

- [ ] **Step 5: Run the full suite + build**

Run: `npm test` then `npm run build`.
Expected: all PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx
git commit -m "feat(shell): add Portée scope filter to the catalog"
```

---

### Task 3: E2E scope filter

**Files:**
- Modify: `shell/e2e/mocks.ts`
- Modify: `shell/e2e/catalog.spec.ts`

**Interfaces:**
- Produces: the resources route mock returns the two items for `all`/`public`, but an empty list when the owner filter targets the mock user (`mockuser`, who owns neither Alpha nor Beta); an E2E selects "Mes éléments" and asserts the grid empties.

- [ ] **Step 1: Make the E2E resources mock owner-aware in `shell/e2e/mocks.ts`**

Replace the `**/api/v2/resources*` route with:

```ts
  await page.route("**/api/v2/resources*", async (route) => {
    const url = new URL(route.request().url());
    const owner = url.searchParams.get("filter{owner.username.in}");
    const visible = ALL.filter((r) => !deleted.has(r.pk));
    // Alpha/Beta are owned by "alice"; the mock user is "mockuser".
    const resources = owner ? visible.filter((r) => r.owner.username === owner) : visible;
    await route.fulfill({
      json: { total: resources.length, page: 1, page_size: 12, resources },
    });
  });
```

(Keep the `const deleted = new Set<string>();` and `ALL` array already at the top of `mockGeoNode`.)

- [ ] **Step 2: Add the E2E to `shell/e2e/catalog.spec.ts`**

```ts
test("filters the catalog to my items (empty for the mock user)", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  await page.getByLabel("Portée").selectOption("mine");
  await expect(page.getByText("Aucun élément")).toBeVisible();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});
```

- [ ] **Step 3: Run the E2E**

Run: `npm run e2e`
Expected: all specs PASS. (If chromium is unavailable here, report the unit suite + build pass and the E2E files are in place.)

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/mocks.ts shell/e2e/catalog.spec.ts
git commit -m "test(shell): cover catalog scope filter in E2E"
```

---

## Self-Review

**Spec coverage (against SP-0b.3 §3 scope + §5 Portée + phase 0b.3-b):**
- `ItemScope` + `listItems` scope/`me` mapping → Task 1. ✅
- "Portée" select in `CatalogPage`, `me` from `useMe`, reset page on change → Task 2. ✅
- E2E scope filter → Task 3. ✅

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `ItemScope` defined in Task 1 (`types.ts`), consumed by `listItems` (Task 1) and `CatalogPage` (Task 2). `ListItemsParams` gains `scope`/`me`, used identically by `useItems` (unchanged hook — queryKey already includes params) in Task 2. `me` sourced from `useMe().data?.username` (existing hook). ✅

## Notes

- The "shared" scope filters page-locally (drops items owned by `me`); pagination totals for that scope are approximate — documented in the SP-0b.3 spec's deferred notes. Revisit if GeoNode exposes a "shared with me" query parameter.
- This completes SP-0b.3 (and the SP-0b item-management arc): auth+catalog (0b.1), lifecycle (0b.2), sharing+scope (0b.3). Next arcs: SP-0c (map viewer), SP-0d (canvas + widgets).
