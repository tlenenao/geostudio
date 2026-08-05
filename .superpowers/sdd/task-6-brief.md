## Task 6: Shell — "Enregistrer la vue" button on `AppRuntimePage`

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx` (add local analytics-context state, a toolbar, the save button + dialog)
- Test: `shell/src/pages/AppRuntimePage.test.tsx` (append)

**Interfaces:**
- Consumes: `useCreateBookmark` (Task 4), `AnalyticsContextState` (`shell/src/builder/AnalyticsContext.tsx`), `Dialog` (`shell/src/ui/dialog.tsx`), `useAuth` (`shell/src/auth/useAuth.ts`, for `username` as the bookmark's `owner`).
- Produces: a button labeled "Enregistrer la vue", visible only when `query.data?.interactions === "auto"`; clicking it opens a dialog (label input, "Enregistrer"/"Annuler" buttons) that calls `useCreateBookmark().mutateAsync(...)` with the page's current `AnalyticsContextState`.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/pages/AppRuntimePage.test.tsx`. First extend the top-of-file mocks: add `vi.mock("../auth/useAuth", ...)` already exists (it mocks `username: "tanguy"`), and add a `createBookmarkItem` spy to the client passed into `renderRuntime`.

```typescript
test("the save-view button is absent when interactions is manual", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(manualDateFilterConfig) });
  await screen.findByLabelText("Date de début");
  expect(screen.queryByRole("button", { name: "Enregistrer la vue" })).not.toBeInTheDocument();
});

test("the save-view button is present when interactions is auto", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig) });
  expect(await screen.findByRole("button", { name: "Enregistrer la vue" })).toBeInTheDocument();
});

test("saving a view captures the current analytics context and posts a bookmark", async () => {
  const createBookmarkItem = vi.fn().mockResolvedValue({
    pk: "bm-1", resourceType: "bookmark", title: "Ma vue", abstract: "",
    owner: "tanguy", thumbnailUrl: null, date: "", configId: "cfg-bm-1", isPublished: false,
  });
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
    createBookmarkItem,
  });
  const fromInput = await screen.findByLabelText("Date de début");
  const toInput = await screen.findByLabelText("Date de fin");
  await userEvent.type(fromInput, "2026-01-01");
  await userEvent.type(toInput, "2026-02-01");

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer la vue" }));
  await userEvent.type(screen.getByLabelText("Nom de la vue"), "Ma vue");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(createBookmarkItem).toHaveBeenCalledWith({
      title: "Ma vue", owner: "tanguy", appId: "9", pageId: "page-1",
      timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
    }),
  );
});
```

Note: `dateFilterConfig` (already defined in this file, `interactions: "auto"` with a `dateRangeFilter` widget on `page-1`) is the config to use — reuse it, don't redefine it.

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: FAIL — no such button exists yet.

- [ ] **Step 3: Implement the button + dialog in `AppRuntimePage.tsx`**

Add imports:

```typescript
import { useState } from "react";
import { useAuth } from "../auth/useAuth";
import { useCreateBookmark } from "../api/hooks";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";
import { Input } from "../ui/input";
```

(merge the `useState` import into the existing `useEffect, useMemo, useRef, useState` import on line 10 if `useState` isn't already there — it is: line 10 already imports `useState`. Only add the new named imports listed above.)

Add local state to retain the latest analytics context (currently only captured in the debounce-timer closure) and the save-dialog state, inside the component body, right after the `handleAnalyticsContextChange` function:

```typescript
  const [currentAnalyticsContext, setCurrentAnalyticsContext] = useState<AnalyticsContextState>(initialAnalyticsContext);
  const [saveDialogOpen, setSaveDialogOpen] = useState(false);
  const [viewTitle, setViewTitle] = useState("");
  const { username } = useAuth();
  const createBookmark = useCreateBookmark();

  function handleAnalyticsContextChangeAndTrack(state: AnalyticsContextState) {
    setCurrentAnalyticsContext(state);
    handleAnalyticsContextChange(state);
  }

  async function saveView() {
    const title = viewTitle.trim();
    if (!title) return;
    try {
      await createBookmark.mutateAsync({
        title, owner: username ?? "",
        appId: pk, pageId: pageId ?? query.data?.pages?.[0]?.id ?? "",
        ...currentAnalyticsContext,
      });
      setSaveDialogOpen(false);
      setViewTitle("");
      createBookmark.reset();
    } catch {
      // surfaced via createBookmark.isError
    }
  }
```

Replace the `onAnalyticsContextChange={handleAnalyticsContextChange}` prop on `<AppRenderer>` with `onAnalyticsContextChange={handleAnalyticsContextChangeAndTrack}`.

Replace the render body (the current bare `<div className="h-full w-full">…</div>`) with a toolbar wrapper:

```typescript
  return (
    <div className="flex h-full w-full flex-col">
      {query.data.interactions === "auto" && (
        <div className="flex justify-end border-b border-slate-200 p-2">
          <Button size="sm" variant="outline" onClick={() => setSaveDialogOpen(true)}>
            Enregistrer la vue
          </Button>
        </div>
      )}
      <div className="min-h-0 flex-1">
        <AppRenderer
          config={query.data}
          mode="runtime"
          pageId={pageId}
          onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
          initialAnalyticsContext={initialAnalyticsContext}
          onAnalyticsContextChange={handleAnalyticsContextChangeAndTrack}
        />
      </div>
      <Dialog open={saveDialogOpen} onClose={() => setSaveDialogOpen(false)} title="Enregistrer la vue">
        <div className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Nom de la vue
            <Input aria-label="Nom de la vue" value={viewTitle} onChange={(e) => setViewTitle(e.target.value)} />
          </label>
          {createBookmark.isError && (
            <p role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setSaveDialogOpen(false)}>
              Annuler
            </Button>
            <Button type="button" size="sm" disabled={createBookmark.isPending || !viewTitle.trim()} onClick={saveView}>
              Enregistrer
            </Button>
          </div>
        </div>
      </Dialog>
    </div>
  );
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS (all tests in the file, including the 5 pre-existing ones — `handleAnalyticsContextChangeAndTrack` calls the original `handleAnalyticsContextChange` unchanged, so the debounced-URL-write behavior is untouched)

- [ ] **Step 5: Run the full shell unit suite**

Run: `cd shell && npm run test`
Expected: all green.

- [ ] **Step 6: Run the shell build (type-check)**

Run: `cd shell && npm run build`
Expected: succeeds — `tsc --noEmit` catches any type mismatch between `CreateBookmarkInput` and the `mutateAsync` call shape.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "feat(shell): enregistrer la vue button on AppRuntimePage (SP-14m)"
```

---

