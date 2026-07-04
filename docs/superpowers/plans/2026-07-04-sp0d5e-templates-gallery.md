# GeoStudio SP-0d.5e — Galerie de templates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let a user pick a pre-built starter layout ("modèle") when creating an app/dashboard item, instead of always starting from an empty canvas.

**Architecture:** `templates.ts` is a pure, static data module — a fixed list of `Template = { id, name, kind, layout, theme? }` — the single source of truth for what templates exist. `createConfigItem` gains an optional `templateId`; when present, it seeds the new config's `layout`/`theme` from the matching template instead of the empty defaults it already builds. `NewItemButton`'s creation dialog gains a "Modèle" `<select>`, filtered to the templates matching the currently-selected `kind`, defaulting to "Vide" (today's behavior, unchanged when no template is picked).

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright + MSW. No new dependency. Backend: **no change** — a template only supplies a `layout`/`theme` shape the backend already accepts.

## Global Constraints

- Additive/back-compatible: `createConfigItem`'s new `templateId?: string` parameter is optional; every existing call site (and every existing test) that omits it gets exactly today's empty-layout config.
- Front: no new service URL, no new dependency. Static data lives in a small builder-local module (`templates.ts`), mirroring `theme.ts`'s `DEFAULT_*` constants — a single source of truth, not duplicated between the dialog and the item-client.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`).

**Scope note:** This plan ships a fixed, curated gallery of 2 starter templates (one `app`, one `dashboard`) plus the always-available "Vide" (blank) option — matching the "3-4 starting points" scope confirmed for this slice. A personal template library (save-an-existing-app-as-template) is a separate, larger feature (needs backend storage) and is out of scope here.

---

### Task 1: `templates.ts` (pure data) + `createConfigItem` seeds from a template

**Files:**
- Create: `shell/src/builder/templates.ts`
- Test: `shell/src/builder/templates.test.ts`
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/api/itemClient.ts`
- Modify: `shell/src/api/hooks.ts`
- Test: `shell/src/api/itemClient.test.ts` (extend)

**Interfaces:**
- Produces:
  - `Template = { id: string; name: string; kind: "app" | "dashboard"; layout: AppLayout; theme?: Theme }` (exported from `templates.ts`).
  - `TEMPLATES: Template[]` — the fixed gallery (2 entries).
  - `getTemplate(id: string): Template | undefined`.
  - `ItemClient.createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item>` (widened; `templateId` optional).

- [ ] **Step 1: Write the failing `templates.ts` tests**

Create `shell/src/builder/templates.test.ts`:

```ts
import { expect, test } from "vitest";
import { TEMPLATES, getTemplate } from "./templates";

test("exposes exactly one app template and one dashboard template", () => {
  expect(TEMPLATES.filter((t) => t.kind === "app")).toHaveLength(1);
  expect(TEMPLATES.filter((t) => t.kind === "dashboard")).toHaveLength(1);
});

test("every template has at least one layout item", () => {
  for (const t of TEMPLATES) {
    expect(t.layout.items.length).toBeGreaterThan(0);
  }
});

test("getTemplate resolves a template by id", () => {
  const first = TEMPLATES[0];
  expect(getTemplate(first.id)).toBe(first);
});

test("getTemplate returns undefined for an unknown id", () => {
  expect(getTemplate("nope")).toBeUndefined();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/templates.test.ts`
Expected: FAIL — module `./templates` does not exist.

- [ ] **Step 3: Implement `templates.ts`**

Create `shell/src/builder/templates.ts`:

```ts
import type { AppLayout, Theme } from "../api/types";

export type Template = {
  id: string;
  name: string;
  kind: "app" | "dashboard";
  layout: AppLayout;
  theme?: Theme;
};

const TWO_COLUMN_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    { id: "tpl-two-col-a", widget: "text", x: 0, y: 0, w: 3, h: 3, props: { text: "Colonne gauche" } },
    { id: "tpl-two-col-b", widget: "text", x: 3, y: 0, w: 3, h: 3, props: { text: "Colonne droite" } },
  ],
};

const BASIC_DASHBOARD_LAYOUT: AppLayout = {
  type: "grid",
  breakpoints: {},
  items: [
    { id: "tpl-dash-title", widget: "text", x: 0, y: 0, w: 6, h: 2, props: { text: "Bienvenue sur votre tableau de bord" } },
    { id: "tpl-dash-cta", widget: "button", x: 0, y: 2, w: 2, h: 1, props: { label: "En savoir plus", href: "" } },
  ],
};

export const TEMPLATES: Template[] = [
  { id: "two-column", name: "Deux colonnes", kind: "app", layout: TWO_COLUMN_LAYOUT },
  { id: "basic-dashboard", name: "Tableau de bord basique", kind: "dashboard", layout: BASIC_DASHBOARD_LAYOUT },
];

export function getTemplate(id: string): Template | undefined {
  return TEMPLATES.find((t) => t.id === id);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/templates.test.ts`
Expected: PASS (4/4).

- [ ] **Step 5: Write the failing `createConfigItem` tests**

Append to `shell/src/api/itemClient.test.ts`:

```ts
test("createConfigItem seeds the layout from a template when templateId is given", async () => {
  let body: any = null;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "two-column" });
  expect(body.config.layout.items).toHaveLength(2);
  expect(body.config.layout.items[0].widget).toBe("text");
});

test("createConfigItem falls back to an empty layout when templateId is unknown", async () => {
  let body: any = null;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-1", kind: body.config.kind, itemId: "1", version: 1, config: body.config });
    }),
  );
  await makeClient().createConfigItem({ kind: "app", title: "T", owner: "o", templateId: "does-not-exist" });
  expect(body.config.layout).toEqual({ type: "grid", breakpoints: {}, items: [] });
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: FAIL — `createConfigItem` doesn't accept/consume `templateId` yet.

- [ ] **Step 7: Widen `createConfigItem`**

Edit `shell/src/api/types.ts`. Change the `createConfigItem` signature in the `ItemClient` interface from:

```ts
  createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item>;
```

to:

```ts
  createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item>;
```

Edit `shell/src/api/itemClient.ts`. Add the import:

```ts
import { getTemplate } from "../builder/templates";
```

Change `createConfigItem`'s signature and body from:

```ts
    async createConfigItem(input: { kind: CreateKind; title: string; owner: string }): Promise<Item> {
      const config = {
        version: 1,
        kind: input.kind,
        theme: {},
        dataSources: [],
        layout: { type: "grid", breakpoints: {}, items: [] },
        messages: [],
      };
```

to:

```ts
    async createConfigItem(input: { kind: CreateKind; title: string; owner: string; templateId?: string }): Promise<Item> {
      const template = input.templateId ? getTemplate(input.templateId) : undefined;
      const config = {
        version: 1,
        kind: input.kind,
        theme: template?.theme ?? {},
        dataSources: [],
        layout: template?.layout ?? { type: "grid", breakpoints: {}, items: [] },
        messages: [],
      };
```

Edit `shell/src/api/hooks.ts`. Widen `useCreateItem`'s `mutationFn` input type from:

```ts
    mutationFn: (input: { kind: CreateKind; title: string; owner: string }) =>
      client.createConfigItem(input),
```

to:

```ts
    mutationFn: (input: { kind: CreateKind; title: string; owner: string; templateId?: string }) =>
      client.createConfigItem(input),
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd shell && npx vitest run src/api/itemClient.test.ts`
Expected: PASS (all tests, including the two new ones). The pre-existing `"createConfigItem sends title, owner and an empty grid layout"` test omits `templateId` — `template` resolves to `undefined`, so `layout` falls back to the empty grid exactly as before.

- [ ] **Step 9: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/templates.ts shell/src/builder/templates.test.ts shell/src/api/types.ts shell/src/api/itemClient.ts shell/src/api/itemClient.test.ts shell/src/api/hooks.ts
git commit -m "feat(shell): templates.ts gallery + createConfigItem seeds layout/theme from a template

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: "Modèle" select in the creation dialog

**Files:**
- Modify: `shell/src/shell/NewItemButton.tsx`
- Test: `shell/src/shell/NewItemButton.test.tsx` (extend)

**Interfaces:**
- Consumes: `TEMPLATES` (Task 1), `useCreateItem` (widened in Task 1).
- Produces: no new exported interface. The dialog gains a `<select aria-label="Modèle">` shown only when `kind !== "map"`, listing `"Vide"` plus every `TEMPLATES` entry whose `kind` matches the currently-selected `kind`; submitting passes the selected `templateId` (or `undefined` for "Vide") to `create.mutateAsync`.

- [ ] **Step 1: Write the failing tests**

`shell/src/shell/NewItemButton.test.tsx` already defines a `Harness` component (real `createItemClient` wired to MSW's `server`, wrapped in `QueryClientProvider`/`ItemClientProvider`/`MemoryRouter`) that every existing test in the file renders `<NewItemButton />` inside of — reuse it verbatim. Add `waitFor` to the file's existing `@testing-library/react` import:

```tsx
import { render, screen, waitFor } from "@testing-library/react";
```

Append to `shell/src/shell/NewItemButton.test.tsx`:

```tsx
test("shows a Modèle select for app/dashboard, filtered by the current type", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.getByRole("option", { name: "Vide" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Deux colonnes" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Tableau de bord basique" })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dashboard");
  expect(screen.getByRole("option", { name: "Tableau de bord basique" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Deux colonnes" })).not.toBeInTheDocument();
});

test("creating from a template posts its layout", async () => {
  let body: any = null;
  server.use(
    http.post("https://builder.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-9", kind: "app", itemId: "9", version: 1, config: body.config });
    }),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Modèle"), "two-column");
  await userEvent.type(screen.getByLabelText("Titre"), "Mon app");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  await waitFor(() => expect(body).not.toBeNull());
  expect(body.config.layout.items).toHaveLength(2);
  expect(body.config.layout.items[0].widget).toBe("text");
});

test("does not show a Modèle select for the map type", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  expect(screen.queryByLabelText("Modèle")).not.toBeInTheDocument();
});
```

This matches the file's existing MSW-backed convention exactly (see its `"creates a Map and navigates to the editor route"` test, which likewise calls `server.use(http.post(...))` to intercept the real POST) — no injected fake `ItemClient`, no new fixtures.

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: FAIL — no "Modèle" select exists yet.

- [ ] **Step 3: Add the "Modèle" select**

Edit `shell/src/shell/NewItemButton.tsx`. Add the import:

```tsx
import { TEMPLATES } from "../builder/templates";
```

Add a `templateId` state next to `kind`/`title`:

```tsx
  const [templateId, setTemplateId] = useState("");
```

In `close()`, reset it alongside the others:

```tsx
  function close() {
    setOpen(false);
    setTitle("");
    setKind("app");
    setTemplateId("");
    create.reset();
    createMap.reset();
  }
```

When `kind` changes, reset `templateId` (a template picked for "app" shouldn't silently survive a switch to "dashboard"). Change the `<select aria-label="Type">`'s `onChange`:

```tsx
              onChange={(e) => setKind(e.target.value as "app" | "dashboard" | "map")}
```

to:

```tsx
              onChange={(e) => { setKind(e.target.value as "app" | "dashboard" | "map"); setTemplateId(""); }}
```

In `submit`, pass `templateId` through (only meaningful for non-map kinds, so this is safe to always include):

```tsx
      const item =
        kind === "map"
          ? await createMap.mutateAsync({ title: clean, owner: username ?? "" })
          : await create.mutateAsync({ kind, title: clean, owner: username ?? "", templateId: templateId || undefined });
```

Add the select itself, right after the "Type" `<label>` block and before the "Titre" `<label>` block:

```tsx
          {kind !== "map" && (
            <label className="flex flex-col gap-1 text-sm">
              Modèle
              <select
                aria-label="Modèle"
                className="h-9 rounded-md border border-slate-300 bg-white px-3 text-sm"
                value={templateId}
                onChange={(e) => setTemplateId(e.target.value)}
              >
                <option value="">Vide</option>
                {TEMPLATES.filter((t) => t.kind === kind).map((t) => (
                  <option key={t.id} value={t.id}>{t.name}</option>
                ))}
              </select>
            </label>
          )}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/shell/NewItemButton.test.tsx`
Expected: PASS. The pre-existing tests (which never touch "Modèle") are unaffected — `templateId` defaults to `""`, so `create.mutateAsync` is called with `templateId: undefined`, and `createConfigItem`'s mock in those tests doesn't assert on that field.

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/shell/NewItemButton.tsx shell/src/shell/NewItemButton.test.tsx
git commit -m "feat(shell): pick a starter template when creating an app/dashboard

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: E2E — create an app from a template, see its widgets immediately

**Files:**
- Create: `shell/e2e/templates.spec.ts`
- Modify: `shell/e2e/mocks.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing).
- Produces: `mockGeoNode`'s `POST /configs` handler now stores the *sent* `config` for `app`/`dashboard` creation (item id `9`) into the same `savedConfigs` map the `PUT` handler already uses, so a subsequent `GET /configs/by-item/9` reflects the template that was actually picked at creation time — today it unconditionally returns a fixed empty response regardless of what was posted, which is correct for every existing spec (none of them assert on a template) but would silently break this one.

- [ ] **Step 1: Make the mock persist the POST'd config**

Edit `shell/e2e/mocks.ts`. Change the `/configs` POST handler's app/dashboard branch from:

```ts
    } else {
      // App/dashboard creation path — keep the existing response unchanged.
      await route.fulfill({
        json: { id: "cfg-9", kind: "app", itemId: "9", version: 1, config: {} },
      });
    }
```

to:

```ts
    } else {
      // App/dashboard creation path — persist the posted config so a later
      // GET (e.g. opening the editor right after creation) reflects it,
      // the same way the PUT handler already does for saves.
      savedConfigs.set("9", body.config);
      await route.fulfill({
        json: { id: "cfg-9", kind: body.config.kind, itemId: "9", version: 1, config: body.config },
      });
    }
```

This is purely additive: every existing spec that creates an app/dashboard (e.g. `app-builder.spec.ts`, `theme.spec.ts`, `pages-navigation.spec.ts`) posts a config with `layout: { type: "grid", breakpoints: {}, items: [] }` (no template), so `savedConfigs.set("9", ...)` now stores that same empty layout instead of nothing — the subsequent `GET /configs/by-item/9` (which already prefers `stored ?? DEFAULT_APP_CONFIG`) returns an equivalent empty config either way. No existing spec's assertions change.

- [ ] **Step 2: Write the E2E**

Create `shell/e2e/templates.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("creating an app from a template shows its widgets immediately in the editor", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await dialog.getByLabel("Modèle").selectOption("two-column");
  await dialog.getByLabel("Titre").fill("App depuis modèle");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await expect(page.getByText("Colonne gauche")).toBeVisible();
  await expect(page.getByText("Colonne droite")).toBeVisible();
});
```

- [ ] **Step 3: Run the new E2E**

Run: `cd shell && npx playwright test templates`
Expected: PASS — both template widgets are visible in the editor right after creation, with no save step in between.

- [ ] **Step 4: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme + pages-navigation + templates).

- [ ] **Step 5: Commit**

```bash
git add shell/e2e/templates.spec.ts shell/e2e/mocks.ts
git commit -m "test(shell): E2E create an app from a template, see its widgets in the editor

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** "modèles pré-construits, 3-4 options sélectionnables à la création" (confirmed scope) → `templates.ts`'s fixed 2-template gallery + implicit "Vide" (Task 1), the "Modèle" select filtered by `kind` (Task 2), end-to-end proof that a template's content appears immediately post-creation (Task 3).
- **Placeholder scan:** none — every step carries complete code; the two templates' exact widget items/props are fully specified, not "TBD".
- **Type consistency:** `Template` is defined once in `templates.ts` and consumed identically by `itemClient.ts` (`getTemplate`) and `NewItemButton.tsx` (`TEMPLATES`, filtered by `.kind`). `createConfigItem`'s widened signature is identical across the `ItemClient` interface (`types.ts`), its implementation (`itemClient.ts`), and `useCreateItem`'s `mutationFn` (`hooks.ts`).
- **Backward compatibility:** `templateId` is optional everywhere; every pre-existing call to `createConfigItem`/`create.mutateAsync` (in `NewItemButton`'s own map-path, in tests, in E2E) omits it and gets exactly today's empty-layout, `theme: {}` config — verified explicitly in Task 1 Step 8's note and Task 2 Step 4's note. The `mocks.ts` change in Task 3 is additive and confirmed not to change any existing spec's observable behavior (Task 3 Step 1's note).
- **Façade discipline:** no new network access; `templateId` flows through the existing `POST /configs` call `createConfigItem` already makes.
- **Engine unity:** not applicable — template selection is a one-time seed at creation time, not a rendering concern; once created, a templated app is indistinguishable from a hand-built one and renders through the same single `AppRenderer` engine as always.
- **Backend:** confirmed no change needed — a template only ever supplies a `layout`/`theme` shape the backend's `BuilderConfig` already accepts unconstrained.
