## Task 4: Shell — types, `itemClient`, hooks

**Files:**
- Modify: `shell/src/api/types.ts:2` (`ResourceType`), insert near `:215-241` (new `Bookmark*` types + `CreateBookmarkInput`), `:103-...` (`ItemClient` interface — add `createBookmarkItem`/`getBookmarkConfig`)
- Modify: `shell/src/api/itemClient.ts:1-2` (imports), insert near `:605-619` (`createBookmarkItem`/`getBookmarkConfig` implementations)
- Modify: `shell/src/api/hooks.ts` (add `useCreateBookmark`, near `:208-217`)
- Test: `shell/src/api/itemClient.test.ts` (append), `shell/src/api/hooks.test.tsx` (append, if it covers `useCreateDataset` — mirror that pattern)

**Interfaces:**
- Consumes: `AnalyticsContextState` shape (`shell/src/builder/AnalyticsContext.tsx:1-13`) — `BookmarkPayload`'s `timeRange`/`extent`/`crossFilter` fields are a byte-for-byte copy of that type's fields, plus `appId`/`pageId`.
- Produces: `CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload` (`BookmarkPayload` itself already carries `appId`/`pageId`/`timeRange`/`extent`/`crossFilter`), `client.createBookmarkItem(input): Promise<Item>`, `client.getBookmarkConfig(pk): Promise<BookmarkPayload>`, `useCreateBookmark()` mutation hook. Task 5 and Task 6 both import these.

- [ ] **Step 1: Write the failing itemClient tests**

Append to `shell/src/api/itemClient.test.ts` (after the `createDatasetItem`/`getDatasetConfig` tests, following the exact same style — check an existing `createMapItem`/`createDatasetItem` test above for the `makeClient()`/`server.use(...)` harness already in this file and reuse it verbatim):

```typescript
test("createBookmarkItem posts a bookmark payload and returns a bookmark Item", async () => {
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      const body = (await request.json()) as { title: string; config: unknown };
      expect(body.config).toEqual({
        version: 1,
        kind: "bookmark",
        bookmark: {
          appId: "app-1", pageId: "page-1",
          timeRange: { from: "2026-01-01", to: "2026-02-01" },
          extent: null, crossFilter: {},
        },
      });
      return HttpResponse.json({ id: "cfg-bookmark", kind: "bookmark", itemId: "bookmark-1" }, { status: 201 });
    }),
  );
  const item = await makeClient().createBookmarkItem({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
  });
  expect(item).toEqual({
    pk: "bookmark-1", resourceType: "bookmark", title: "Ma vue", abstract: "",
    owner: "alice", thumbnailUrl: null, date: "", configId: "cfg-bookmark", isPublished: false,
  });
});

test("getBookmarkConfig reads the bookmark payload from the by-item config", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-1", () =>
      HttpResponse.json({
        id: "cfg-bookmark", itemId: "bookmark-1", kind: "bookmark",
        config: {
          version: 1, kind: "bookmark",
          bookmark: {
            appId: "app-1", pageId: "page-1",
            timeRange: { from: "2026-01-01", to: "2026-02-01" },
            extent: null, crossFilter: {},
          },
        },
      }),
    ),
  );
  const payload = await makeClient().getBookmarkConfig("bookmark-1");
  expect(payload).toEqual({
    appId: "app-1", pageId: "page-1",
    timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
  });
});

test("getBookmarkConfig throws when the config has no bookmark payload", async () => {
  server.use(
    http.get("https://core.test/configs/by-item/bookmark-2", () =>
      HttpResponse.json({ id: "cfg-x", itemId: "bookmark-2", kind: "bookmark", config: { version: 1, kind: "bookmark" } }),
    ),
  );
  await expect(makeClient().getBookmarkConfig("bookmark-2")).rejects.toThrow();
});
```

(`server`/`http`/`HttpResponse` are already imported at the top of `itemClient.test.ts:2-3`, and `makeClient` is already defined at `:6` — the same harness the existing `createDatasetItem` tests use. Nothing new to import.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `createBookmarkItem`/`getBookmarkConfig` don't exist on the client yet (TypeScript compile error / `undefined is not a function`).

- [ ] **Step 3: Add the types**

In `shell/src/api/types.ts`, extend `ResourceType` (line 2):

```typescript
export type ResourceType = "app" | "dashboard" | "map" | "site" | "dataset" | "external" | "bookmark";
```

Insert near the `DatasetConfig`/`CreateDatasetInput` block (after line 241, before `export type FeatureLayerSource`):

```typescript
export type BookmarkCrossFilterValue = string | string[] | { from: string; to: string };
export type BookmarkCrossFilterEntry = { field: string; value: BookmarkCrossFilterValue; originSourceId: string };

export type BookmarkPayload = {
  appId: string;
  pageId: string;
  timeRange: { from: string; to: string } | null;
  extent: [number, number, number, number] | null;
  crossFilter: Record<string, BookmarkCrossFilterEntry>;
};

export type CreateBookmarkInput = { title: string; owner: string } & BookmarkPayload;
```

Add to the `ItemClient` interface (after `createDatasetItem`, around line 136):

```typescript
  createDatasetItem(input: CreateDatasetInput): Promise<Item>;
  createBookmarkItem(input: CreateBookmarkInput): Promise<Item>;
  getBookmarkConfig(pk: string): Promise<BookmarkPayload>;
```

- [ ] **Step 4: Implement `itemClient.ts`**

Extend the type import at the top of `shell/src/api/itemClient.ts` (line 2) with `BookmarkPayload, CreateBookmarkInput`.

Insert after `createDatasetItem` (after line 605, before `getDatasetConfig`):

```typescript
    async createBookmarkItem(input: CreateBookmarkInput): Promise<Item> {
      const bookmark: BookmarkPayload = {
        appId: input.appId, pageId: input.pageId,
        timeRange: input.timeRange, extent: input.extent, crossFilter: input.crossFilter,
      };
      const config = { version: 1, kind: "bookmark", bookmark };
      const data = await request<{ id: string | number; kind: string; itemId: string | null }>(
        "POST", `/configs`, { title: input.title, config },
      );
      if (!data.itemId) throw new Error("createBookmarkItem: core returned no itemId");
      return {
        pk: String(data.itemId), resourceType: "bookmark", title: input.title, abstract: "",
        owner: input.owner, thumbnailUrl: null, date: "", configId: String(data.id),
        isPublished: false,
      };
    },

    async getBookmarkConfig(pk: string): Promise<BookmarkPayload> {
      const data = await request<{ config?: { bookmark?: BookmarkPayload } }>(
        "GET", `/configs/by-item/${pk}`,
      );
      if (!data.config?.bookmark) throw new Error("getBookmarkConfig: config has no bookmark payload");
      return data.config.bookmark;
    },
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS

- [ ] **Step 6: Write the failing hook test**

`hooks.test.tsx` has no dedicated test for `useCreateDataset`, but it does have one for `useCreateMap` (`shell/src/api/hooks.test.tsx:140-147`), using its own `makeWrapper(client: ItemClient)` helper (`:129-138`, distinct from the file's other `wrapper` function used by hooks that don't need a custom per-test client). Add the mirror for `useCreateBookmark` right after the `useCreateMap` test:

```typescript
test("useCreateBookmark creates a bookmark and invalidates items", async () => {
  const client = {
    createBookmarkItem: vi.fn().mockResolvedValue({ pk: "bookmark-1", resourceType: "bookmark", title: "Ma vue" }),
  } as unknown as ItemClient;
  const { result } = renderHook(() => useCreateBookmark(), { wrapper: makeWrapper(client) });
  await result.current.mutateAsync({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: null, extent: null, crossFilter: {},
  });
  expect(client.createBookmarkItem).toHaveBeenCalledWith({
    title: "Ma vue", owner: "alice", appId: "app-1", pageId: "page-1",
    timeRange: null, extent: null, crossFilter: {},
  });
});
```

Add `useCreateBookmark` to this file's import from `./hooks` (line 10).

- [ ] **Step 7: Implement `useCreateBookmark`**

In `shell/src/api/hooks.ts`, add after `useCreateDataset` (after line 217):

```typescript
export function useCreateBookmark() {
  const client = useItemClientInternal();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: CreateBookmarkInput) => client.createBookmarkItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
```

Add `CreateBookmarkInput` to this file's type import from `./types`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts src/api/hooks.test.tsx`
Expected: PASS

- [ ] **Step 9: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: 398+ tests, all green (no regressions — every change so far is additive: a new `ResourceType` member, new types, new interface methods, new client methods, new hook).

- [ ] **Step 10: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/hooks.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): bookmark item client + hook (SP-14m)"
```

---

