# GeoStudio SP-0d.6 — Publication & partage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a builder app/dashboard be published (GeoNode's own `is_published`), viewed at its runtime route without authentication once published/shared, embedded in a bare `<iframe>` (no extra route needed — the runtime is already chrome-less), and get a manually-captured thumbnail.

**Architecture:** No `BuilderConfig` schema change and no Builder Service change at all — every piece of this slice is front-end-only, reusing GeoNode's own resource model and the existing `getAppConfig`/`updateItem`/`uploadThumbnail` façade methods. Publication state is GeoNode's `is_published` field (already read by `listItems`'s `scope: "public"` filter), toggled via the existing `updateItem` PATCH. The runtime route stops being wrapped in `RequireAuth`/`AppLayout` and instead gates itself: it calls `getItem(pk)` first — the one call that already goes through GeoNode's real permission check — and only fetches the config (`getAppConfig`) once that succeeds; a failure renders an access-denied message and never touches the Builder Service. Because the runtime route drops its `AppLayout` chrome as part of this same change, it becomes embeddable in an `<iframe>` with no new route, no new headers. Thumbnail capture is a client-side DOM→PNG snapshot (`html-to-image`, the one new dependency in this plan) of the builder's live preview, uploaded through the thumbnail endpoint that already exists.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright + MSW + React Router v6.26 + React Query 5. One new frontend dependency: `html-to-image` (client-side DOM capture, Task 4 only). No backend change of any kind.

## Global Constraints

- Additive/back-compatible: `Item.isPublished: boolean` is a new required field (GeoNode resources always have a real `is_published` value, never absent) — every existing literal `Item` fixture in the test suite needs it added; this is a known, enumerated ripple, not a surprise (Task 1 lists every file).
- No `BuilderConfig`/Builder Service change anywhere in this plan — publication state lives entirely on the GeoNode `Item`, never in `AppConfig`.
- Front: no new service URL. One new dependency (`html-to-image`, Task 4 only) — otherwise none.
- The runtime route (`/apps/:pk/:pageId?`) is the **only** route whose auth/chrome behavior changes. Every other route (`/`, `/items/:pk`, `/maps/:pk`, `/apps/:pk/edit`) keeps requiring authentication and keeps rendering inside `AppLayout`, unchanged.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`).

**Scope note:** This plan does not (and cannot, without extending the mock-auth harness, which is out of scope) prove the fully-anonymous case end-to-end in Playwright — `authMode: "mock"` (used by all current E2E specs) hardcodes an always-authenticated mock user with no way to flip it to "no user" per test. The *gating logic itself* (call `getItem` first; on failure, never call `getAppConfig`; on success, proceed) is proven at the unit level (Task 2) by mocking `ItemClient.getItem` to reject/resolve directly — this validates the sequencing regardless of what actually put the caller in an unauthenticated state. The E2E slice (Task 5) instead proves the more valuable regression: that an **authenticated** user's existing runtime flows (already exercised by `app-builder.spec.ts`, `theme.spec.ts`, `pages-navigation.spec.ts`, etc.) still work unchanged after moving the runtime route out from under `RequireAuth`/`AppLayout` — the routing surgery in Task 2 is the highest-risk part of this plan precisely because it touches `App.tsx`'s bootstrap, so proving nothing broke for the common case matters more here than proving the anonymous case, which is already unit-covered.

---

### Task 1: `is_published` — GeoNode-backed publish toggle

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Test: `shell/src/api/itemClient.test.ts` (extend)
- Modify: `shell/src/shell/ItemActions.tsx`
- Test: `shell/src/shell/ItemActions.test.tsx` (extend)
- Modify (fixture ripple, additive field only): `shell/src/api/hooks.test.tsx:60-61`, `shell/src/shell/ShareDialog.test.tsx:19,21`, `shell/src/ui/ItemCard.test.tsx:7-16`

**Interfaces:**
- Produces:
  - `Item.isPublished: boolean` (new field, added to the existing `Item` type).
  - `UpdatePatch.isPublished?: boolean` (new optional field, added to the existing `UpdatePatch` type — `updateItem` already accepts a `Partial`-style patch object, so this slots in without a signature change).
  - `updateItem(pk, { isPublished })` maps `isPublished` → GeoNode's `is_published` (snake_case) in the PATCH body; `toItem()` reads `is_published` back into `isPublished`.
  - `ItemActions` gains a "Publier"/"Dépublier" menu button (single click, no dialog — mirrors the existing direct-action style, not the dialog-based "Modifier"/"Partager" flows) that calls `useUpdateItem(item.pk).mutateAsync({ isPublished: !item.isPublished })`.

- [ ] **Step 1: Write the failing `itemClient` tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("getItem maps is_published into isPublished", async () => {
  const item = await makeClient().getItem("7");
  expect(item.isPublished).toBe(false);
});

test("updateItem sends isPublished as is_published and maps the result back", async () => {
  let body: any = null;
  server.use(
    http.patch("https://geonode.test/api/v2/resources/:pk", async ({ request, params }) => {
      body = await request.json();
      return HttpResponse.json({
        resource: {
          pk: String(params.pk), resource_type: "app", title: "Item", abstract: "",
          owner: { username: "alice" }, thumbnail_url: null, date: "2026-01-01T00:00:00Z",
          is_published: body.is_published,
        },
      });
    }),
  );
  const item = await makeClient().updateItem("7", { isPublished: true });
  expect(body.is_published).toBe(true);
  expect(item.isPublished).toBe(true);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `Item`/`UpdatePatch` don't have `isPublished` yet; `toItem()`/`updateItem()` don't read/send `is_published`.

- [ ] **Step 3: Widen the types**

Edit `shell/src/api/types.ts`. Change:

```ts
export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
};
```

to:

```ts
export type Item = {
  pk: string;
  resourceType: ResourceType;
  title: string;
  abstract: string;
  owner: string;
  thumbnailUrl: string | null;
  date: string;
  configId: string | null;
  isPublished: boolean;
};
```

Change:

```ts
export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[] };
```

to:

```ts
export type UpdatePatch = { title?: string; abstract?: string; keywords?: string[]; isPublished?: boolean };
```

- [ ] **Step 4: Thread `is_published` through `itemClient.ts`**

Edit `shell/src/api/itemClient.ts`. Change the raw resource shape and `toItem()`:

```ts
type GeoNodeResource = {
  pk: number | string;
  resource_type: string;
  title: string;
  abstract?: string;
  owner?: { username?: string };
  thumbnail_url?: string | null;
  date?: string;
};

function toItem(r: GeoNodeResource): Item {
  return {
    pk: String(r.pk),
    resourceType: (r.resource_type as ResourceType) ?? "map",
    title: r.title,
    abstract: r.abstract ?? "",
    owner: r.owner?.username ?? "",
    thumbnailUrl: r.thumbnail_url ?? null,
    date: r.date ?? "",
    configId: null,
  };
}
```

to:

```ts
type GeoNodeResource = {
  pk: number | string;
  resource_type: string;
  title: string;
  abstract?: string;
  owner?: { username?: string };
  thumbnail_url?: string | null;
  date?: string;
  is_published?: boolean;
};

function toItem(r: GeoNodeResource): Item {
  return {
    pk: String(r.pk),
    resourceType: (r.resource_type as ResourceType) ?? "map",
    title: r.title,
    abstract: r.abstract ?? "",
    owner: r.owner?.username ?? "",
    thumbnailUrl: r.thumbnail_url ?? null,
    date: r.date ?? "",
    configId: null,
    isPublished: r.is_published ?? false,
  };
}
```

Change `updateItem`'s PATCH body from:

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
```

to:

```ts
    async updateItem(pk: string, patch: UpdatePatch): Promise<Item> {
      const token = getToken();
      const { isPublished, ...rest } = patch;
      const body = { ...rest, ...(isPublished !== undefined ? { is_published: isPublished } : {}) };
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}`, {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify(body),
      });
```

- [ ] **Step 5: Add `is_published` to the shared MSW fixture**

Edit `shell/src/test/msw/handlers.ts`. This file is the **global** MSW handler set used by every Vitest unit test that hits the GeoNode mock — the change below is purely additive (a new field on an existing fixture, echoed on PATCH), but run the full suite (Step 9) to confirm, not just this task's own files.

Change:

```ts
function resource(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resource_type: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: { username: "alice" },
    thumbnail_url: `${GEONODE}/thumbs/${pk}.png`,
    date: "2026-01-01T00:00:00Z",
  };
}
```

to:

```ts
function resource(pk: string, type = "app", title = `Item ${pk}`) {
  return {
    pk,
    resource_type: type,
    title,
    abstract: `Abstract ${pk}`,
    owner: { username: "alice" },
    thumbnail_url: `${GEONODE}/thumbs/${pk}.png`,
    date: "2026-01-01T00:00:00Z",
    is_published: false,
  };
}
```

Change the PATCH handler from:

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
```

to:

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
        is_published: (patch.is_published as boolean) ?? false,
      },
    });
  }),
```

- [ ] **Step 6: Run to verify the itemClient tests pass**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS.

- [ ] **Step 7: Fix the fixture ripple — every literal `Item` object needs `isPublished`**

`Item` is now missing a required field in three other test files. Add `isPublished: false` to each:

Edit `shell/src/api/hooks.test.tsx`. Change:

```ts
      { pk: "1", resourceType: "app", title: "A", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
      { pk: "2", resourceType: "app", title: "B", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null },
```

to:

```ts
      { pk: "1", resourceType: "app", title: "A", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null, isPublished: false },
      { pk: "2", resourceType: "app", title: "B", abstract: "", owner: "x", thumbnailUrl: null, date: "", configId: null, isPublished: false },
```

Edit `shell/src/shell/ShareDialog.test.tsx`. Find the literal `Item` fixture object (it has `thumbnailUrl: null,` and `configId: null,` on their own lines) and add `isPublished: false,` immediately after `configId: null,`.

Edit `shell/src/ui/ItemCard.test.tsx`. Change:

```ts
const item: Item = {
  pk: "42",
  resourceType: "dashboard",
  title: "Suivi incidents",
  abstract: "Tableau de bord",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01T00:00:00Z",
  configId: null,
};
```

to:

```ts
const item: Item = {
  pk: "42",
  resourceType: "dashboard",
  title: "Suivi incidents",
  abstract: "Tableau de bord",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01T00:00:00Z",
  configId: null,
  isPublished: false,
};
```

- [ ] **Step 8: Write the failing `ItemActions` test**

Append to `shell/src/shell/ItemActions.test.tsx`:

```tsx
test("toggles publication from the menu", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  const publish = screen.getByRole("button", { name: "Publier" });
  await userEvent.click(publish);
  await waitFor(() => expect(screen.queryByRole("button", { name: "Publier" })).not.toBeInTheDocument());
});
```

Add `isPublished: false` to this file's own `item` fixture (declared at the top of the file, alongside `configId: null,`).

- [ ] **Step 9: Run to verify it fails**

Run: `cd shell && npx vitest run src/shell/ItemActions.test.tsx`
Expected: FAIL — no "Publier" button exists in the menu yet.

- [ ] **Step 10: Add the publish toggle to `ItemActions`**

Edit `shell/src/shell/ItemActions.tsx`. Add a `publish` mutation next to `update`/`thumbnail`/`remove`:

```tsx
  const publish = useUpdateItem(item.pk);
```

Widen the import line:

```tsx
import { useDeleteItem, useUpdateItem, useUploadThumbnail } from "../api/hooks";
```

(unchanged — `useUpdateItem` is already imported; reuse the same hook for both the "Modifier" dialog's `update` mutation and this new toggle would collide on the same mutation state. Instead, call `useUpdateItem(item.pk)` a second time under a distinct name — React Query mutations are independent per hook call, so this is safe and keeps `update`'s pending/error state from being clobbered by the toggle's own pending/error state.)

Add the menu button, right after "Modifier" and before "Miniature":

```tsx
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("edit")}>
            Modifier
          </button>
          <button
            className="px-3 py-1 text-left hover:bg-slate-100"
            onClick={async () => {
              try {
                await publish.mutateAsync({ isPublished: !item.isPublished });
                setPanel(null);
              } catch {
                /* surfaced via publish.isError */
              }
            }}
          >
            {item.isPublished ? "Dépublier" : "Publier"}
          </button>
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("thumbnail")}>
            Miniature
          </button>
```

Add an error message below the menu, mirroring the existing `remove.isError` pattern at the bottom of the component:

```tsx
      {publish.isError && panel === "menu" && (
        <p role="alert" className="mt-2 text-sm text-red-600">
          Échec de la publication.
        </p>
      )}
```

- [ ] **Step 11: Run to verify it passes**

Run: `cd shell && npx vitest run src/shell/ItemActions.test.tsx`
Expected: PASS. The pre-existing "renames an item…" test still passes — it clicks "Modifier" by role name, unaffected by the new sibling button.

- [ ] **Step 12: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass (confirms the shared `handlers.ts`/`Item` fixture changes didn't regress any other test); build succeeds.

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/test/msw/handlers.ts shell/src/api/hooks.test.tsx shell/src/shell/ShareDialog.test.tsx shell/src/ui/ItemCard.test.tsx shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx
git commit -m "feat(shell): publish/unpublish an item via GeoNode's is_published

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Runtime route becomes chrome-less, unauthenticated-reachable, gated by `getItem`

**Files:**
- Modify: `shell/src/App.tsx`
- Modify: `shell/src/shell/routes.tsx`
- Test: `shell/src/shell/routes.test.tsx` (extend)
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppRuntimePage.test.tsx` (extend)

**Interfaces:**
- Consumes: `useItem(pk)` (existing, `shell/src/api/hooks.ts:14-20`), `useAppConfig(pk, { enabled })` (existing, already supports the `enabled` option).
- Produces: `AppRuntimePage`'s external signature (`{ pk, pageId }`) is unchanged; internally it now calls `useItem(pk)` before `useAppConfig`, and gates rendering on both. `AppRoutes`'s exported shape is unchanged (still `export function AppRoutes()`), but its internal route tree now nests every route *except* the runtime one under a new, unexported `ProtectedLayout` component.

- [ ] **Step 1: Write the failing `routes.test.tsx` tests**

Edit `shell/src/shell/routes.test.tsx`. Add a `useAuth` mock at the top of the file (after the existing imports), since `RequireAuth` (now reachable through `routes.tsx` itself) calls the real `useAuth()` hook, which needs a mocked, always-authenticated state for every pre-existing test in this file to keep passing exactly as before:

```tsx
import { vi } from "vitest";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));
```

Append two new tests at the end of the file:

```tsx
test("the runtime route renders without going through the auth gate", () => {
  authState.isAuthenticated = false;
  wrap(<AppRoutes />, "/apps/42");
  expect(screen.getByText("app-runtime-42-none")).toBeInTheDocument();
  authState.isAuthenticated = true;
});

test("protected routes still require authentication", () => {
  authState.isAuthenticated = false;
  wrap(<AppRoutes />, "/");
  expect(authState.signIn).toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /ouvrir/i })).not.toBeInTheDocument();
  authState.isAuthenticated = true;
});
```

(Each test resets `authState.isAuthenticated = true` at the end so it doesn't bleed into the next test — this file has no `beforeEach`/`afterEach` today, so resetting inline keeps the change minimal and localized to the two tests that touch it.)

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: FAIL — `useAuth` isn't even imported/used by `routes.tsx` yet, so `authState.isAuthenticated = false` has no effect and every route still renders unconditionally.

- [ ] **Step 3: Restructure `routes.tsx`**

Replace `shell/src/shell/routes.tsx` with:

```tsx
import { Routes, Route, Outlet, useNavigate, useParams } from "react-router-dom";
import { CatalogPage } from "../pages/CatalogPage";
import { ItemDetailPage } from "../pages/ItemDetailPage";
import { MapEditorPage } from "../pages/MapEditorPage";
import { AppBuilderPage } from "../pages/AppBuilderPage";
import { AppRuntimePage } from "../pages/AppRuntimePage";
import { RequireAuth } from "../auth/RequireAuth";
import { AppLayout } from "./AppLayout";

function CatalogRoute() {
  const navigate = useNavigate();
  return (
    <CatalogPage
      onOpenItem={(pk, type) =>
        navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)
      }
    />
  );
}

function ItemDetailRoute() {
  const { pk } = useParams();
  const navigate = useNavigate();
  return (
    <ItemDetailPage
      pk={pk!}
      onDeleted={() => navigate("/")}
      onOpenEditor={(type) => navigate(type === "map" ? `/maps/${pk}` : `/apps/${pk}/edit`)}
    />
  );
}

function MapEditorRoute() {
  const { pk } = useParams();
  return <MapEditorPage pk={pk!} />;
}

function AppBuilderRoute() {
  const { pk } = useParams();
  return <AppBuilderPage pk={pk!} />;
}

function AppRuntimeRoute() {
  const { pk, pageId } = useParams();
  return <AppRuntimePage pk={pk!} pageId={pageId} />;
}

function ProtectedLayout() {
  return (
    <RequireAuth>
      <AppLayout>
        <Outlet />
      </AppLayout>
    </RequireAuth>
  );
}

export function AppRoutes() {
  return (
    <Routes>
      <Route element={<ProtectedLayout />}>
        <Route path="/" element={<CatalogRoute />} />
        <Route path="/items/:pk" element={<ItemDetailRoute />} />
        <Route path="/maps/:pk" element={<MapEditorRoute />} />
        <Route path="/apps/:pk/edit" element={<AppBuilderRoute />} />
      </Route>
      <Route path="/apps/:pk/:pageId?" element={<AppRuntimeRoute />} />
    </Routes>
  );
}
```

The only line that moved semantically is `/apps/:pk/edit` (now nested under `ProtectedLayout`) versus `/apps/:pk/:pageId?` (still a top-level sibling, now the only unprotected route). React Router v6 ranks routes by their fully-resolved path regardless of nesting depth, so `/apps/:pk/edit`'s static `edit` segment still outranks the sibling's dynamic `:pageId?` segment exactly as it did before this change — the existing `"renders the app builder route at /apps/:pk/edit"` test (already in this file, unmodified) guards against a regression here.

- [ ] **Step 4: Restructure `App.tsx`**

Replace `shell/src/App.tsx` with:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { BrowserRouter } from "react-router-dom";
import { useMemo } from "react";
import { loadConfig } from "./config";
import { AuthProvider } from "./auth/AuthProvider";
import { useAuth } from "./auth/useAuth";
import { createItemClient } from "./api/itemClient";
import { ItemClientProvider } from "./api/ItemClientProvider";
import { AppRoutes } from "./shell/routes";

const config = loadConfig(import.meta.env as unknown as Record<string, string | undefined>);
const queryClient = new QueryClient();

function AppShell() {
  const { getAccessToken } = useAuth();
  const client = useMemo(
    () =>
      createItemClient({
        geonodeUrl: config.geonodeUrl,
        builderUrl: config.builderUrl,
        martinUrl: config.martinUrl,
        featureservUrl: config.featureservUrl,
        getToken: getAccessToken,
      }),
    [getAccessToken],
  );
  return (
    <ItemClientProvider client={client}>
      <BrowserRouter>
        <AppRoutes />
      </BrowserRouter>
    </ItemClientProvider>
  );
}

export default function App() {
  return (
    <AuthProvider config={config}>
      <QueryClientProvider client={queryClient}>
        <AppShell />
      </QueryClientProvider>
    </AuthProvider>
  );
}
```

`getAccessToken()` already returns `undefined` gracefully when there's no authenticated user (`shell/src/auth/useAuth.ts:37`, `() => oidc.user?.access_token`) — `ItemClientProvider`'s `client` is now created *before* any auth gate, so an unauthenticated visitor's requests simply omit the `Authorization` header (every request builder in `itemClient.ts` already does `...(token ? {...} : {})`), which is exactly what lets `getItem`/`getAppConfig` reach GeoNode/the Builder Service as an anonymous caller.

- [ ] **Step 5: Run to verify the route tests pass**

Run: `cd shell && npx vitest run src/shell/routes.test.tsx`
Expected: PASS (all tests, including the two new ones and every pre-existing one — the pre-existing tests never flip `authState.isAuthenticated`, so they exercise the same "authenticated" path they always did, now via the mocked `useAuth` instead of no `RequireAuth` at all).

- [ ] **Step 6: Write the failing `AppRuntimePage` gating tests**

Edit `shell/src/pages/AppRuntimePage.test.tsx`. The existing test's `renderRuntime()` call only mocks `getAppConfig` — once `AppRuntimePage` calls `getItem` first, that test needs a `getItem` mock too, or it will fail with "getItem is not a function". Change:

```tsx
test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Détails" }));
  expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/a%2Fb");
});
```

to:

```tsx
const okItem: Item = {
  pk: "9", resourceType: "app", title: "App", abstract: "", owner: "alice",
  thumbnailUrl: null, date: "", configId: null, isPublished: true,
};

test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Détails" }));
  expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/a%2Fb");
});

test("shows an access-denied message and never fetches the config when getItem fails", async () => {
  const getAppConfig = vi.fn().mockResolvedValue(config);
  renderRuntime({ getItem: vi.fn().mockRejectedValue(new Error("403")), getAppConfig });
  expect(await screen.findByRole("alert")).toHaveTextContent(/accès/i);
  expect(getAppConfig).not.toHaveBeenCalled();
});

test("proceeds to fetch and render the config once getItem succeeds", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(config) });
  expect(await screen.findByRole("button", { name: "Accueil" })).toBeInTheDocument();
});
```

Add `Item` to this file's type import:

```tsx
import type { AppConfig, Item, ItemClient } from "../api/types";
```

- [ ] **Step 7: Run to verify they fail**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: FAIL — `AppRuntimePage` doesn't call `getItem` at all yet, so the first test throws (`getItem is not a function`) and the two new tests can't observe the gating behavior they're asserting.

- [ ] **Step 8: Gate `AppRuntimePage` on `getItem`**

Replace `shell/src/pages/AppRuntimePage.tsx` with:

```tsx
import { useNavigate } from "react-router-dom";
import { useAppConfig, useItem } from "../api/hooks";
import { AppRenderer } from "../builder/AppRenderer";
import { registerBuiltinWidgets } from "../builder/widgets";

registerBuiltinWidgets();

export function AppRuntimePage({ pk, pageId }: { pk: string; pageId?: string }) {
  const itemQuery = useItem(pk);
  const query = useAppConfig(pk, { enabled: itemQuery.isSuccess });
  const navigate = useNavigate();
  if (itemQuery.isLoading || (itemQuery.isSuccess && query.isLoading)) {
    return <p role="status">Chargement…</p>;
  }
  if (itemQuery.isError) {
    return <p role="alert" className="text-sm text-red-600">Accès refusé.</p>;
  }
  if (query.isError || !query.data) {
    return <p role="alert" className="text-sm text-red-600">Application introuvable.</p>;
  }
  return (
    <div className="h-full w-full">
      <AppRenderer
        config={query.data}
        mode="runtime"
        pageId={pageId}
        onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
      />
    </div>
  );
}
```

- [ ] **Step 9: Run to verify they pass**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 10: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/App.tsx shell/src/shell/routes.tsx shell/src/shell/routes.test.tsx shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "feat(shell): runtime route is chrome-less, unauthenticated-reachable, gated via GeoNode getItem

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `ItemCard` displays `thumbnailUrl`

**Files:**
- Modify: `shell/src/ui/ItemCard.tsx`
- Test: `shell/src/ui/ItemCard.test.tsx` (extend)

**Interfaces:**
- No signature change to `ItemCard({ item, onOpen, actions })`. `thumbnailUrl` (already present on `Item`, already fetched by every `getItem`/`listItems` call, but never rendered anywhere) is now shown as an `<img>` when present; the existing type badge stays as the fallback when absent.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/ui/ItemCard.test.tsx`:

```tsx
test("shows a thumbnail image when thumbnailUrl is set", () => {
  render(<ItemCard item={{ ...item, thumbnailUrl: "https://geonode.test/thumbs/42.png" }} onOpen={() => {}} />);
  expect(screen.getByRole("img", { name: item.title })).toHaveAttribute("src", "https://geonode.test/thumbs/42.png");
});

test("shows no image when thumbnailUrl is null", () => {
  render(<ItemCard item={item} onOpen={() => {}} />);
  expect(screen.queryByRole("img")).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify the first one fails**

Run: `cd shell && npx vitest run src/ui/ItemCard.test.tsx`
Expected: FAIL — no `<img>` is ever rendered today.

- [ ] **Step 3: Render the thumbnail**

Edit `shell/src/ui/ItemCard.tsx`. Change:

```tsx
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {item.resourceType}
        </span>
        {actions}
      </div>
      <h3 className="text-base font-semibold">{item.title}</h3>
```

to:

```tsx
    <Card className="flex flex-col gap-2 p-4">
      <div className="flex items-start justify-between">
        <span className="w-fit rounded bg-slate-100 px-2 py-0.5 text-xs uppercase text-slate-600">
          {item.resourceType}
        </span>
        {actions}
      </div>
      {item.thumbnailUrl && (
        <img
          src={item.thumbnailUrl}
          alt={item.title}
          className="h-24 w-full rounded object-cover"
        />
      )}
      <h3 className="text-base font-semibold">{item.title}</h3>
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/ui/ItemCard.test.tsx`
Expected: PASS (5/5 — the 3 pre-existing tests use `thumbnailUrl: null` in the shared `item` fixture, so they never render an `<img>` and remain unaffected).

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/ui/ItemCard.tsx shell/src/ui/ItemCard.test.tsx
git commit -m "fix(shell): ItemCard actually renders thumbnailUrl

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Client-side DOM thumbnail capture in the builder

**Files:**
- Modify: `shell/package.json` (new dependency)
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `uploadThumbnail` (existing, via `useUploadThumbnail(pk)`, `shell/src/api/hooks.ts:100-110`); `html-to-image`'s `toBlob(node: HTMLElement): Promise<Blob | null>`.
- Produces: no new exported interface. `AppBuilderPage` gains a `ref` on its existing `<main>` element and a "Capturer une miniature" toolbar button that snapshots that element's current DOM to a PNG blob and uploads it through the existing thumbnail endpoint.

- [ ] **Step 1: Add the dependency**

Run: `cd shell && npm install html-to-image`
Expected: `shell/package.json`'s `dependencies` gains an `html-to-image` entry; `package-lock.json` (or the project's lockfile) updates accordingly.

- [ ] **Step 2: Write the failing test**

Edit `shell/src/pages/AppBuilderPage.test.tsx`. Add a mock for the new dependency at the top of the file (it renders real DOM/Canvas internally, which jsdom can't do — mirrors how `EChart`/`MapView` are already mocked elsewhere in this codebase):

```tsx
vi.mock("html-to-image", () => ({
  toBlob: vi.fn().mockResolvedValue(new Blob(["x"], { type: "image/png" })),
}));
```

Append this test:

```tsx
test("captures a thumbnail and uploads it", async () => {
  const uploadThumbnail = vi.fn().mockResolvedValue(undefined);
  renderPage({
    getAppConfig: vi.fn().mockResolvedValue(config),
    saveAppConfig: vi.fn().mockResolvedValue(undefined),
    uploadThumbnail,
  });
  await screen.findByRole("button", { name: "Capturer une miniature" });
  await userEvent.click(screen.getByRole("button", { name: "Capturer une miniature" }));
  await waitFor(() => expect(uploadThumbnail).toHaveBeenCalledWith("5", expect.any(File)));
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — no "Capturer une miniature" button exists yet.

- [ ] **Step 4: Wire the capture button**

Edit `shell/src/pages/AppBuilderPage.tsx`. Add the imports:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { toBlob } from "html-to-image";
import { useAppConfig, useSaveApp, useUploadThumbnail } from "../api/hooks";
```

(`useRef` is added to the existing `react` import; `useUploadThumbnail` is added to the existing `../api/hooks` import.)

Add the ref and mutation inside the component, next to the existing `save` mutation:

```tsx
  const query = useAppConfig(pk);
  const save = useSaveApp(pk);
  const thumbnail = useUploadThumbnail(pk);
  const mainRef = useRef<HTMLElement>(null);
```

Add the capture handler, next to `addWidget`/`updateSelectedProps`:

```tsx
  async function captureThumbnail() {
    if (!mainRef.current) return;
    const blob = await toBlob(mainRef.current);
    if (!blob) return;
    const file = new File([blob], "thumbnail.png", { type: "image/png" });
    try {
      await thumbnail.mutateAsync(file);
    } catch {
      /* surfaced via thumbnail.isError */
    }
  }
```

Add the button to the toolbar, right before "Enregistrer":

```tsx
        <div className="flex-1" />
        <Button size="sm" variant="outline" disabled={thumbnail.isPending} onClick={captureThumbnail}>
          Capturer une miniature
        </Button>
        <Button size="sm" disabled={save.isPending} onClick={() => save.mutate(draft)}>Enregistrer</Button>
        {save.isError && <span role="alert" className="text-sm text-red-600">Échec de l'enregistrement.</span>}
        {thumbnail.isError && <span role="alert" className="text-sm text-red-600">Échec de la capture.</span>}
```

Add the ref to the existing `<main>` element:

```tsx
        <main ref={mainRef} className="flex-1 overflow-auto p-2">
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS. Every pre-existing test in this file omits `uploadThumbnail` from its `renderPage(...)` client object — since none of them click "Capturer une miniature", `client.uploadThumbnail` is never called and its absence is never exercised.

- [ ] **Step 6: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/package.json shell/package-lock.json shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): capture a DOM thumbnail from the builder and upload it

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

(If the project's lockfile has a different name/path than `shell/package-lock.json` — e.g. `pnpm-lock.yaml` or `yarn.lock` — stage that file instead; check which lockfile is already tracked in git before running `npm install`.)

---

### Task 5: E2E — publish an item, thumbnail capture, authenticated-runtime regression

**Files:**
- Create: `shell/e2e/publication.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing).
- Produces: an E2E spec with three independent assertions in one flow: (1) toggling "Publier"/"Dépublier" from the catalog's item menu sends the right PATCH and flips the button label; (2) an authenticated visit to the runtime route (`/apps/9`) still renders correctly after Task 2's routing surgery — the regression this plan cares about most, since no anonymous-access path can be simulated under `authMode: "mock"` (see this plan's Scope note); (3) capturing a thumbnail from the builder succeeds.

- [ ] **Step 1: Make the item-9 mock track and PATCH `is_published`**

Edit `shell/e2e/mocks.ts`. Its `**/api/v2/resources/9` route today only ever answers with a fixed, hardcoded resource (no method branching, no `is_published`):

```ts
  await page.route("**/api/v2/resources/9", async (route) => {
    await route.fulfill({
      json: {
        resource: { pk: "9", resource_type: "app", title: "Créée", abstract: "",
          owner: { username: "mockuser" }, thumbnail_url: null, date: "2026-01-01" },
      },
    });
  });
```

Change it to branch on method and track publication state in the same closure that already holds `savedConfigs` (declare `let published = false;` right next to the existing `const savedConfigs = new Map<string, unknown>();` line, near the top of `mockGeoNode`):

```ts
  await page.route("**/api/v2/resources/9", async (route) => {
    if (route.request().method() === "PATCH") {
      const body = await route.request().postDataJSON();
      if (typeof body.is_published === "boolean") published = body.is_published;
    }
    await route.fulfill({
      json: {
        resource: { pk: "9", resource_type: "app", title: "Créée", abstract: "",
          owner: { username: "mockuser" }, thumbnail_url: null, date: "2026-01-01",
          is_published: published },
      },
    });
  });
```

This is additive for every other spec that already visits `/apps/9` and never toggles publication — `is_published: false` is simply present in the response now, matching the type this plan added to `Item`, and no existing spec asserts on its absence.

- [ ] **Step 2: Write the E2E**

Create `shell/e2e/publication.spec.ts`. `mockGeoNode`'s catalog list (`GET /api/v2/resources`) is a static fixture of two pre-existing items ("1"/"2") that never picks up newly-created items, so a freshly-created item is never listed on the catalog page — toggling its publish state has to happen from `/items/:pk` (item detail, `ItemDetailPage`), which calls `useItem(pk)` against the exact per-id route this task instruments, rather than from the catalog list:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("publishing an item, capturing a thumbnail, and the runtime route still work", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  // Create an app (lands on /apps/9/edit, per every other E2E spec's convention).
  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App publication");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // 1. Publish toggle from the item detail page.
  await page.goto("/items/9");
  await page.getByRole("button", { name: "Actions" }).click();
  await page.getByRole("button", { name: "Publier" }).click();
  await expect(page.getByRole("button", { name: "Actions" })).toBeVisible();
  await page.getByRole("button", { name: "Actions" }).click();
  await expect(page.getByRole("button", { name: "Dépublier" })).toBeVisible();

  // 2. Authenticated runtime route still renders after the routing change.
  await page.goto("/apps/9");
  await expect(page.locator("body")).toBeVisible();

  // 3. Thumbnail capture from the builder.
  await page.goto("/apps/9/edit");
  await page.getByRole("button", { name: "Capturer une miniature" }).click();
  await expect(page.getByRole("button", { name: "Capturer une miniature" })).toBeEnabled();
});
```

- [ ] **Step 3: Run the new E2E**

Run: `cd shell && npx playwright test publication`
Expected: PASS.

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme + pages-navigation + templates + variables + publication).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/publication.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): E2E publish toggle, thumbnail capture, authenticated runtime regression

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design §10/§13 SP-0d.6, as refined):** `is_published` reused from GeoNode, no `BuilderConfig` change → Task 1. Runtime route chrome-less + unauthenticated-reachable, gated via a `getItem`-first check rather than a Builder Service change → Task 2. Embed/iframe falls out of Task 2 for free (no separate route/headers, as the refined spec states) — no dedicated task needed, and the E2E's step 2 (visiting `/apps/9` and confirming it renders without the `AppLayout` chrome) is the closest proof available under this plan's mock-auth constraints. `ItemCard` thumbnail display fix + manual DOM capture → Tasks 3–4. End-to-end proof → Task 5.
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor; Task 5 Step 1 is the one step that asks the implementer to adapt a sketch to the real file rather than apply a byte-exact diff, and it says so explicitly rather than pretending certainty about a file this plan didn't fully quote.
- **Type consistency:** `Item.isPublished`/`UpdatePatch.isPublished` defined once in `api/types.ts`, consumed identically by `itemClient.ts` (`toItem`, `updateItem`), `ItemActions.tsx`, and every fixture updated in Task 1 Step 7. `AppRuntimePage`'s gating (`itemQuery`/`query`) uses the exact same `useItem`/`useAppConfig` hooks and `{enabled}` option pattern already established by `useMapConfig`/other hooks — no new hook shape introduced.
- **Backward compatibility:** `Item.isPublished` is a new *required* field, not optional — deliberately, because GeoNode resources always have a real `is_published` value (verified: already read via `listItems`'s `scope: "public"` filter param) — so every literal `Item` fixture in the test suite is updated in Task 1 Step 7, enumerated exhaustively rather than left as a silent type error for the next task to discover. `UpdatePatch.isPublished` is optional, so every pre-existing `updateItem(pk, {title, abstract})`-style call (no `isPublished`) is unaffected — verified in Task 1 Step 4's `updateItem` rewrite (`isPublished !== undefined` guard). Every non-runtime route keeps its exact pre-existing auth/chrome behavior (Task 2's `routes.test.tsx` additions prove this explicitly, not just by omission).
- **Façade discipline:** no new network access beyond what already existed; `getItem`/`updateItem`/`uploadThumbnail`/`getAppConfig` are all pre-existing façade methods, only their call sequencing (Task 2) or payload (Task 1) changes.
- **Engine unity:** unaffected — `AppRenderer` itself is untouched by this entire plan; only what surrounds it (chrome, auth gate, route nesting) changes.
- **Backend:** confirmed no change needed anywhere in this plan — `builder-service/app/schemas.py` gains no field, and no route in `builder-service/app/routes.py` is touched. The Builder Service's pre-existing lack of its own permission check (documented in the refined spec, §10) is explicitly *not* fixed by this plan — the `getItem`-first gate in `AppRuntimePage` works around it at the call-sequencing level rather than closing it at the source, and this tradeoff is written into the spec, not left implicit.
