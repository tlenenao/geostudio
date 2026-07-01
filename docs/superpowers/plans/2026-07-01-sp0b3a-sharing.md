# Item Sharing (SP-0b.3-a) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user share an App/Dashboard from the shell — set it public/private and grant existing GeoNode groups a Reader/Editor role — via a `ShareDialog` opened from the item actions menu.

**Architecture:** Front-only. Extend the `item-client` façade with `listGroups`, `getSharing`, `setSharing` (mapping a simple `Sharing` model to/from GeoNode's permissions payload, isolated in the façade). Add TanStack Query hooks (`useGroups`, `useSharing`, `useSetSharing`). Build a `ShareDialog` (reusing the `Dialog` primitive) and add a "Partager" entry to the existing `ItemActions` menu. No Builder Service change.

**Tech Stack:** React 19, TypeScript, @tanstack/react-query, Vitest + Testing Library + MSW. (No new dependencies.)

## Global Constraints

- Work under `shell/`; run from `shell/`: `npm test`, `npm run build`.
- All network access via `item-client`; no GeoNode import/URL outside the façade; no token in localStorage.
- Keep test output clean (MSW `onUnhandledRequest: "error"`).
- Sharing model (façade contract): `Sharing = { public: boolean; groups: { groupId: string; role: "viewer" | "editor" }[] }`.
- GeoNode mapping (defined by the MSW mock, isolated in `item-client`): the permissions payload uses a `groups` array of `{ id, permissions }`; `permissions` is `"view"` (Reader) or `"edit"` (Editor); a group with `id === "anonymous"` and `"view"` represents **public**. Real GeoNode keys may differ; only `item-client` and the mock know them.
- `listGroups` maps GeoNode `group_profiles: [{ pk, title }]` → `Group = { id: string; title: string }`.
- Existing `Item`/`ItemClient` contracts extend, not break.

---

### Task 1: `item-client` sharing methods + MSW handlers

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/test/msw/handlers.ts`
- Test: `shell/src/api/itemClient.test.ts` (add cases)

**Interfaces:**
- Produces in `types.ts`: `Group = { id: string; title: string }`, `ShareRole = "viewer" | "editor"`, `Sharing = { public: boolean; groups: { groupId: string; role: ShareRole }[] }`; and on `ItemClient`: `listGroups(): Promise<Group[]>`, `getSharing(pk: string): Promise<Sharing>`, `setSharing(pk: string, sharing: Sharing): Promise<void>`.
- `listGroups` → `GET {geonodeUrl}/api/v2/groups`, maps `group_profiles`.
- `getSharing` → `GET {geonodeUrl}/api/v2/resources/{pk}/permissions`; `public = groups.some(g => g.id === "anonymous")`; `groups = payload.groups.filter(g => g.id !== "anonymous").map(g => ({ groupId: g.id, role: g.permissions === "edit" ? "editor" : "viewer" }))`.
- `setSharing` → `PUT {geonodeUrl}/api/v2/resources/{pk}/permissions` with `{ groups: [...(public ? [{ id: "anonymous", permissions: "view" }] : []), ...groups.map(g => ({ id: g.groupId, permissions: g.role === "editor" ? "edit" : "view" }))] }`; throws on non-2xx.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/itemClient.test.ts`:

```ts
test("listGroups maps GeoNode group_profiles", async () => {
  const groups = await makeClient().listGroups();
  expect(groups).toEqual([
    { id: "10", title: "Équipe A" },
    { id: "11", title: "Équipe B" },
  ]);
});

test("getSharing maps public flag and group roles", async () => {
  const sharing = await makeClient().getSharing("7");
  expect(sharing.public).toBe(true);
  expect(sharing.groups).toEqual([{ groupId: "10", role: "editor" }]);
});

test("setSharing sends the mapped GeoNode payload", async () => {
  let body: any = null;
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  await makeClient().setSharing("7", {
    public: true,
    groups: [{ groupId: "5", role: "viewer" }],
  });
  expect(body.groups).toEqual([
    { id: "anonymous", permissions: "view" },
    { id: "5", permissions: "view" },
  ]);
});

test("setSharing omits the anonymous group when private", async () => {
  let body: any = null;
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  await makeClient().setSharing("7", {
    public: false,
    groups: [{ groupId: "5", role: "editor" }],
  });
  expect(body.groups).toEqual([{ id: "5", permissions: "edit" }]);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: FAIL — methods missing / no MSW handlers.

- [ ] **Step 3: Add types in `shell/src/api/types.ts`**

```ts
export type Group = { id: string; title: string };
export type ShareRole = "viewer" | "editor";
export type Sharing = {
  public: boolean;
  groups: { groupId: string; role: ShareRole }[];
};
```

On `interface ItemClient`, add:

```ts
  listGroups(): Promise<Group[]>;
  getSharing(pk: string): Promise<Sharing>;
  setSharing(pk: string, sharing: Sharing): Promise<void>;
```

- [ ] **Step 4: Implement in `shell/src/api/itemClient.ts`**

Add `Group`, `Sharing` to the type import. Add the three methods to the returned object (reusing the existing `get<T>` helper for GET; `geonodeUrl`/`getToken` are in scope):

```ts
    async listGroups(): Promise<Group[]> {
      const data = await get<{ group_profiles: { pk: number | string; title: string }[] }>(
        `/api/v2/groups`,
      );
      return data.group_profiles.map((g) => ({ id: String(g.pk), title: g.title }));
    },

    async getSharing(pk: string): Promise<Sharing> {
      const data = await get<{ groups: { id: string; permissions: string }[] }>(
        `/api/v2/resources/${pk}/permissions`,
      );
      return {
        public: data.groups.some((g) => g.id === "anonymous"),
        groups: data.groups
          .filter((g) => g.id !== "anonymous")
          .map((g) => ({ groupId: g.id, role: g.permissions === "edit" ? "editor" : "viewer" })),
      };
    },

    async setSharing(pk: string, sharing: Sharing): Promise<void> {
      const token = getToken();
      const groups = [
        ...(sharing.public ? [{ id: "anonymous", permissions: "view" }] : []),
        ...sharing.groups.map((g) => ({
          id: g.groupId,
          permissions: g.role === "editor" ? "edit" : "view",
        })),
      ];
      const res = await fetch(`${geonodeUrl}/api/v2/resources/${pk}/permissions`, {
        method: "PUT",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ groups }),
      });
      if (!res.ok) {
        throw new Error(`Request failed: ${res.status} PUT permissions`);
      }
    },
```

- [ ] **Step 5: Add MSW handlers in `shell/src/test/msw/handlers.ts`**

```ts
  http.get(`${GEONODE}/api/v2/groups`, () =>
    HttpResponse.json({
      group_profiles: [
        { pk: 10, title: "Équipe A" },
        { pk: 11, title: "Équipe B" },
      ],
    }),
  ),

  http.get(`${GEONODE}/api/v2/resources/:pk/permissions`, () =>
    HttpResponse.json({
      groups: [
        { id: "anonymous", permissions: "view" },
        { id: "10", permissions: "edit" },
      ],
    }),
  ),

  http.put(`${GEONODE}/api/v2/resources/:pk/permissions`, () =>
    new HttpResponse(null, { status: 200 }),
  ),
```

- [ ] **Step 6: Run to verify they pass**

Run: `npm test -- src/api/itemClient.test.ts`
Expected: PASS (existing + 4 new).

- [ ] **Step 7: Commit**

```bash
git add shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/test/msw/handlers.ts shell/src/api/itemClient.test.ts
git commit -m "feat(shell): add item-client sharing (listGroups/getSharing/setSharing)"
```

---

### Task 2: Sharing hooks

**Files:**
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/hooks.test.tsx` (add cases)

**Interfaces:**
- Consumes: `useItemClient`, `useQuery`, `useMutation`, `useQueryClient`, `Sharing`.
- Produces:
  - `useGroups()` → `useQuery(["groups"], () => client.listGroups())`.
  - `useSharing(pk)` → `useQuery(["sharing", pk], () => client.getSharing(pk))`.
  - `useSetSharing(pk)` → `useMutation((sharing: Sharing) => client.setSharing(pk, sharing))`; `onSuccess` invalidates `["sharing", pk]` and `["items"]`.

- [ ] **Step 1: Write the failing tests**

Add to `shell/src/api/hooks.test.tsx`:

```tsx
import { useGroups, useSharing } from "./hooks";

test("useGroups returns the mapped groups", async () => {
  const { result } = renderHook(() => useGroups(), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.[0]).toEqual({ id: "10", title: "Équipe A" });
});

test("useSharing returns the item sharing", async () => {
  const { result } = renderHook(() => useSharing("7"), { wrapper });
  await waitFor(() => expect(result.current.isSuccess).toBe(true));
  expect(result.current.data?.public).toBe(true);
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `npm test -- src/api/hooks.test.tsx`
Expected: FAIL — `useGroups`/`useSharing` not exported.

- [ ] **Step 3: Implement in `shell/src/api/hooks.ts`**

Add `Sharing` to the type import. Add the hooks:

```ts
export function useGroups() {
  const client = useItemClient();
  return useQuery({ queryKey: ["groups"], queryFn: () => client.listGroups() });
}

export function useSharing(pk: string) {
  const client = useItemClient();
  return useQuery({ queryKey: ["sharing", pk], queryFn: () => client.getSharing(pk) });
}

export function useSetSharing(pk: string) {
  const client = useItemClient();
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (sharing: Sharing) => client.setSharing(pk, sharing),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["sharing", pk] });
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
git commit -m "feat(shell): add useGroups/useSharing/useSetSharing hooks"
```

---

### Task 3: `ShareDialog` component

**Files:**
- Create: `shell/src/shell/ShareDialog.tsx`
- Test: `shell/src/shell/ShareDialog.test.tsx`

**Interfaces:**
- Consumes: `useGroups`, `useSharing`, `useSetSharing`, `Dialog`, `Button`, `ShareRole`, `Item`.
- Produces: `ShareDialog({ item, open, onClose }: { item: Item; open: boolean; onClose: () => void })` — a `Dialog` titled "Partager l'élément" with a **Public** checkbox (`aria-label="Public"`), a per-group checkbox (`aria-label={\`Groupe \${title}\`}`) + role `<select>` (`aria-label={\`Rôle \${title}\`}`, Lecteur/Éditeur), initialized from `useSharing`. **Enregistrer** calls `useSetSharing(item.pk).mutateAsync({ public, groups })` (only checked groups), closes on success, shows `role="alert"` on error, disabled while pending. Loading/error states for the queries.

- [ ] **Step 1: Write the failing test**

Create `shell/src/shell/ShareDialog.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
import { ShareDialog } from "./ShareDialog";

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Mon app",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
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

test("saves the sharing payload for a checked group", async () => {
  let body: any = null;
  server.use(
    http.put("https://geonode.test/api/v2/resources/:pk/permissions", async ({ request }) => {
      body = await request.json();
      return new HttpResponse(null, { status: 200 });
    }),
  );
  const onClose = vi.fn();
  render(
    <Harness>
      <ShareDialog item={item} open onClose={onClose} />
    </Harness>,
  );
  // Group "Équipe B" (id 11) is not shared initially; check it as Reader.
  await userEvent.click(await screen.findByRole("checkbox", { name: "Groupe Équipe B" }));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() => expect(onClose).toHaveBeenCalled());
  // Initial sharing had public + group 10 as editor; we added 11 as viewer.
  expect(body.groups).toEqual(
    expect.arrayContaining([
      { id: "anonymous", permissions: "view" },
      { id: "10", permissions: "edit" },
      { id: "11", permissions: "view" },
    ]),
  );
});
```

Add `import { vi } from "vitest";` at the top.

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/shell/ShareDialog.test.tsx`
Expected: FAIL — cannot resolve `./ShareDialog`.

- [ ] **Step 3: Create `shell/src/shell/ShareDialog.tsx`**

```tsx
import { useEffect, useState } from "react";
import { useGroups, useSetSharing, useSharing } from "../api/hooks";
import type { Item, ShareRole } from "../api/types";
import { Button } from "../ui/button";
import { Dialog } from "../ui/dialog";

export function ShareDialog({
  item,
  open,
  onClose,
}: {
  item: Item;
  open: boolean;
  onClose: () => void;
}) {
  const groupsQuery = useGroups();
  const sharingQuery = useSharing(item.pk);
  const setSharing = useSetSharing(item.pk);

  const [isPublic, setIsPublic] = useState(false);
  const [roles, setRoles] = useState<Record<string, ShareRole | undefined>>({});

  useEffect(() => {
    if (sharingQuery.data) {
      setIsPublic(sharingQuery.data.public);
      const map: Record<string, ShareRole> = {};
      sharingQuery.data.groups.forEach((g) => {
        map[g.groupId] = g.role;
      });
      setRoles(map);
    }
  }, [sharingQuery.data]);

  async function submit() {
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
    <Dialog open={open} onClose={onClose} title="Partager l'élément">
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

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/shell/ShareDialog.test.tsx`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add shell/src/shell/ShareDialog.tsx shell/src/shell/ShareDialog.test.tsx
git commit -m "feat(shell): add ShareDialog (visibility + group roles)"
```

---

### Task 4: "Partager" entry in `ItemActions`

**Files:**
- Modify: `shell/src/shell/ItemActions.tsx`
- Test: `shell/src/shell/ItemActions.test.tsx` (add a case)

**Interfaces:**
- Consumes: `ShareDialog`.
- Produces: the `Panel` union gains `"share"`; the menu gains a **Partager** button (opens the share panel); `<ShareDialog item={item} open={panel === "share"} onClose={() => setPanel(null)} />` is rendered.

- [ ] **Step 1: Write the failing test**

Add to `shell/src/shell/ItemActions.test.tsx`:

```tsx
test("opens the share dialog from the menu", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /partager/i }));
  expect(await screen.findByRole("dialog", { name: /partager/i })).toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `npm test -- src/shell/ItemActions.test.tsx`
Expected: FAIL — no "Partager" button.

- [ ] **Step 3: Wire into `shell/src/shell/ItemActions.tsx`**

Add the import:

```tsx
import { ShareDialog } from "./ShareDialog";
```

Change the `Panel` type to include `"share"`:

```tsx
type Panel = null | "menu" | "edit" | "thumbnail" | "share" | "delete";
```

Add a **Partager** button to the menu (after "Miniature", before "Supprimer"):

```tsx
          <button className="px-3 py-1 text-left hover:bg-slate-100" onClick={() => setPanel("share")}>
            Partager
          </button>
```

Render the dialog (next to the other dialogs, e.g. after the thumbnail `Dialog`):

```tsx
      <ShareDialog item={item} open={panel === "share"} onClose={() => setPanel(null)} />
```

- [ ] **Step 4: Run to verify it passes**

Run: `npm test -- src/shell/ItemActions.test.tsx`
Expected: PASS (existing + new).

- [ ] **Step 5: Run the full suite + build**

Run: `npm test` then `npm run build`.
Expected: all PASS; build succeeds.

- [ ] **Step 6: Commit**

```bash
git add shell/src/shell/ItemActions.tsx shell/src/shell/ItemActions.test.tsx
git commit -m "feat(shell): add Partager entry to ItemActions"
```

---

## Self-Review

**Spec coverage (against SP-0b.3 §3/§4/§5 + phase 0b.3-a):**
- `listGroups`/`getSharing`/`setSharing` + Sharing↔GeoNode mapping → Task 1. ✅
- `useGroups`/`useSharing`/`useSetSharing` (invalidations) → Task 2. ✅
- `ShareDialog` (public toggle + group roles, loading/error, save) → Task 3. ✅
- "Partager" entry in `ItemActions` → Task 4. ✅
- Out of phase (0b.3-b): `ItemScope` + `listItems` scope + catalog scope filter — correctly excluded.

**Placeholder scan:** every step has complete code; no TBD/TODO. ✅

**Type consistency:** `Group`/`ShareRole`/`Sharing` defined in Task 1 (`types.ts`), consumed by hooks (Task 2), `ShareDialog` (Task 3). `useGroups`/`useSharing`/`useSetSharing` defined in Task 2, consumed by `ShareDialog` (Task 3). `ShareDialog({ item, open, onClose })` defined in Task 3, consumed by `ItemActions` (Task 4). The `ItemActions.test` `Harness` (from SP-0b.2-c) already provides QueryClient + ItemClientProvider + global MSW, so the new share-menu test resolves groups/sharing via the Task 1 handlers. ✅

## Notes for SP-0b.3-b

- `listItems` gains `scope?: ItemScope` + `me?: string`; the catalog adds a "Portée" `<select>`; the façade maps scope to GeoNode filters (mine/public direct; "shared" = visible and not owned by `me`).
