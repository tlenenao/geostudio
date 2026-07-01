# Front Item Creation (SP-0b.2-b) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user create an App or Dashboard from the shell: a "Nouveau" button opens a dialog (type + title), which calls the Builder Service `POST /configs` through the `item-client`, then navigates to the new item's detail page.

**Architecture:** Extend the existing shell (`shell/`, delivered in SP-0b.1). Add `createConfigItem` to the `item-client` façade (posts a skeleton `BuilderConfig` to `{builderUrl}/configs` and maps the `ConfigRead` response to `Item`). Add a `useCreateItem` TanStack Query mutation. Add a minimal accessible `Dialog` primitive and a self-contained `NewItemButton` (button + form + mutation + navigation + owner from `useAuth`). Mount `NewItemButton` in the `AppLayout` header.

**Tech Stack:** React 19, TypeScript, Vite, Tailwind, @tanstack/react-query (mutations), react-router-dom, Vitest + Testing Library + MSW, Playwright. (No new dependencies.)

## Global Constraints

- Node floor 20; npm; run from `shell/`: `npm test`, `npm run build`, `npm run e2e`.
- No token in localStorage (unchanged); all network access goes through `item-client` only.
- External URLs come from injected `item-client` opts (`builderUrl`/`geonodeUrl`); no hard-coded URLs in components.
- Test output must stay clean (MSW `onUnhandledRequest: "error"` is configured).
- Builder Service contract (from SP-0a) consumed as-is: `POST /configs` body is `{ title: string, owner: string, config: BuilderConfig }`; response `ConfigRead` is `{ id: string, kind: string, itemId: string | null, version: number, config: {...} }`. The skeleton `BuilderConfig` is `{ version: 1, kind, theme: {}, dataSources: [], layout: { type: "grid", breakpoints: {}, items: [] }, messages: [] }`.
- `Item` shape (from SP-0b.1) stays stable; only the `ItemClient` interface gains a method.
- Created item kind is exactly `"app"` or `"dashboard"`.

---

### Task 1: `createConfigItem` on the item-client

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Test: `shell/src/api/itemClient.test.ts` (add cases)

**Interfaces:**
- Consumes: existing `createItemClient({ geonodeUrl, builderUrl, getToken })`, `Item`, `ResourceType`.
- Produces:
  - `type CreateKind = "app" | "dashboard"` in `types.ts`.
  - `ItemClient.createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item>` — `POST {builderUrl}/configs` with body `{ title, owner, config: <skeleton> }` and Bearer when a token exists; maps `ConfigRead` → `Item` (`pk = String(itemId ?? "")`, `resourceType = kind`, `configId = String(id)`, `abstract = ""`, `thumbnailUrl = null`, `date = ""`). Throws `Error` with the status on non-2xx.
  - MSW handler `POST https://builder.test/configs` echoing the posted config and returning `{ id: "cfg-1", kind, itemId: "99", version: 1, config }`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts`:

```ts
test("createConfigItem posts a skeleton config and maps to Item", async () => {
  const item = await makeClient().createConfigItem({
    kind: "dashboard",
    title: "My Dash",
    owner: "alice",
  });
  expect(item).toMatchObject({
    pk: "99",
    resourceType: "dashboard",
    title: "My Dash",
    owner: "alice",
    configId: "cfg-1",
    thumbnailUrl: null,
  });
});

test("createConfigItem sends title, owner and an empty grid layout", async () => {
  let body: any = null;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({
        id: "c",
        kind: body.config.kind,
        itemId: "1",
        version: 1,
        config: body.config,
      });
    }),
  );
  await makeClient("abc").createConfigItem({ kind: "app", title: "T", owner: "o" });
  expect(body.title).toBe("T");
  expect(body.owner).toBe("o");
  expect(body.config.kind).toBe("app");
  expect(body.config.layout).toEqual({ type: "grid", breakpoints: {}, items: [] });
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: FAIL — `createConfigItem` is not a function / no MSW handler for POST (unhandled-request error).

- [ ] **Step 3: Add `CreateKind` + method signature to `shell/src/api/types.ts`**

Add the type and extend the interface:

```ts
export type CreateKind = "app" | "dashboard";
```

In `interface ItemClient`, add:

```ts
  createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item>;
```

- [ ] **Step 4: Implement in `shell/src/api/itemClient.ts`**

Update the destructure to include `builderUrl`:

```ts
  const { geonodeUrl, builderUrl, getToken } = opts;
```

Add the method inside the returned object (alongside `listItems`/`getItem`/`getMe`):

```ts
    async createConfigItem(input): Promise<Item> {
      const config = {
        version: 1,
        kind: input.kind,
        theme: {},
        dataSources: [],
        layout: { type: "grid", breakpoints: {}, items: [] },
        messages: [],
      };
      const token = getToken();
      const res = await fetch(`${builderUrl}/configs`, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ title: input.title, owner: input.owner, config }),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} /configs`);
      }
      const data = (await res.json()) as {
        id: string | number;
        kind: string;
        itemId: string | null;
      };
      return {
        pk: String(data.itemId ?? ""),
        resourceType: data.kind as ResourceType,
        title: input.title,
        abstract: "",
        owner: input.owner,
        thumbnailUrl: null,
        date: "",
        configId: String(data.id),
      };
    },
```

Add the `CreateKind` import to the type import line at the top of the file:

```ts
import type { CreateKind, Item, ItemClient, ItemPage, ListItemsParams, Me, ResourceType } from "./types";
```

(If TypeScript flags the untyped `input` parameter, type it as `{ kind: CreateKind; title: string; owner: string }`.)

- [ ] **Step 5: Add the MSW handler in `shell/src/test/msw/handlers.ts`**

Add to the `handlers` array:

```ts
  http.post("https://builder.test/configs", async ({ request }) => {
    const body = (await request.json()) as { config: { kind: string } };
    return HttpResponse.json({
      id: "cfg-1",
      kind: body.config.kind,
      itemId: "99",
      version: 1,
      config: body.config,
    });
  }),
```

- [ ] **Step 6: Run to verify they pass**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: PASS (existing + 2 new).

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/test/msw/handlers.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add item-client.createConfigItem (POST /configs)"
```

---

### Task 2: `useCreateItem` mutation hook

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx` (add a case)

**Interfaces:**
- Consumes: `useItemClient`, `CreateKind` from `../api`, `useMutation`/`useQueryClient`.
- Produces: `useCreateItem()` → TanStack `UseMutationResult<Item, Error, { kind: CreateKind; title: string; owner: string }>`; on success invalidates `["items"]`.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/api/hooks.test.tsx` (the `wrapper` already provides QueryClient + ItemClientProvider; add `act` to the existing testing-library import):

```tsx
import { act } from "@testing-library/react";
import { useCreateItem } from "./hooks";

test("useCreateItem creates an item and returns it", async () => {
  const { result } = renderHook(() => useCreateItem(), { wrapper });
  await act(async () => {
    await result.current.mutateAsync({ kind: "app", title: "X", owner: "alice" });
  });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.pk).toBe("99");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: FAIL — `useCreateItem` is not exported.

- [ ] **Step 3: Implement in `shell/src/api/hooks.ts`**

Replace the import line:

```ts
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
```

Add `CreateKind` to the type import:

```ts
import type { CreateKind, ListItemsParams } from "./types";
```

Add the hook:

```ts
export function useCreateItem() {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: { kind: CreateKind; title: string; owner: string }) =>
      client.createConfigItem(input),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["items"] });
    },
  });
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: PASS (existing + new).

- [ ] **Step 5: Commit**

```bash
git add shell/src/api/hooks.ts shell/src/api/hooks.test.tsx
git commit -m "feat(shell): add useCreateItem mutation hook"
```

---

### Task 3: Minimal `Dialog` primitive

**Files:**
- Create: `shell/src/ui/dialog.tsx`
- Test: `shell/src/ui/dialog.test.tsx`

**Interfaces:**
- Consumes: nothing (React only).
- Produces: `Dialog({ open, onClose, title, children }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode })` — renders nothing when `!open`; when open renders an overlay (click → `onClose`) and a panel with `role="dialog"` + `aria-label={title}` + a visible `<h2>` title; pressing Escape calls `onClose`.

- [ ] **Step 1: Write the failing test**

Create `shell/src/ui/dialog.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import { Dialog } from "./dialog";

test("renders nothing when closed", () => {
  render(
    <Dialog open={false} onClose={() => {}} title="T">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
});

test("renders content when open and closes on Escape", async () => {
  const onClose = vi.fn();
  render(
    <Dialog open onClose={onClose} title="Titre">
      <p>body</p>
    </Dialog>,
  );
  expect(screen.getByRole("dialog", { name: "Titre" })).toBeInTheDocument();
  expect(screen.getByText("body")).toBeInTheDocument();
  await userEvent.keyboard("{Escape}");
  expect(onClose).toHaveBeenCalledTimes(1);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/ui/dialog.test.tsx`
Expected: FAIL — cannot resolve `./dialog`.

- [ ] **Step 3: Create `shell/src/ui/dialog.tsx`**

```tsx
import { useEffect } from "react";

export function Dialog({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: React.ReactNode;
}) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center">
      <div className="absolute inset-0 bg-black/40" aria-hidden="true" onClick={onClose} />
      <div
        role="dialog"
        aria-label={title}
        className="relative z-10 w-full max-w-md rounded-lg bg-white p-6 shadow-lg"
      >
        <h2 className="mb-4 text-lg font-semibold">{title}</h2>
        {children}
      </div>
    </div>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/ui/dialog.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/ui/dialog.tsx shell/src/ui/dialog.test.tsx
git commit -m "feat(shell): add minimal accessible Dialog primitive"
```

---

### Task 4: `NewItemButton` (create dialog + flow)

**Files:**
- Create: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx`

**Interfaces:**
- Consumes: `useCreateItem` (`../api/hooks`), `useAuth` (`../auth/useAuth`), `useNavigate` (react-router-dom), `Dialog`/`Button`/`Input` (`../ui/*`).
- Produces: `NewItemButton()` — a "Nouveau" button opening a `Dialog` titled "Nouvel élément" with a Type `<select>` (App/Dashboard, `aria-label="Type"`), a Titre `<Input>` (`aria-label="Titre"`), Annuler/Créer buttons. On submit (title non-empty) it calls `useCreateItem().mutateAsync({ kind, title, owner: username ?? "" })`, closes the dialog, and `navigate(\`/items/\${item.pk}\`)`. Shows `role="alert"` on mutation error; the Créer button is disabled while pending.

- [ ] **Step 1: Write the failing test**

Create `shell/src/shell/NewItemButton.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { NewItemButton } from "./NewItemButton";

vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
    username: "alice",
    getAccessToken: () => "t",
    signIn: vi.fn(),
    signOut: vi.fn(),
    error: null,
  }),
}));

function DetailProbe() {
  const { pk } = useParams();
  return <div>detail-{pk}</div>;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          {children}
          <Routes>
            <Route path="/items/:pk" element={<DetailProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("creates an item and navigates to its detail", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.getByRole("dialog", { name: /nouvel/i })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Titre"), "My App");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("detail-99")).toBeInTheDocument();
});

test("does not submit an empty title", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(screen.queryByText(/^detail-/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/shell/NewItemButton.test.tsx`
Expected: FAIL — cannot resolve `./NewItemButton`.

- [ ] **Step 3: Create `shell/src/shell/NewItemButton.tsx`**

```tsx
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useCreateItem } from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { Button } from "../ui/button";
import { Input } from "../ui/input";
import { Dialog } from "../ui/dialog";

export function NewItemButton() {
  const [open, setOpen] = useState(false);
  const [kind, setKind] = useState<"app" | "dashboard">("app");
  const [title, setTitle] = useState("");
  const { username } = useAuth();
  const navigate = useNavigate();
  const create = useCreateItem();

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const clean = title.trim();
    if (!clean) return;
    const item = await create.mutateAsync({ kind, title: clean, owner: username ?? "" });
    setOpen(false);
    setTitle("");
    navigate(`/items/${item.pk}`);
  }

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Nouveau
      </Button>
      <Dialog open={open} onClose={() => setOpen(false)} title="Nouvel élément">
        <form onSubmit={submit} className="flex flex-col gap-3">
          <label className="flex flex-col gap-1 text-sm">
            Type
            <select
              aria-label="Type"
              className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
              value={kind}
              onChange={(e) => setKind(e.target.value as "app" | "dashboard")}
            >
              <option value="app">App</option>
              <option value="dashboard">Dashboard</option>
            </select>
          </label>
          <label className="flex flex-col gap-1 text-sm">
            Titre
            <Input
              aria-label="Titre"
              value={title}
              onChange={(e) => setTitle(e.target.value)}
            />
          </label>
          {create.isError && (
            <p role="alert" className="text-sm text-red-600">
              Échec de la création.
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button type="button" variant="outline" size="sm" onClick={() => setOpen(false)}>
              Annuler
            </Button>
            <Button type="submit" size="sm" disabled={create.isPending}>
              Créer
            </Button>
          </div>
        </form>
      </Dialog>
    </>
  );
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/shell/NewItemButton.test.tsx`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx
git commit -m "feat(shell): add NewItemButton create dialog + flow"
```

---

### Task 5: Mount `NewItemButton` in the AppLayout header + E2E

**Files:**
- Modify: `shell/src/shell/AppLayout.tsx`
- Modify: `shell/src/shell/AppLayout.test.tsx`
- Modify: `shell/e2e/mocks.ts`
- Modify: `shell/e2e/catalog.spec.ts`

**Interfaces:**
- Consumes: `NewItemButton`.
- Produces: `AppLayout` renders `<NewItemButton />` in the header (left of the username). `AppLayout.test` mocks `./NewItemButton` so the layout test stays focused. The E2E gains a "create App → lands on detail" flow with route mocks for `POST **/configs` and the new item's GeoNode detail.

- [ ] **Step 1: Update `AppLayout.test.tsx` to mock NewItemButton (write the new expectation first)**

In `shell/src/shell/AppLayout.test.tsx`, add a mock next to the existing `vi.mock("../auth/useAuth", ...)`:

```tsx
vi.mock("./NewItemButton", () => ({
  NewItemButton: () => <button>Nouveau</button>,
}));
```

Add an assertion to the existing layout test (after the brand/username checks):

```tsx
  expect(screen.getByRole("button", { name: "Nouveau" })).toBeInTheDocument();
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/shell/AppLayout.test.tsx`
Expected: FAIL — no "Nouveau" button in the layout yet.

- [ ] **Step 3: Render `NewItemButton` in `shell/src/shell/AppLayout.tsx`**

Add the import:

```tsx
import { NewItemButton } from "./NewItemButton";
```

In the header's right-hand cluster, add `<NewItemButton />` before the username span:

```tsx
        <div className="flex items-center gap-3 text-sm">
          <NewItemButton />
          <span>{username}</span>
          <Button size="sm" variant="outline" onClick={signOut}>
            Déconnexion
          </Button>
        </div>
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/shell/AppLayout.test.tsx`
Expected: PASS.

- [ ] **Step 5: Run the full unit suite + build**

Run: `npm test` then `npm run build`.
Expected: all tests PASS; build succeeds.

- [ ] **Step 6: Extend the E2E mocks in `shell/e2e/mocks.ts`**

Add inside `mockGeoNode` (or as additional routes in the same function) handlers for the create POST and the new item's detail:

```ts
  await page.route("**/configs", async (route) => {
    if (route.request().method() !== "POST") return route.fallback();
    await route.fulfill({
      json: { id: "cfg-9", kind: "app", itemId: "9", version: 1, config: {} },
    });
  });
  await page.route("**/api/v2/resources/9", async (route) => {
    await route.fulfill({
      json: {
        resource: { pk: "9", resource_type: "app", title: "Créée", abstract: "",
          owner: { username: "mockuser" }, thumbnail_url: null, date: "2026-01-01" },
      },
    });
  });
```

- [ ] **Step 7: Add the create-flow E2E in `shell/e2e/catalog.spec.ts`**

```ts
test("create an App → lands on its detail page", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByLabel("Titre").fill("Créée");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/items\/9$/);
  await expect(page.getByRole("heading", { name: "Créée" })).toBeVisible();
});
```

- [ ] **Step 8: Run the E2E**

Run: `npm run e2e`
Expected: both specs PASS. (If chromium cannot run in this environment, report that the unit suite + build pass and the E2E files are in place.)

- [ ] **Step 9: Commit**

```bash
git add shell/src/shell/AppLayout.tsx shell/src/shell/AppLayout.test.tsx shell/e2e/mocks.ts shell/e2e/catalog.spec.ts
git commit -m "feat(shell): mount NewItemButton in header and cover create flow in E2E"
```

---

## Self-Review

**Spec coverage (against SP-0b.2 §4 — front création / §8 phase 0b.2-b):**
- `createConfigItem` (POST /configs, skeleton config, map to Item) → Task 1. ✅
- `useCreateItem` (invalidate `["items"]`) → Task 2. ✅
- `CreateItemDialog` (kind select + title) → realized as `NewItemButton` (button + dialog) using the new `Dialog` primitive → Tasks 3, 4. ✅
- "Nouveau" button + navigation to `/items/{pk}` → Tasks 4, 5. ✅
- E2E create flow → Task 5. ✅
- Out of phase (0b.2-c): rename/edit/thumbnail/delete UI — correctly excluded.

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `CreateKind = "app" | "dashboard"` defined in Task 1, reused in `ItemClient.createConfigItem` (Task 1), `useCreateItem` (Task 2), and `NewItemButton`'s local `kind` state (Task 4). `createConfigItem` returns `Item` with `pk` used by `NewItemButton`'s `navigate(\`/items/\${item.pk}\`)` and asserted as `"99"`/`"9"` in tests. The `useAuth` return shape includes `error: null` (matches the SP-0b.1 `AuthState` after its final-review fix). ✅

## Notes for SP-0b.2-c

- Reuse the `Dialog` primitive for `ConfirmDialog` and the metadata/thumbnail dialogs.
- `deleteItem(configId)` → `DELETE /configs/{configId}` (delivered in 0b.2-a); handle a `500` from a GeoNode-side 404 as "already deleted" per the 0b.2-a final-review note in the spec.
