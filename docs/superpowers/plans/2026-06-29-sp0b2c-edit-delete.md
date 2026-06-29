# Front Item Edit / Thumbnail / Delete (SP-0b.2-c) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the App/Dashboard item lifecycle in the GeoStudio shell — rename, edit metadata (title/abstract/keywords), upload a thumbnail, and delete — with optimistic updates and rollback, plus the Builder Service "by-item" operations that let the front act on a catalog item using only its GeoNode `pk`.

**Architecture:** Add `get_config_by_item` to the Builder Service repository and `GET`/`DELETE /configs/by-item/{itemId}` routes (so the front never needs the internal config id). On the front, extend the `item-client` façade (`updateItem` → PATCH GeoNode, `uploadThumbnail` → PUT GeoNode, `deleteItem(pk)` → DELETE by-item), add TanStack Query mutation hooks with optimistic update + rollback, and build `MetadataForm`, `ThumbnailUpload`, `ConfirmDialog`, and a self-contained `ItemActions` menu mounted on each catalog card and the item detail page.

**Tech Stack:** Backend: Python 3.12, FastAPI, SQLAlchemy 2.0, pytest. Front: React 19, TypeScript, @tanstack/react-query, react-router-dom, Vitest + Testing Library + MSW, Playwright. (No new dependencies.)

## Global Constraints

- Backend work under `builder-service/` (`uv run pytest`); front under `shell/` (`npm test`, `npm run build`, `npm run e2e`).
- Keep both test suites' output clean (pytest `filterwarnings = ["error"]`; MSW `onUnhandledRequest: "error"`).
- Delete resolves by GeoNode `pk` via the Builder Service by-item routes (decision validated): the front calls `deleteItem(pk)`, never a config id.
- The Builder route handlers use the repository layer only — no direct ORM imports (consistent with SP-0b.2-a).
- Symmetric delete preserved: deleting removes the config, its revisions, and the GeoNode item.
- Front: all network access via `item-client`; no token in localStorage; URLs from injected opts.
- Existing contracts stay stable; only additions. `Item` shape unchanged.
- Edit applies to `title`, `abstract`, `keywords` (PATCH GeoNode). Thumbnail: client validates `image/*` and `≤ 2 MB` before upload.
- `deleteItem` treats HTTP `404` as success (item already gone) per the SP-0b.2 spec §6.

---

### Task 1: Builder repository `get_config_by_item`

**Files:**
- Modify: `builder-service/app/repository.py`
- Test: `builder-service/tests/test_repository.py` (add cases)

**Interfaces:**
- Consumes: `Config`, `ConfigRevision`, existing `_latest_revision`/`_to_read`/`ConfigRead`.
- Produces: `get_config_by_item(session: Session, item_id: str) -> ConfigRead | None` — finds the `Config` whose `item_id` matches; returns its latest-revision `ConfigRead`, or `None` if no config has that `item_id`.

- [ ] **Step 1: Write the failing tests**

Add to `builder-service/tests/test_repository.py`:

```python
def test_get_config_by_item_returns_latest(session):
    created = repo.create_config(session, _config(widget="map"), item_id="item-7")
    repo.update_config(session, created.id, _config(widget="table"))
    found = repo.get_config_by_item(session, "item-7")
    assert found is not None
    assert found.id == created.id
    assert found.itemId == "item-7"
    assert found.config.layout.items[0].widget == "table"


def test_get_config_by_item_missing_returns_none(session):
    assert repo.get_config_by_item(session, "nope") is None
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_repository.py -k by_item -v`
Expected: FAIL — `AttributeError: module 'app.repository' has no attribute 'get_config_by_item'`.

- [ ] **Step 3: Implement in `builder-service/app/repository.py`**

```python
def get_config_by_item(session: Session, item_id: str) -> ConfigRead | None:
    record = session.scalar(select(Config).where(Config.item_id == item_id))
    if record is None:
        return None
    revision = _latest_revision(session, record.id)
    if revision is None:
        return None
    return _to_read(record, revision)
```

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_repository.py -v`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add builder-service/app/repository.py builder-service/tests/test_repository.py
git commit -m "feat(builder-service): add repository.get_config_by_item"
```

---

### Task 2: Builder `GET` + `DELETE /configs/by-item/{itemId}` routes

**Files:**
- Modify: `builder-service/app/routes.py`
- Test: `builder-service/tests/test_routes.py` (add cases)

**Interfaces:**
- Consumes: `repo.get_config_by_item`, `repo.delete_config`, `ItemClient.delete_item`, existing deps; `ConfigRead` response model.
- Produces:
  - `GET /configs/by-item/{item_id}` → `200 ConfigRead` or `404`.
  - `DELETE /configs/by-item/{item_id}` → look up config by item; `404` if none; else `items.delete_item(item_id)` then `repo.delete_config(<config id>)`; `204` empty body.

- [ ] **Step 1: Write the failing tests**

Add to `builder-service/tests/test_routes.py`:

```python
def test_get_config_by_item(client):
    created = _create(client)
    item_id = created["itemId"]
    response = client.get(f"/configs/by-item/{item_id}")
    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_config_by_item_missing_returns_404(client):
    assert client.get("/configs/by-item/nope").status_code == 404


def test_delete_by_item_removes_config_and_item(client):
    created = _create(client)
    item_id = created["itemId"]
    response = client.delete(f"/configs/by-item/{item_id}")
    assert response.status_code == 204
    assert response.content == b""
    assert client.stub.deleted == [item_id]
    assert client.get(f"/configs/{created['id']}").status_code == 404


def test_delete_by_item_missing_returns_404(client):
    assert client.delete("/configs/by-item/nope").status_code == 404
```

- [ ] **Step 2: Run to verify they fail**

Run: `uv run pytest tests/test_routes.py -k by_item -v`
Expected: FAIL — 404/405 (routes don't exist yet).

- [ ] **Step 3: Add the routes to `builder-service/app/routes.py`**

```python
@router.get("/configs/by-item/{item_id}", response_model=ConfigRead)
def get_config_by_item(
    item_id: str, session: Session = Depends(get_session)
) -> ConfigRead:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    return result


@router.delete(
    "/configs/by-item/{item_id}", status_code=status.HTTP_204_NO_CONTENT
)
def delete_config_by_item(
    item_id: str,
    session: Session = Depends(get_session),
    items: ItemClient = Depends(get_item_client),
) -> Response:
    result = repo.get_config_by_item(session, item_id)
    if result is None:
        raise HTTPException(status_code=404, detail="config not found")
    if result.itemId:
        items.delete_item(result.itemId)
    repo.delete_config(session, result.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
```

(`ConfigRead`, `Response`, `status`, `Depends`, `HTTPException`, `ItemClient`, `repo`, `get_session`, `get_item_client` are all already imported in this file from earlier phases.)

- [ ] **Step 4: Run to verify they pass**

Run: `uv run pytest tests/test_routes.py -v`
Expected: PASS (existing + 4 new).

- [ ] **Step 5: Run the full backend suite**

Run: `uv run pytest -q`
Expected: PASS, pristine.

- [ ] **Step 6: Commit**

```bash
git add builder-service/app/routes.py builder-service/tests/test_routes.py
git commit -m "feat(builder-service): add GET/DELETE /configs/by-item/{itemId}"
```

---

### Task 3: item-client `updateItem` / `uploadThumbnail` / `deleteItem` + create null-guard

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Test: `shell/src/api/itemClient.test.ts` (add cases)

**Interfaces:**
- Consumes: existing `createItemClient`, `Item`, `toItem`.
- Produces:
  - `type UpdatePatch = { title?: string; abstract?: string; keywords?: string[] }` in `types.ts`.
  - On `ItemClient`: `updateItem(pk: string, patch: UpdatePatch): Promise<Item>`; `uploadThumbnail(pk: string, file: File): Promise<void>`; `deleteItem(pk: string): Promise<void>`.
  - `updateItem` → `PATCH {geonodeUrl}/api/v2/resources/{pk}` (JSON patch), maps `{resource}` via `toItem`.
  - `uploadThumbnail` → `PUT {geonodeUrl}/api/v2/resources/{pk}/set_thumbnail` (FormData with `file`); throws on non-ok.
  - `deleteItem` → `DELETE {builderUrl}/configs/by-item/{pk}`; resolves on `res.ok` OR `res.status === 404`; throws otherwise.
  - `createConfigItem` now throws `Error("createConfigItem: builder returned no itemId")` when the response `itemId` is falsy (the null-guard from the SP-0b.2-b final review).

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts`:

```ts
test("updateItem PATCHes GeoNode and maps the result", async () => {
  const item = await makeClient().updateItem("7", { title: "Renamed", abstract: "New" });
  expect(item.pk).toBe("7");
  expect(item.title).toBe("Renamed");
  expect(item.abstract).toBe("New");
});

test("uploadThumbnail PUTs multipart without throwing", async () => {
  const file = new File(["x"], "t.png", { type: "image/png" });
  await expect(makeClient().uploadThumbnail("7", file)).resolves.toBeUndefined();
});

test("deleteItem DELETEs the by-item endpoint", async () => {
  let url: string | null = null;
  server.use(
    http.delete("https://builder.test/configs/by-item/:pk", ({ request }) => {
      url = new URL(request.url).pathname;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  await makeClient().deleteItem("42");
  expect(url).toBe("/configs/by-item/42");
});

test("deleteItem treats 404 as success", async () => {
  server.use(
    http.delete("https://builder.test/configs/by-item/:pk", () =>
      new HttpResponse(null, { status: 404 }),
    ),
  );
  await expect(makeClient().deleteItem("gone")).resolves.toBeUndefined();
});

test("createConfigItem throws when builder returns no itemId", async () => {
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      const body = (await request.json()) as { config: { kind: string } };
      return HttpResponse.json({ id: "c", kind: body.config.kind, itemId: null, version: 1, config: body.config });
    }),
  );
  await expect(
    makeClient().createConfigItem({ kind: "app", title: "T", owner: "o" }),
  ).rejects.toThrow(/itemId/);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: FAIL — methods missing / no MSW handlers for PATCH, PUT, DELETE by-item.

- [ ] **Step 3: Add types in `shell/src/api/types.ts`**

```ts
export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[] };
```

On `interface ItemClient`, add:

```ts
  updateItem(pk: string, patch: UpdatePatch): Promise<Item>;
  uploadThumbnail(pk: string, file: File): Promise<void>;
  deleteItem(pk: string): Promise<void>;
```

- [ ] **Step 4: Implement in `shell/src/api/itemClient.ts`**

Add `UpdatePatch` to the type import. In `createConfigItem`, after parsing `data`, add the guard before mapping:

```ts
      if (!data.itemId) {
        throw new Error("createConfigItem: builder returned no itemId");
      }
```

Add the three methods to the returned object:

```ts
    async updateItem(pk: string, patch: UpdatePatch): Promise<Item> {
      const token = getToken();
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(patch),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PATCH /resources/${pk}`);
      }
      const data = (await res.json()) as { resource: GeoNodeResource };
      return toItem(data.resource);
    },

    async uploadThumbnail(pk: string, file: File): Promise<void> {
      const token = getToken();
      const form = new FormData();
      form.append("file", file);
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}/set_thumbnail`, {
        method: "PUT",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
        body: form,
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PUT thumbnail`);
      }
    },

    async deleteItem(pk: string): Promise<void> {
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs/by-item/${pk}`, {
        method: "DELETE",
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok && res.status !== 404) {
        throw new Error(`Request failed: ${res.status} DELETE /configs/by-item/${pk}`);
      }
    },
```

- [ ] **Step 5: Add MSW handlers in `shell/src/test/msw/handlers.ts`**

```ts
  http.patch(`${GEONODE}/api/v2/resources/:pk`, async ({ params, request }) => {
    const patch = (await request.json()) as Record<string, unknown>;
    return HttpResponse.json({
      resource: {
        pk: String(params.pk),
        resource_type: "app",
        title: (patch.title as string) ?? "Item",
        abstract: (patch.abstract as string) ?? "",
        owner: { username: "alice" },
        thumbnail_url: null,
        date: "2026-01-01T00:00:00Z",
      },
    });
  }),

  http.put(`${GEONODE}/api/v2/resources/:pk/set_thumbnail`, () =>
    new HttpResponse(null, { status: 200 }),
  ),

  http.delete("https://builder.test/configs/by-item/:pk", () =>
    new HttpResponse(null, { status: 204 }),
  ),
```

- [ ] **Step 6: Run to verify they pass**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: PASS (existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/test/msw/handlers.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add updateItem/uploadThumbnail/deleteItem + create null-guard"
```

---

### Task 4: Mutation hooks (`useUpdateItem`, `useUploadThumbnail`, `useDeleteItem`)

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx` (add cases)

**Interfaces:**
- Consumes: `useItemClient`, `useMutation`, `useQueryClient`, `UpdatePatch`, `Item`, `ItemPage`.
- Produces:
  - `useDeleteItem()` — `mutationFn: (pk) => client.deleteItem(pk)`; `onMutate` optimistically removes the item from every `["items", *]` page (snapshot via `getQueriesData`); `onError` restores the snapshot; `onSettled` invalidates `["items"]`.
  - `useUpdateItem(pk)` — `mutationFn: (patch) => client.updateItem(pk, patch)`; `onMutate` optimistically merges `title`/`abstract` into `["item", pk]` and into every `["items", *]` page; `onError` restores; `onSettled` invalidates both.
  - `useUploadThumbnail(pk)` — `mutationFn: (file) => client.uploadThumbnail(pk, file)`; `onSuccess` invalidates `["item", pk]` and `["items"]`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/hooks.test.tsx`:

```tsx
import { useDeleteItem, useUpdateItem } from "./hooks";

test("useDeleteItem optimistically removes the item from the list", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  const wrap = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
  queryClient.setQueryData(["items", {}], {
    items: [
      { pk: "1", resourceType: "app", title: "A", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
      { pk: "2", resourceType: "app", title: "B", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
    ],
    total: 2,
    page: 1,
    pageSize: 12,
  });

  const { result } = renderHook(() => useDeleteItem(), { wrapper: wrap });
  await act(async () => {
    await result.current.mutateAsync("1");
  });
  const page = queryClient.getQueryData(["items", {}]) as { items: { pk: string }[] };
  expect(page.items.map((i) => i.pk)).toEqual(["2"]);
});

test("useUpdateItem updates the cached item title", async () => {
  const { result } = renderHook(() => useUpdateItem("7"), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ title: "Renamed" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.title).toBe("Renamed");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: FAIL — `useDeleteItem`/`useUpdateItem` not exported.

- [ ] **Step 3: Implement in `shell/src/api/hooks.ts`**

Add to the type import: `import type { CreateKind, Item, ItemPage, ListItemsParams, UpdatePatch } from "./types";`

Add the hooks:

```ts
export function useDeleteItem() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (pk: string) => client.deleteItem(pk),
    onMutate: async (pk: string) => {
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const previous = queryClient.getQueriesData<ItemPage>({ queryKey: ["items"] });
      queryClient.setQueriesData<ItemPage>({ queryKey: ["items"] }, (old) =>
        old
          ? { ...old, items: old.items.filter((i) => i.pk !== pk), total: old.total - 1 }
          : old,
      );
      return { previous };
    },
    onError: (_err, _pk, ctx) => {
      ctx?.previous.forEach(([key, data]) => queryClient.setQueryData(key, data));
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUpdateItem(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: UpdatePatch) => client.updateItem(pk, patch),
    onMutate: async (patch: UpdatePatch) => {
      await queryClient.cancelQueries({ queryKey: ["item", pk] });
      await queryClient.cancelQueries({ queryKey: ["items"] });
      const prevItem = queryClient.getQueryData<Item>(["item", pk]);
      const prevLists = queryClient.getQueriesData<ItemPage>({ queryKey: ["items"] });
      const merge = (i: Item): Item => ({
        ...i,
        ...(patch.title !== undefined ? { title: patch.title } : {}),
        ...(patch.abstract !== undefined ? { abstract: patch.abstract } : {}),
      });
      queryClient.setQueryData<Item>(["item", pk], (old) => (old ? merge(old) : old));
      queryClient.setQueriesData<ItemPage>({ queryKey: ["items"] }, (old) =>
        old ? { ...old, items: old.items.map((i) => (i.pk === pk ? merge(i) : i)) } : old,
      );
      return { prevItem, prevLists };
    },
    onError: (_err, _patch, ctx) => {
      if (ctx) {
        queryClient.setQueryData(["item", pk], ctx.prevItem);
        ctx.prevLists.forEach(([key, data]) => queryClient.setQueryData(key, data));
      }
    },
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}

export function useUploadThumbnail(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => client.uploadThumbnail(pk, file),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["item", pk] });
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
```

- [ ] **Step 4: Run to verify they pass**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: PASS (existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): add update/delete/thumbnail mutation hooks with optimistic rollback"
```

---

### Task 5: `MetadataForm` component

**Files:**
- Create: `shell/src/ui/MetadataForm.tsx`
- Test: `shell/src/ui/MetadataForm.test.tsx`

**Interfaces:**
- Consumes: `Input`, `Button`.
- Produces: `MetadataForm({ initial, onSubmit, onCancel, pending }: { initial: { title: string; abstract: string; keywords: string[] }; onSubmit: (v: { title: string; abstract: string; keywords: string[] }) => void; onCancel: () => void; pending?: boolean })` — a form with Titre (`aria-label="Titre"`), Résumé (`aria-label="Résumé"`, textarea), Mots-clés (`aria-label="Mots-clés"`, comma-separated text). On submit with a non-empty title, calls `onSubmit` with `{ title: trimmed, abstract, keywords: split-on-comma-trimmed-nonempty }`. Enregistrer button disabled when `pending` or title empty; Annuler calls `onCancel`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/ui/MetadataForm.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { MetadataForm } from "./MetadataForm";

test("submits trimmed title, abstract and split keywords", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "Old", abstract: "A", keywords: ["k1"] }}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  const title = screen.getByLabelText("Titre");
  await userEvent.clear(title);
  await userEvent.type(title, "  New  ");
  const kw = screen.getByLabelText("Mots-clés");
  await userEvent.clear(kw);
  await userEvent.type(kw, "a, b ,c");
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).toHaveBeenCalledWith({ title: "New", abstract: "A", keywords: ["a", "b", "c"] });
});

test("does not submit an empty title", async () => {
  const onSubmit = vi.fn();
  render(
    <MetadataForm
      initial={{ title: "", abstract: "", keywords: [] }}
      onSubmit={onSubmit}
      onCancel={() => {}}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  expect(onSubmit).not.toHaveBeenCalled();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/ui/MetadataForm.test.tsx`
Expected: FAIL — cannot resolve `./MetadataForm`.

- [ ] **Step 3: Create `shell/src/ui/MetadataForm.tsx`**

```tsx
import { useState } from "react";
import { Button } from "./button";
import { Input } from "./input";

export function MetadataForm({
  initial,
  onSubmit,
  onCancel,
  pending,
}: {
  initial: { title: string; abstract: string; keywords: string[] };
  onSubmit: (v: { title: string; abstract: string; keywords: string[] }) => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  const [title, setTitle] = useState(initial.title);
  const [abstract, setAbstract] = useState(initial.abstract);
  const [keywords, setKeywords] = useState(initial.keywords.join(", "));

  function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    onSubmit({
      title: clean,
      abstract,
      keywords: keywords
        .split(",")
        .map((k) => k.trim())
        .filter((k) => k.length > 0),
    });
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-3">
      <label className="flex flex-col gap-1 text-sm">
        Titre
        <Input aria-label="Titre" value={title} onChange={(e) => setTitle(e.target.value)} />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Résumé
        <textarea
          aria-label="Résumé"
          className="min-h-20 rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
          value={abstract}
          onChange={(e) => setAbstract(e.target.value)}
        />
      </label>
      <label className="flex flex-col gap-1 text-sm">
        Mots-clés
        <Input
          aria-label="Mots-clés"
          value={keywords}
          onChange={(e) => setKeywords(e.target.value)}
        />
      </label>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="submit" size="sm" disabled={pending || !title.trim()}>
          Enregistrer
        </Button>
      </div>
    </form>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/ui/MetadataForm.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/MetadataForm.tsx shell/src/ui/MetadataForm.test.tsx
git commit -m "feat(shell): add MetadataForm component"
```

---

### Task 6: `ThumbnailUpload` component (client-side validation)

**Files:**
- Create: `shell/src/ui/ThumbnailUpload.tsx`
- Test: `shell/src/ui/ThumbnailUpload.test.tsx`

**Interfaces:**
- Consumes: `Button`.
- Produces: `ThumbnailUpload({ onUpload, pending }: { onUpload: (file: File) => void; pending?: boolean })` — a file input (`aria-label="Miniature"`, `accept="image/*"`). On file selection it validates `type.startsWith("image/")` and `size <= 2 * 1024 * 1024`; on failure renders `role="alert"` with the reason and does NOT call `onUpload`; on success calls `onUpload(file)`. The constant `MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024` is module-level.

- [ ] **Step 1: Write the failing test**

Create `shell/src/ui/ThumbnailUpload.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ThumbnailUpload } from "./ThumbnailUpload";

test("calls onUpload for a valid image", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const file = new File(["x"], "t.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText("Miniature"), file);
  expect(onUpload).toHaveBeenCalledWith(file);
  expect(screen.queryByRole("alert")).not.toBeInTheDocument();
});

test("rejects a non-image file", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const file = new File(["x"], "t.txt", { type: "text/plain" });
  await userEvent.upload(screen.getByLabelText("Miniature"), file);
  expect(onUpload).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});

test("rejects an image larger than 2 MB", async () => {
  const onUpload = vi.fn();
  render(<ThumbnailUpload onUpload={onUpload} />);
  const big = new File([new Uint8Array(2 * 1024 * 1024 + 1)], "big.png", { type: "image/png" });
  await userEvent.upload(screen.getByLabelText("Miniature"), big);
  expect(onUpload).not.toHaveBeenCalled();
  expect(screen.getByRole("alert")).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/ui/ThumbnailUpload.test.tsx`
Expected: FAIL — cannot resolve `./ThumbnailUpload`.

- [ ] **Step 3: Create `shell/src/ui/ThumbnailUpload.tsx`**

```tsx
import { useState } from "react";

export const MAX_THUMBNAIL_BYTES = 2 * 1024 * 1024;

export function ThumbnailUpload({
  onUpload,
  pending,
}: {
  onUpload: (file: File) => void;
  pending?: boolean;
}) {
  const [error, setError] = useState<string | null>(null);

  function onChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    if (!file.type.startsWith("image/")) {
      setError("Le fichier doit être une image.");
      return;
    }
    if (file.size > MAX_THUMBNAIL_BYTES) {
      setError("L'image dépasse 2 Mo.");
      return;
    }
    setError(null);
    onUpload(file);
  }

  return (
    <div className="flex flex-col gap-1 text-sm">
      <label className="flex flex-col gap-1">
        Miniature
        <input
          aria-label="Miniature"
          type="file"
          accept="image/*"
          disabled={pending}
          onChange={onChange}
        />
      </label>
      {error && (
        <p role="alert" className="text-sm text-red-600">
          {error}
        </p>
      )}
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/ui/ThumbnailUpload.test.tsx`
Expected: PASS (3 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/ThumbnailUpload.tsx shell/src/ui/ThumbnailUpload.test.tsx
git commit -m "feat(shell): add ThumbnailUpload with client-side validation"
```

---

### Task 7: `ConfirmDialog` + `ItemActions` menu + `ItemCard` actions slot

**Files:**
- Create: `shell/src/ui/ConfirmDialog.tsx`
- Create: `shell/src/shell/ItemActions.tsx`
- Modify: `shell/src/ui/ItemCard.tsx`
- Test: `shell/src/ui/ConfirmDialog.test.tsx`
- Test: `shell/src/shell/ItemActions.test.tsx`
- Test: `shell/src/ui/ItemCard.test.tsx` (add an actions-slot case)

**Interfaces:**
- Consumes: `Dialog`, `Button`, `MetadataForm`, `ThumbnailUpload`, `useUpdateItem`, `useUploadThumbnail`, `useDeleteItem`, `Item`.
- Produces:
  - `ConfirmDialog({ open, title, message, confirmLabel, onConfirm, onCancel, pending }: { open: boolean; title: string; message: string; confirmLabel: string; onConfirm: () => void; onCancel: () => void; pending?: boolean })` — a `Dialog` with the message and Annuler/confirm buttons.
  - `ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void })` — a "Actions" button toggling a small menu with **Renommer/Modifier**, **Miniature**, **Supprimer**. "Modifier" opens a `Dialog` with `MetadataForm` (initial from the item; keywords default `[]`) wired to `useUpdateItem(item.pk)`. "Miniature" opens a `Dialog` with `ThumbnailUpload` wired to `useUploadThumbnail(item.pk)`. "Supprimer" opens a `ConfirmDialog` wired to `useDeleteItem`; on success calls `onDeleted?.()`. All dialogs close on success.
  - `ItemCard` gains an optional `actions?: React.ReactNode` prop rendered in the card header; existing props/behavior unchanged.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/ui/ConfirmDialog.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { ConfirmDialog } from "./ConfirmDialog";

test("confirm and cancel fire their callbacks", async () => {
  const onConfirm = vi.fn();
  const onCancel = vi.fn();
  render(
    <ConfirmDialog
      open
      title="Supprimer"
      message="Sûr ?"
      confirmLabel="Supprimer"
      onConfirm={onConfirm}
      onCancel={onCancel}
    />,
  );
  expect(screen.getByText("Sûr ?")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  expect(onConfirm).toHaveBeenCalled();
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(onCancel).toHaveBeenCalled();
});
```

Add to `shell/src/ui/ItemCard.test.tsx`:

```tsx
test("renders the actions slot when provided", () => {
  render(<ItemCard item={item} onOpen={() => {}} actions={<span>ACTIONS</span>} />);
  expect(screen.getByText("ACTIONS")).toBeInTheDocument();
});
```

Create `shell/src/shell/ItemActions.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
import { ItemActions } from "./ItemActions";

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Old",
  abstract: "A",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false }, mutations: { retry: false } } });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("renames an item via the edit dialog", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /modifier/i }));
  const title = screen.getByLabelText("Titre");
  await userEvent.clear(title);
  await userEvent.type(title, "Renamed");
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("deletes an item after confirmation and calls onDeleted", async () => {
  const onDeleted = vi.fn();
  render(
    <Harness>
      <ItemActions item={item} onDeleted={onDeleted} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /supprimer/i }));
  // Confirm in the dialog
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(onDeleted).toHaveBeenCalled());
});
```

Add `import { within } from "@testing-library/react";` at the top of `ItemActions.test.tsx`.

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/ui/ConfirmDialog.test.tsx src/shell/ItemActions.test.tsx src/ui/ItemCard.test.tsx`
Expected: FAIL — modules / actions prop missing.

- [ ] **Step 3: Create `shell/src/ui/ConfirmDialog.tsx`**

```tsx
import { Button } from "./button";
import { Dialog } from "./dialog";

export function ConfirmDialog({
  open,
  title,
  message,
  confirmLabel,
  onConfirm,
  onCancel,
  pending,
}: {
  open: boolean;
  title: string;
  message: string;
  confirmLabel: string;
  onConfirm: () => void;
  onCancel: () => void;
  pending?: boolean;
}) {
  return (
    <Dialog open={open} onClose={onCancel} title={title}>
      <p className="mb-4 text-sm text-slate-600">{message}</p>
      <div className="flex justify-end gap-2">
        <Button type="button" variant="outline" size="sm" onClick={onCancel}>
          Annuler
        </Button>
        <Button type="button" size="sm" disabled={pending} onClick={onConfirm}>
          {confirmLabel}
        </Button>
      </div>
    </Dialog>
  );
}
```

- [ ] **Step 4: Add the `actions` slot to `shell/src/ui/ItemCard.tsx`**

Add `actions?: React.ReactNode` to the props type and render it in the card header next to the type badge:

```tsx
export function ItemCard({
  item,
  onOpen,
  actions,
}: {
  item: Item;
  onOpen: (pk: string) => void;
  actions?: React.ReactNode;
}) {
  return (
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {item.resourceType}
        </span>
        {actions}
      </div>
      <h3 className="text-base font-semibold">{item.title}</h3>
      <p className="line-clamp-2 text-sm text-slate-500">{item.abstract}</p>
      <Button size="sm" className="mt-2 w-fit" onClick={() => onOpen(item.pk)}>
        Ouvrir
      </Button>
    </Card>
  );
}
```

- [ ] **Step 5: Create `shell/src/shell/ItemActions.tsx`**

```tsx
import { useState } from "react";
import { useDeleteItem, useUpdateItem, useUploadThumbnail } from "../api/hooks";
import type { Item } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { ConfirmDialog } from "../ui/ConfirmDialog";
import { MetadataForm } from "../ui/MetadataForm";
import { ThumbnailUpload } from "../ui/ThumbnailUpload";

type Panel = null | "menu" | "edit" | "thumbnail" | "delete";

export function ItemActions({ item, onDeleted }: { item: Item; onDeleted?: () => void }) {
  const [panel, setPanel] = useState<Panel>(null);
  const update = useUpdateItem(item.pk);
  const thumbnail = useUploadThumbnail(item.pk);
  const remove = useDeleteItem();

  async function save(v: { title: string; abstract: string; keywords: string[] }) {
    try {
      await update.mutateAsync(v);
      setPanel(null);
    } catch {
      /* surfaced via update.isError */
    }
  }

  async function upload(file: File) {
    try {
      await thumbnail.mutateAsync(file);
      setPanel(null);
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }

  async function confirmDelete() {
    try {
      await remove.mutateAsync(item.pk);
      setPanel(null);
      onDeleted?.();
    } catch {
      /* surfaced via remove.isError */
    }
  }

  return (
    <>
      <Button size="sm" variant="ghost" aria-label="Actions" onClick={() => setPanel("menu")}>
        ⋯
      </Button>

      {panel === "menu" && (
        <div className="absolute z-20 mt-8 flex flex-col rounded-md border border-slate-200 bg-white text-sm shadow">
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("edit")}>
            Modifier
          </button>
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("thumbnail")}>
            Miniature
          </button>
          <button className="px-3 py-1 text-left text-red-600 hover:bg-slate-100" onClick={() => setPanel("delete")}>
            Supprimer
          </button>
        </div>
      )}

      <Dialog open={panel === "edit"} onClose={() => setPanel(null)} title="Modifier l'élément">
        <MetadataForm
          initial={{ title: item.title, abstract: item.abstract, keywords: [] }}
          onSubmit={save}
          onCancel={() => setPanel(null)}
          pending={update.isPending}
        />
        {update.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            Échec de l'enregistrement.
          </p>
        )}
      </Dialog>

      <Dialog open={panel === "thumbnail"} onClose={() => setPanel(null)} title="Miniature">
        <ThumbnailUpload onUpload={upload} pending={thumbnail.isPending} />
        {thumbnail.isError && (
          <p role="alert" className="mt-2 text-sm text-red-600">
            Échec de l'envoi.
          </p>
        )}
      </Dialog>

      <ConfirmDialog
        open={panel === "delete"}
        title="Supprimer l'élément"
        message={`Supprimer « ${item.title} » ? Cette action est irréversible.`}
        confirmLabel="Supprimer"
        pending={remove.isPending}
        onConfirm={confirmDelete}
        onCancel={() => setPanel(null)}
      />
    </>
  );
}
```

- [ ] **Step 6: Run to verify they pass**

Run: `npm test -- src/ui/ConfirmDialog.test.tsx src/shell/ItemActions.test.tsx src/ui/ItemCard.test.tsx`
Expected: PASS (all).

- [ ] **Step 7: Commit**

```bash
git add shell/src/ui/ConfirmDialog.tsx shell/src/ui/ConfirmDialog.test.tsx shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx shell/src/ui/ItemCard.tsx shell/src/ui/ItemCard.test.tsx
git commit -m "feat(shell): add ConfirmDialog and ItemActions menu (edit/thumbnail/delete)"
```

---

### Task 8: Integrate `ItemActions` into catalog + detail, and extend E2E

**Files:**
- Modify: `shell/src/pages/CatalogPage.tsx`
- Modify: `shell/src/pages/CatalogPage.test.tsx`
- Modify: `shell/src/pages/ItemDetailPage.tsx`
- Modify: `shell/src/pages/ItemDetailPage.test.tsx`
- Modify: `shell/e2e/mocks.ts`
- Modify: `shell/e2e/catalog.spec.ts`

**Interfaces:**
- Consumes: `ItemActions`.
- Produces: `CatalogPage` renders `<ItemCard ... actions={<ItemActions item={item} />} />`. `ItemDetailPage` renders `<ItemActions item={item} />`. Both pages' tests mock `../shell/ItemActions` to keep them focused. The E2E gains a delete flow (create or use a listed item → Actions → Supprimer → confirm → item leaves the grid).

- [ ] **Step 1: Update the page tests to mock ItemActions (write the failing expectation first)**

In `shell/src/pages/CatalogPage.test.tsx` add near the top:

```tsx
import { vi } from "vitest";
vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));
```

Add an assertion to the "lists items" test:

```tsx
  expect(screen.getAllByText("actions").length).toBeGreaterThan(0);
```

In `shell/src/pages/ItemDetailPage.test.tsx` add near the top:

```tsx
import { vi } from "vitest";
vi.mock("../shell/ItemActions", () => ({ ItemActions: () => <span>actions</span> }));
```

Add to the "shows the item detail" test:

```tsx
  expect(screen.getByText("actions")).toBeInTheDocument();
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/pages/`
Expected: FAIL — "actions" not rendered yet.

- [ ] **Step 3: Render `ItemActions` in `shell/src/pages/CatalogPage.tsx`**

Add the import:

```tsx
import { ItemActions } from "../shell/ItemActions";
```

Change the grid's card render to pass the actions slot:

```tsx
          {query.data.items.map((item) => (
            <ItemCard
              key={item.pk}
              item={item}
              onOpen={onOpenItem}
              actions={<ItemActions item={item} />}
            />
          ))}
```

- [ ] **Step 4: Render `ItemActions` in `shell/src/pages/ItemDetailPage.tsx`**

Add the import and render it in the header next to the type badge (after `query.data` is resolved):

```tsx
import { ItemActions } from "../shell/ItemActions";
```

Inside the returned `<article>`, add after the type badge span:

```tsx
      <div className="w-fit">
        <ItemActions item={item} />
      </div>
```

- [ ] **Step 5: Run the full unit suite + build**

Run: `npm test` then `npm run build`.
Expected: all tests PASS; build succeeds.

- [ ] **Step 6: Extend the E2E mocks in `shell/e2e/mocks.ts`**

Add a delete route to `mockGeoNode`:

```ts
  await page.route("**/configs/by-item/**", async (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    await route.fulfill({ status: 204, body: "" });
  });
```

- [ ] **Step 7: Add the delete-flow E2E in `shell/e2e/catalog.spec.ts`**

```ts
test("delete an item from the catalog", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Alpha" })).toBeVisible();
  const card = page.locator("div", { hasText: "Alpha" }).last();
  await card.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: /supprimer/i }).first().click();
  await page.getByRole("dialog").getByRole("button", { name: "Supprimer" }).click();
  await expect(page.getByRole("heading", { name: "Alpha" })).toHaveCount(0);
});
```

(If the `page.locator` card scoping proves flaky, target the first card's Actions button directly: `page.getByRole("button", { name: "Actions" }).first()`.)

- [ ] **Step 8: Run the E2E**

Run: `npm run e2e`
Expected: all specs PASS. (If chromium is unavailable here, report the unit suite + build pass and the E2E files are in place.)

- [ ] **Step 9: Commit**

```bash
git add shell/src/pages/CatalogPage.tsx shell/src/pages/CatalogPage.test.tsx shell/src/pages/ItemDetailPage.tsx shell/src/pages/ItemDetailPage.test.tsx shell/e2e/mocks.ts shell/e2e/catalog.spec.ts
git commit -m "feat(shell): mount ItemActions on catalog + detail and cover delete in E2E"
```

---

## Self-Review

**Spec coverage (against SP-0b.2 §4.1/§4.2/§4.3 + the by-item decision + final-review notes):**
- by-item resolution (decision) → Tasks 1, 2 (`get_config_by_item`, `GET`/`DELETE /configs/by-item`). ✅
- `updateItem`/`uploadThumbnail`/`deleteItem(pk)` → Task 3. ✅
- `createConfigItem` null-guard (SP-0b.2-b final-review Important) → Task 3. ✅
- `useUpdateItem`/`useUploadThumbnail`/`useDeleteItem` with optimistic + rollback → Task 4. ✅
- `MetadataForm` (title/abstract/keywords) → Task 5. ✅
- `ThumbnailUpload` (image/* + ≤2MB) → Task 6. ✅
- `ConfirmDialog` + actions menu (Renommer/Modifier/Supprimer) → Task 7. ✅
- Mounted on `ItemCard` + `ItemDetailPage`; E2E delete flow → Task 8. ✅
- `deleteItem` treats 404 as success → Task 3. ✅
- Symmetric delete preserved (by-item route calls `delete_item` + `delete_config`) → Task 2. ✅

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `UpdatePatch` defined in Task 3 (`types.ts`), consumed by `itemClient.updateItem` (Task 3) and `useUpdateItem` (Task 4). `ConfigRead` reused by the by-item GET route (Task 2). `ItemActions({item, onDeleted})` (Task 7) consumed in Tasks 8. `ItemCard` `actions` slot defined in Task 7, used in Task 8. The hooks' `ItemPage`/`Item` generics match the `types.ts` shapes. ✅

## Notes for later sub-projects

- Dialog a11y polish (aria-modal, focus management, aria-haspopup) remains deferred from SP-0b.2-b — fold into a dedicated a11y pass or SP-0b.3.
- The actions menu is a minimal popover (no outside-click close / keyboard nav); acceptable for this phase, candidate for a shared `Menu` primitive later.
- SP-0b.3 (sharing/groups) will reuse `Dialog`/`ConfirmDialog` and the `ItemActions` slot.
