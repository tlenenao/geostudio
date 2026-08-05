## Task 5: Shell — `CatalogPage` reuse (`/bookmarks`) + bookmark-aware open navigation

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx:12,14,50-66` (add `fixedType` prop, hide the selector when set)
- Modify: `shell/src/shell/routes.tsx` (add `BookmarksRoute` + `/bookmarks` route; add a shared async open-navigation helper used by both `CatalogRoute` and `BookmarksRoute`)
- Test: `shell/src/pages/CatalogPage.test.tsx` (append), `shell/src/shell/routes.test.tsx` (append)

**Interfaces:**
- Consumes: `client.getBookmarkConfig(pk)` (Task 4), `encodeAnalyticsContext` (`shell/src/lib/analyticsContextUrl.ts:3-6`), `useItemClient` (`shell/src/api/ItemClientProvider.ts`).
- Produces: `CatalogPage({ onOpenItem, fixedType? }: { onOpenItem: ...; fixedType?: ResourceType })`; route `/bookmarks`. No change to `CatalogPage`'s existing `onOpenItem` contract, so Task 6 and E2E (Task 7) can rely on it unchanged.

- [ ] **Step 1: Write the failing `CatalogPage` test**

Append to `shell/src/pages/CatalogPage.test.tsx`:

```typescript
test("fixedType locks the type filter and hides the selector", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 12 });
    }),
  );
  render(<CatalogPage onOpenItem={() => {}} fixedType="bookmark" />, { wrapper });
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark"));
  expect(screen.queryByLabelText("Type")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: FAIL — `CatalogPage` has no `fixedType` prop; `type` stays `""`/unlocked and the `Type` selector is still rendered.

- [ ] **Step 3: Implement `fixedType` in `CatalogPage.tsx`**

Change the signature (line 12):

```typescript
export function CatalogPage({
  onOpenItem, fixedType,
}: {
  onOpenItem: (pk: string, type: ResourceType) => void;
  fixedType?: ResourceType;
}) {
```

Change the `type` state initializer (line 14):

```typescript
  const [type, setType] = useState<ResourceType | "">(fixedType ?? "");
```

Wrap the `Type` selector label (lines 50-66) in a guard:

```typescript
        {!fixedType && (
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={type}
              onChange={(e) => {
                setType(e.target.value as ResourceType | "");
                setPage(1);
              }}
            >
              <option value="">Tous</option>
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
              <option value="map">Map</option>
            </select>
          </label>
        )}
```

- [ ] **Step 4: Run test to verify it passes**

Run: `cd shell && npx vitest run src/pages/CatalogPage.test.tsx`
Expected: PASS (4 tests total)

- [ ] **Step 5: Write the failing routes test**

Append to `shell/src/shell/routes.test.tsx`. First add a mock for the bookmark-config fetch route, mirroring the file's existing `http.get("https://core.test/items", ...)` mock style:

```typescript
test("renders the bookmarks catalog at /bookmarks, filtered to type=bookmark", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({
        items: [
          { pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      });
    }),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await screen.findByText("Ma vue");
  expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark");
});

test("opening a bookmark navigates to its app+page+ctx URL, not an editor", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          { pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
        ],
        total: 1, page: 1, pageSize: 12,
      }),
    ),
    http.get("https://core.test/configs/by-item/bm-1", () =>
      HttpResponse.json({
        id: "cfg-bm-1", itemId: "bm-1", kind: "bookmark",
        config: {
          version: 1, kind: "bookmark",
          bookmark: { appId: "42", pageId: "page-1", timeRange: null, extent: null, crossFilter: {} },
        },
      }),
    ),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText(/^app-runtime-42-page-1$/)).toBeInTheDocument();
});
```

- [ ] **Step 6: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: FAIL — no `/bookmarks` route exists (blank render / no "Ma vue" text found).

- [ ] **Step 7: Implement the route + bookmark-aware open navigation**

In `shell/src/shell/routes.tsx`, add the import:

```typescript
import { useItemClient } from "../api/ItemClientProvider";
import { encodeAnalyticsContext } from "../lib/analyticsContextUrl";
```

Add a shared navigation helper, right after the imports (before `CatalogRoute`):

```typescript
// Shared by CatalogRoute (general catalog) and BookmarksRoute ("Mes vues"):
// a bookmark has no editor (SP-14m — no edit flow for this kind), so opening
// one fetches its saved app/page/context and replays it via ?ctx=, instead
// of navigating to an editor route like every other kind below.
function useOpenItem() {
  const navigate = useNavigate();
  const client = useItemClient();
  return async (pk: string, type: ResourceType) => {
    if (type === "bookmark") {
      const bookmark = await client.getBookmarkConfig(pk);
      const ctx = encodeAnalyticsContext({
        timeRange: bookmark.timeRange, extent: bookmark.extent, crossFilter: bookmark.crossFilter,
      });
      navigate(`/apps/${encodeURIComponent(bookmark.appId)}/${encodeURIComponent(bookmark.pageId)}?ctx=${ctx}`);
      return;
    }
    navigate(type === "map" ? `/maps/${pk}` : type === "dataset" ? `/datasets/${pk}/edit` : `/apps/${pk}/edit`);
  };
}
```

Add the `ResourceType` import to the existing `import type` (or add a new `import type { ResourceType } from "../api/types";` line).

Replace `CatalogRoute` to use the shared helper:

```typescript
function CatalogRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} />;
}
```

Add `BookmarksRoute` right after it:

```typescript
function BookmarksRoute() {
  const onOpenItem = useOpenItem();
  return <CatalogPage onOpenItem={onOpenItem} fixedType="bookmark" />;
}
```

Register the route in `AppRoutes` (inside `<Route element={<ProtectedLayout />}>`, after `/items/:pk`):

```typescript
        <Route path="/bookmarks" element={<BookmarksRoute />} />
```

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: PASS (all routes.test.tsx tests, including the two new ones — the pre-existing `"navigates from catalog to app builder on open (app item)"` test must still pass unchanged, since `useOpenItem`'s non-bookmark branch is byte-identical to the old inline ternary)

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green, no regressions.

- [ ] **Step 10: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/shell/routes.tsx shell/src/pages/CatalogPage.test.tsx shell/src/shell/routes.test.tsx
git commit -m "feat(shell): /bookmarks catalog + bookmark-aware open navigation (SP-14m)"
```

---

