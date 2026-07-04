# GeoStudio SP-0d.5 — Dette technique ciblée Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the four highest-value gaps flagged by the SP-0d.5a/b/d final reviews: the theme's `--gs-color-muted`/`--gs-color-border`/`--gs-color-text` tokens are unused by most builtin widgets; `ActionsPanel` shows cross-page messages with broken-looking labels when switching pages; `setPageLayout` silently mutates the wrong page on an invalid `pageId`; and `AppRuntimePage`'s route push doesn't percent-encode its path segments.

**Architecture:** Four independent, additive fixes, each scoped to the file(s) that already own the behavior — no new modules, no schema changes, no cross-cutting refactor. Each task is a mechanical edit plus a regression test proving the specific gap is closed.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library; no new dependency.

## Global Constraints

- Additive/behavior-preserving: every fix must leave all currently-passing tests green with no assertion changes other than the ones this plan adds.
- Front: no new service URL, no new dependency.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`).

**Scope note:** The Carte (map) widget is intentionally **not** touched by Task 1. Its `Component` has no synchronously-reachable, currently-tested neutral/muted text element to retheme — the only text it renders outside the map canvas itself is the error state (`text-red-600`, deliberately left unthemed everywhere in this codebase, matching Bouton/Texte/Liste/Table/Indicateur/Filtre/Graphique's own error text) and a `Suspense` fallback that only renders while the lazy `MapView` import is pending, which is not reliably observable from a jsdom unit test. Re-theming it would mean touching untested, Suspense-timing-dependent code for no visible gain — skipped rather than faked.

---

### Task 1: Extend theme tokens to Liste, Table, Indicateur, Filtre, Graphique

**Files:**
- Modify: `shell/src/builder/widgets/data.tsx`
- Modify: `shell/src/builder/widgets/indicator.tsx`
- Modify: `shell/src/builder/widgets/filter.tsx`
- Modify: `shell/src/builder/widgets/chart.tsx`
- Test: `shell/src/builder/widgets/data.test.tsx` (extend), `shell/src/builder/widgets/indicator.test.tsx` (extend), `shell/src/builder/widgets/filter.test.tsx` (extend), `shell/src/builder/widgets/chart.test.tsx` (extend)

**Interfaces:**
- Consumes: the `--gs-color-text`/`--gs-color-muted`/`--gs-color-border` CSS custom properties (already applied on `AppRenderer`'s root by SP-0d.5d) — no new interface.
- Produces: no new interface. Each widget's rendered classNames swap hardcoded `slate-*` colors for the matching `--gs-*` token, following the exact pattern already used by the canvas backdrop/Bouton/Texte in SP-0d.5d Task 3.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/builder/widgets/data.test.tsx`:

```tsx
test("list item uses the theme border/surface/text tokens", () => {
  const List = getWidget("list")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "Parc A" } }] }) } as WidgetContext;
  render(<List props={{ titleField: "nom" }} ctx={ctx} />);
  expect(screen.getByText("Parc A")).toHaveClass(
    "border-[var(--gs-color-border)]",
    "text-[var(--gs-color-text)]",
    "hover:bg-[var(--gs-color-surface)]",
  );
});

test("table cells and headers use the theme border/text tokens", () => {
  const Table = getWidget("table")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: { nom: "A" } }] }) } as WidgetContext;
  render(<Table props={{ dataSourceId: "d", columns: ["nom"] }} ctx={ctx} />);
  expect(screen.getByRole("cell", { name: "A" })).toHaveClass("border-[var(--gs-color-border)]");
  expect(screen.getByRole("table")).toHaveClass("text-[var(--gs-color-text)]");
});
```

Append to `shell/src/builder/widgets/indicator.test.tsx`:

```tsx
test("indicator uses the theme text/muted tokens", () => {
  const Ind = getWidget("indicator")!.Component;
  const ctx = { mode: "runtime", data: state({ records: [{ id: 1, properties: {} }] }) } as WidgetContext;
  render(<Ind props={{ label: "Total" }} ctx={ctx} />);
  expect(screen.getByText("1")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByText("Total")).toHaveClass("text-[var(--gs-color-muted)]");
});
```

Append to `shell/src/builder/widgets/filter.test.tsx`:

```tsx
test("filter label and input use the theme text/border tokens", () => {
  const Filter = getWidget("filter")!.Component;
  render(<Filter props={{ label: "Rechercher" }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("Rechercher")).toHaveClass("text-[var(--gs-color-text)]");
  expect(screen.getByLabelText("Valeur du filtre")).toHaveClass("border-[var(--gs-color-border)]");
});
```

Append to `shell/src/builder/widgets/chart.test.tsx`:

```tsx
test("loading and empty states use the theme muted token", () => {
  const Chart = getWidget("chart")!.Component;
  const { rerender } = render(<Chart props={{}} ctx={{ mode: "runtime", data: state({ loading: true }) } as WidgetContext} />);
  expect(screen.getByText(/chargement/i)).toHaveClass("text-[var(--gs-color-muted)]");
  rerender(<Chart props={{}} ctx={{ mode: "runtime", data: state() } as WidgetContext} />);
  expect(screen.getByText(/aucune donnée/i)).toHaveClass("text-[var(--gs-color-muted)]");
});
```

- [ ] **Step 2: Run to verify they fail**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx src/builder/widgets/indicator.test.tsx src/builder/widgets/filter.test.tsx src/builder/widgets/chart.test.tsx`
Expected: FAIL — none of the four widgets carry the new classes yet.

- [ ] **Step 3: Swap Liste's and Table's classes**

Edit `shell/src/builder/widgets/data.tsx`. In the `list` widget's `Component`, change both loading/empty lines:

```tsx
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
```

to:

```tsx
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
```

Then change the `<li>` className:

```tsx
              className="cursor-pointer truncate border-b border-slate-100 py-0.5 hover:bg-slate-50"
```

to:

```tsx
              className="cursor-pointer truncate border-b border-[var(--gs-color-border)] py-0.5 text-[var(--gs-color-text)] hover:bg-[var(--gs-color-surface)]"
```

In the `table` widget's `Component`, change its own loading/empty lines the same way:

```tsx
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
```

to:

```tsx
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
```

Then change the table markup:

```tsx
          <table className="w-full text-left">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b p-1">
```

to:

```tsx
          <table className="w-full text-left text-[var(--gs-color-text)]">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th key={c} className="border-b border-[var(--gs-color-border)] p-1">
```

Then change the data cell and pagination classNames:

```tsx
                  {columns.map((c) => <td key={c} className="border-b border-slate-100 p-1">{String(r.properties[c] ?? "")}</td>)}
```

to:

```tsx
                  {columns.map((c) => <td key={c} className="border-b border-[var(--gs-color-border)] p-1">{String(r.properties[c] ?? "")}</td>)}
```

and:

```tsx
            <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-slate-500">
              <button type="button" className="rounded border border-slate-300 px-1 disabled:opacity-40"
                disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
              <span>Page {current + 1} / {pageCount}</span>
              <button type="button" className="rounded border border-slate-300 px-1 disabled:opacity-40"
                disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
            </div>
```

to:

```tsx
            <div className="mt-auto flex items-center justify-between pt-1 text-[10px] text-[var(--gs-color-muted)]">
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current === 0} onClick={() => setPage(current - 1)}>Précédent</button>
              <span>Page {current + 1} / {pageCount}</span>
              <button type="button" className="rounded border border-[var(--gs-color-border)] px-1 disabled:opacity-40"
                disabled={current >= pageCount - 1} onClick={() => setPage(current + 1)}>Suivant</button>
            </div>
```

- [ ] **Step 4: Swap Indicateur's classes**

Edit `shell/src/builder/widgets/indicator.tsx`. Change:

```tsx
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;
```

to:

```tsx
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur</p>;
```

Then change:

```tsx
        <div className="flex h-full flex-col items-center justify-center">
          <span className="text-2xl font-semibold">{value}</span>
          <span className="text-xs text-slate-500">{String(props.label ?? "")}</span>
        </div>
```

to:

```tsx
        <div className="flex h-full flex-col items-center justify-center">
          <span className="text-2xl font-semibold text-[var(--gs-color-text)]">{value}</span>
          <span className="text-xs text-[var(--gs-color-muted)]">{String(props.label ?? "")}</span>
        </div>
```

- [ ] **Step 5: Swap Filtre's classes**

Edit `shell/src/builder/widgets/filter.tsx`. Change:

```tsx
        <label className="flex flex-col gap-1 text-sm">
          {String(props.label ?? "Filtrer")}
          <input
            aria-label="Valeur du filtre"
            className="h-9 rounded-md border border-slate-300 px-2"
```

to:

```tsx
        <label className="flex flex-col gap-1 text-sm text-[var(--gs-color-text)]">
          {String(props.label ?? "Filtrer")}
          <input
            aria-label="Valeur du filtre"
            className="h-9 rounded-md border border-[var(--gs-color-border)] px-2"
```

- [ ] **Step 6: Swap Graphique's loading/empty classes**

Edit `shell/src/builder/widgets/chart.tsx`. Change:

```tsx
      if (!data || data.loading) return <p className="text-xs text-slate-400">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-slate-400">Aucune donnée</p>;
```

to:

```tsx
      if (!data || data.loading) return <p className="text-xs text-[var(--gs-color-muted)]">Chargement…</p>;
      if (data.error) return <p className="text-xs text-red-600">Erreur de données</p>;
      if (data.records.length === 0) return <p className="text-xs text-[var(--gs-color-muted)]">Aucune donnée</p>;
```

(The `Suspense` fallback text `"Graphique…"` stays as-is — see this plan's Scope note.)

- [ ] **Step 7: Run to verify they pass**

Run: `cd shell && npx vitest run src/builder/widgets/data.test.tsx src/builder/widgets/indicator.test.tsx src/builder/widgets/filter.test.tsx src/builder/widgets/chart.test.tsx`
Expected: PASS.

- [ ] **Step 8: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/widgets/data.tsx shell/src/builder/widgets/data.test.tsx shell/src/builder/widgets/indicator.tsx shell/src/builder/widgets/indicator.test.tsx shell/src/builder/widgets/filter.tsx shell/src/builder/widgets/filter.test.tsx shell/src/builder/widgets/chart.tsx shell/src/builder/widgets/chart.test.tsx
git commit -m "fix(shell): extend theme tokens to Liste/Table/Indicateur/Filtre/Graphique

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `ActionsPanel` only lists messages resolvable on the current page

**Files:**
- Modify: `shell/src/builder/ActionsPanel.tsx`
- Test: `shell/src/builder/ActionsPanel.test.tsx` (extend)

**Interfaces:**
- Consumes: `items: WidgetItem[]` (already the active page's items, per SP-0d.5b's `AppBuilderPage` wiring — no caller change needed).
- Produces: no signature change. The displayed/editable message list now hides any `ActionMessage` whose `from` or `to` isn't one of the current `items` — it does **not** delete anything from `config.messages` (switching back to the page where both endpoints live shows the message again, unchanged).

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/ActionsPanel.test.tsx`:

```tsx
test("hides a message whose endpoints are not on the current page", () => {
  const messages: ActionMessage[] = [
    { id: "m1", from: "f1", event: "changed", to: "l1", action: "setFilter" },
    { id: "m2", from: "ghost", event: "changed", to: "l1", action: "setFilter" },
  ];
  render(<ActionsPanel items={items} messages={messages} onChange={vi.fn()} />);
  expect(screen.getByText("Filtre.changed → Liste.setFilter")).toBeInTheDocument();
  expect(screen.queryByText(/ghost/)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/ActionsPanel.test.tsx`
Expected: FAIL — `m2` still renders as `"ghost.changed → Liste.setFilter"`.

- [ ] **Step 3: Filter the displayed list**

Edit `shell/src/builder/ActionsPanel.tsx`. Add a helper right after the existing `actionsOf` function:

```ts
function isOnThisPage(items: WidgetItem[], id: string): boolean {
  return items.some((i) => i.id === id);
}
```

Inside the `ActionsPanel` component, right after the `emitters`/`receivers` declarations, add:

```ts
  const visibleMessages = messages.filter(
    (m) => isOnThisPage(items, m.from) && isOnThisPage(items, m.to),
  );
```

Then change the rendered list from:

```tsx
      <ul className="flex flex-col gap-1">
        {messages.map((m) => (
          <li key={m.id} className="flex items-center justify-between rounded border border-slate-200 p-1 text-xs">
            <span>{widgetLabel(items, m.from)}.{m.event} → {widgetLabel(items, m.to)}.{m.action}</span>
            <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
          </li>
        ))}
        {messages.length === 0 && <li className="text-xs text-slate-400">Aucune action.</li>}
      </ul>
```

to:

```tsx
      <ul className="flex flex-col gap-1">
        {visibleMessages.map((m) => (
          <li key={m.id} className="flex items-center justify-between rounded border border-slate-200 p-1 text-xs">
            <span>{widgetLabel(items, m.from)}.{m.event} → {widgetLabel(items, m.to)}.{m.action}</span>
            <button type="button" aria-label={`Retirer l'action ${m.id}`} className="text-red-600" onClick={() => remove(m.id)}>✕</button>
          </li>
        ))}
        {visibleMessages.length === 0 && <li className="text-xs text-slate-400">Aucune action.</li>}
      </ul>
```

`remove(id)` is unchanged — it still filters the full `messages` prop by `id`, so removing a message that happens to be hidden on the current page still works correctly if the button is ever reachable (it isn't, today, since a hidden message's remove button isn't rendered — this is intentionally conservative: nothing you can't see gets deleted from here).

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/ActionsPanel.test.tsx`
Expected: PASS (3/3). The two pre-existing tests are unaffected — both `m1`/`f1`→`l1` messages there already resolve within `items`.

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/ActionsPanel.tsx shell/src/builder/ActionsPanel.test.tsx
git commit -m "fix(shell): ActionsPanel only shows messages resolvable on the active page

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `setPageLayout` ignores an unrelated `pageId` on an implicit-page config

**Files:**
- Modify: `shell/src/builder/pages.ts`
- Test: `shell/src/builder/pages.test.ts` (extend)

**Interfaces:**
- No signature change to `setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig`. Behavior change only: when `config.pages` is absent/empty (the config has exactly one implicit page, `"page-1"`), a `pageId` that doesn't match the implicit page's id is now a no-op (returns `config` unchanged, by reference) instead of overwriting `layout` regardless.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/pages.test.ts`:

```ts
test("setPageLayout on an implicit-page config ignores an unrelated pageId", () => {
  const newLayout: AppLayout = { type: "grid", breakpoints: {}, items: [] };
  const next = setPageLayout(baseConfig, "not-a-real-page", newLayout);
  expect(next).toBe(baseConfig);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/pages.test.ts`
Expected: FAIL — `setPageLayout` currently overwrites `layout` for any `pageId` on an implicit-page config.

- [ ] **Step 3: Guard the implicit-page branch**

Edit `shell/src/builder/pages.ts`. Change:

```ts
export function setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig {
  if (!config.pages || config.pages.length === 0) {
    return { ...config, layout };
  }
  const pages = config.pages.map((p) => (p.id === pageId ? { ...p, layout } : p));
  return { ...config, pages, layout: pages[0].layout };
}
```

to:

```ts
export function setPageLayout(config: AppConfig, pageId: string, layout: AppLayout): AppConfig {
  if (!config.pages || config.pages.length === 0) {
    if (pageId !== IMPLICIT_PAGE_ID) return config;
    return { ...config, layout };
  }
  const pages = config.pages.map((p) => (p.id === pageId ? { ...p, layout } : p));
  return { ...config, pages, layout: pages[0].layout };
}
```

(`IMPLICIT_PAGE_ID` is already defined at the top of this file — no new import.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/pages.test.ts`
Expected: PASS (7/7). The existing "on an implicit-page config only updates the top-level layout" test still passes — it calls `setPageLayout(baseConfig, "page-1", newLayout)`, and `"page-1"` **is** `IMPLICIT_PAGE_ID`.

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/pages.ts shell/src/builder/pages.test.ts
git commit -m "fix(shell): setPageLayout ignores an unrelated pageId on an implicit-page config

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `AppRuntimePage` percent-encodes the route it navigates to

**Files:**
- Modify: `shell/src/pages/AppRuntimePage.tsx`
- Test: `shell/src/pages/AppRuntimePage.test.tsx` (new)

**Interfaces:**
- No signature change to `AppRuntimePage({ pk: string, pageId?: string })`. Behavior change only: the route pushed on navigation is built with `encodeURIComponent` on both `pk` and the target `pageId`, so a `pageId` containing characters like `/`, `#`, `?`, or spaces produces a single, well-formed path segment instead of corrupting the route.

- [ ] **Step 1: Write the failing test**

Create `shell/src/pages/AppRuntimePage.test.tsx`:

```tsx
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRuntimePage } from "./AppRuntimePage";

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };
const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} },
  ] },
  pages: [
    { id: "page-1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
      { id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} },
    ] } },
    { id: "a/b", name: "Détails", layout: emptyLayout },
  ],
};

function LocationDisplay() {
  const location = useLocation();
  return <p data-testid="loc">{location.pathname}</p>;
}

function renderRuntime(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/apps/9/page-1"]}>
          <AppRuntimePage pk="9" pageId="page-1" />
          <LocationDisplay />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Détails" }));
  expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/a%2Fb");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: FAIL — the resulting path is `/apps/9/a/b` (broken into two segments) instead of `/apps/9/a%2Fb`.

- [ ] **Step 3: Encode the route push**

Edit `shell/src/pages/AppRuntimePage.tsx`. Change:

```tsx
        onNavigate={(nextPageId) => navigate(`/apps/${pk}/${nextPageId}`)}
```

to:

```tsx
        onNavigate={(nextPageId) => navigate(`/apps/${encodeURIComponent(pk)}/${encodeURIComponent(nextPageId)}`)}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/AppRuntimePage.test.tsx`
Expected: PASS.

- [ ] **Step 5: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/pages/AppRuntimePage.tsx shell/src/pages/AppRuntimePage.test.tsx
git commit -m "fix(shell): AppRuntimePage percent-encodes pk/pageId in its route push

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (the four items the user confirmed for this plan's scope):** theme token coverage on remaining widgets → Task 1 (Liste/Table/Indicateur/Filtre/Graphique; Carte explicitly excluded with a documented reason in the Scope note, since forcing an untestable change would violate this skill's "no placeholders / no faked coverage" rule). Cross-page action scoping → Task 2 (display-only filter, no destructive mutation). `pageId` validation → Task 3. `encodeURIComponent` → Task 4.
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor; the one deliberately-skipped item (Carte's Suspense fallback) is explained, not silently dropped.
- **Type consistency:** no type changes in this plan — every task edits existing, already-typed functions/components without touching their signatures. `isOnThisPage(items: WidgetItem[], id: string): boolean` is a new private helper, consistent with `WidgetItem` from `../api/types` already imported by `ActionsPanel.tsx`.
- **Backward compatibility:** Task 1 changes classNames only, no markup/behavior change — pre-existing tests asserting text content (not classNames) are unaffected. Task 2's filter is a no-op for every existing test fixture (all pre-existing `messages` already resolve within their `items`). Task 3's guard only changes behavior for a `pageId` that was never valid to begin with (no test or call site relies on the old overwrite-anything behavior — confirmed by grepping `setPageLayout(` call sites: `AppRenderer.tsx`'s `handleMove` and `AppBuilderPage.tsx`'s `addWidget`/`updateSelectedProps` all pass `activePageId`, which is always resolved via `getPages(config)[0].id` or a real page's id, never an arbitrary string). Task 4 changes the URL's exact bytes only when `pk`/`pageId` contain characters needing escaping — today's ids (`crypto.randomUUID()`, numeric `pk`) are already safe under `encodeURIComponent` (letters/digits/hyphens pass through unchanged), so no existing E2E assertion on a literal URL breaks.
- **Façade discipline:** no network access added or changed in any task.
- **Engine unity:** untouched — none of these four fixes are mode-specific; they apply identically in edit/preview/runtime (Tasks 1–3) or are runtime-only by construction (Task 4, `AppRuntimePage` only exists in runtime).
