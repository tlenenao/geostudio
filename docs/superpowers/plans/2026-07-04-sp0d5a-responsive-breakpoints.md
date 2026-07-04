# GeoStudio SP-0d.5a — Responsive par breakpoint — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre les apps du builder responsives — chaque widget peut avoir des positions par breakpoint (`sm`/`md`/`lg`), éditées via un sélecteur de breakpoint et choisies automatiquement au runtime selon la largeur.

**Architecture:** On étend `WidgetItem` d'un champ additif `layouts?: { [bp]: {x,y,w,h} }` ; `x/y/w/h` reste la position par défaut (breakpoint `lg`). Des helpers purs dans `grid.ts` (`posFor`, `moveItemAt`, `breakpointForWidth`) calculent la position effective à un breakpoint et écrivent au bon endroit. `GridCanvas` rend à un breakpoint donné ; `AppRenderer` fournit le breakpoint — **contrôlé** par une prop en édition (sélecteur de la toolbar), **auto-détecté** via `ResizeObserver` au runtime. Le backend Pydantic accepte `layouts` (additif) pour que le round-trip le conserve.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright ; FastAPI + Pydantic (builder-service).

## Global Constraints

- Extensions **additives** : `Item`/`ItemClient`/`AppConfig`/`WidgetItem` étendus sans rupture ; les configs SP-0d.1–0d.4 (sans `layouts`) restent valides et rendues à l'identique.
- `x/y/w/h` = position par défaut = breakpoint `lg` ; `layouts.sm`/`layouts.md` sont des surcharges optionnelles retombant sur la base.
- Breakpoints : `lg` (largeur ≥ 1024), `md` (≥ 640 et < 1024), `sm` (< 640).
- Un seul moteur `AppRenderer` pour edit/preview/runtime — même choix de position.
- Front : aucun accès réseau nouveau. Backend : `LayoutItem.layouts` additif (`builder-service/app/schemas.py`), configs existants valides ; stockage via `model_dump(by_alias=True)` / lecture via `BuilderConfig.model_validate`.
- L'environnement de test unitaire (jsdom) **n'a pas** `ResizeObserver` ; l'auto-détection doit être gardée (`typeof ResizeObserver === "undefined"` → défaut `lg`) et est couverte en E2E (vrai navigateur).
- MSW `onUnhandledRequest:"error"` ; pas de token en localStorage.
- Commits terminés par : `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`.
- Branche `dev`. Commandes front depuis `shell/` (`cd shell && ...`), backend depuis `builder-service/`.

---

### Task 1: `WidgetItem.layouts` + helpers de grille par breakpoint

**Files:**
- Modify: `shell/src/api/types.ts`
- Modify: `shell/src/builder/grid.ts`
- Test: `shell/src/builder/grid.test.ts`

**Interfaces:**
- Produces:
  - `WidgetItem.layouts?: Partial<Record<"sm" | "md" | "lg", { x: number; y: number; w: number; h: number }>>`
  - `BREAKPOINTS = ["sm", "md", "lg"] as const` ; `type Breakpoint = "sm" | "md" | "lg"` ; `type Pos = { x: number; y: number; w: number; h: number }`
  - `posFor(item: WidgetItem, bp: Breakpoint): Pos` — `lg` → base `x/y/w/h` ; `md`/`sm` → `item.layouts?.[bp]` sinon base.
  - `styleForPos(pos: Pos): CSSProperties`
  - `moveItemAt(item: WidgetItem, bp: Breakpoint, dxCells: number, dyCells: number): WidgetItem` — écrit `x/y` à `lg`, `layouts[bp]` à `md`/`sm` (sans toucher les autres breakpoints), clampe sur la grille.
  - `breakpointForWidth(width: number): Breakpoint`
- Consumes: `GRID_COLS` (existant).

- [ ] **Step 1: Add the `layouts` field to `WidgetItem`**

Edit `shell/src/api/types.ts`. Replace the `WidgetItem` type:

```ts
export type WidgetItem = {
  id: string;
  widget: string;
  x: number;
  y: number;
  w: number;
  h: number;
  props: Record<string, unknown>;
  layouts?: Partial<Record<"sm" | "md" | "lg", { x: number; y: number; w: number; h: number }>>;
};
```

- [ ] **Step 2: Write the failing grid-helper tests**

Append to `shell/src/builder/grid.test.ts`:

```ts
import { posFor, styleForPos, moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";

const baseItem = { id: "a", widget: "text", x: 2, y: 3, w: 4, h: 2, props: {} };

test("posFor returns the base position at lg", () => {
  expect(posFor(baseItem, "lg")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("posFor falls back to the base position when a breakpoint has no override", () => {
  expect(posFor(baseItem, "sm")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("posFor uses the per-breakpoint override when present", () => {
  const item = { ...baseItem, layouts: { sm: { x: 0, y: 5, w: 12, h: 2 } } };
  expect(posFor(item, "sm")).toEqual({ x: 0, y: 5, w: 12, h: 2 });
  expect(posFor(item, "lg")).toEqual({ x: 2, y: 3, w: 4, h: 2 });
});

test("styleForPos maps a position to grid CSS", () => {
  expect(styleForPos({ x: 2, y: 3, w: 4, h: 2 })).toEqual({
    gridColumn: "3 / span 4",
    gridRow: "4 / span 2",
  });
});

test("moveItemAt writes the base position at lg", () => {
  const moved = moveItemAt(baseItem, "lg", 1, -1);
  expect(moved.x).toBe(3);
  expect(moved.y).toBe(2);
  expect(moved.layouts).toBeUndefined();
});

test("moveItemAt writes a per-breakpoint override at sm and keeps the base intact", () => {
  const moved = moveItemAt(baseItem, "sm", 1, 0);
  expect(moved.x).toBe(2); // base untouched
  expect(moved.layouts?.sm).toEqual({ x: 3, y: 3, w: 4, h: 2 });
});

test("moveItemAt preserves other breakpoints' overrides", () => {
  const item = { ...baseItem, layouts: { md: { x: 1, y: 1, w: 6, h: 2 } } };
  const moved = moveItemAt(item, "sm", 1, 0);
  expect(moved.layouts?.md).toEqual({ x: 1, y: 1, w: 6, h: 2 });
  expect(moved.layouts?.sm).toEqual({ x: 3, y: 3, w: 4, h: 2 });
});

test("moveItemAt clamps within the grid", () => {
  const moved = moveItemAt(baseItem, "lg", 100, -100);
  expect(moved.x).toBe(12 - 4); // GRID_COLS - w
  expect(moved.y).toBe(0);
});

test("breakpointForWidth maps widths to breakpoints", () => {
  expect(breakpointForWidth(1280)).toBe<Breakpoint>("lg");
  expect(breakpointForWidth(1024)).toBe<Breakpoint>("lg");
  expect(breakpointForWidth(800)).toBe<Breakpoint>("md");
  expect(breakpointForWidth(640)).toBe<Breakpoint>("md");
  expect(breakpointForWidth(500)).toBe<Breakpoint>("sm");
});
```

- [ ] **Step 3: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/grid.test.ts`
Expected: FAIL — new helpers not exported.

- [ ] **Step 4: Implement the helpers**

Edit `shell/src/builder/grid.ts`. Append (keep the existing `GRID_COLS`, `moveItem`, `resizeItem`, `styleFor`):

```ts
export const BREAKPOINTS = ["sm", "md", "lg"] as const;
export type Breakpoint = (typeof BREAKPOINTS)[number];
export type Pos = { x: number; y: number; w: number; h: number };

function basePos(item: WidgetItem): Pos {
  return { x: item.x, y: item.y, w: item.w, h: item.h };
}

// Effective position of an item at a breakpoint. `lg` is the base position
// (x/y/w/h); md/sm use their override if present, else fall back to the base.
export function posFor(item: WidgetItem, bp: Breakpoint): Pos {
  if (bp === "lg") return basePos(item);
  return item.layouts?.[bp] ?? basePos(item);
}

export function styleForPos(pos: Pos): CSSProperties {
  return {
    gridColumn: `${pos.x + 1} / span ${pos.w}`,
    gridRow: `${pos.y + 1} / span ${pos.h}`,
  };
}

// Move an item within a breakpoint: writes the base position at `lg`, or the
// per-breakpoint override at md/sm (leaving the base and other breakpoints
// untouched). Clamps to the grid.
export function moveItemAt(item: WidgetItem, bp: Breakpoint, dxCells: number, dyCells: number): WidgetItem {
  const cur = posFor(item, bp);
  const x = Math.max(0, Math.min(GRID_COLS - cur.w, cur.x + dxCells));
  const y = Math.max(0, cur.y + dyCells);
  if (bp === "lg") return { ...item, x, y };
  return { ...item, layouts: { ...item.layouts, [bp]: { ...cur, x, y } } };
}

export function breakpointForWidth(width: number): Breakpoint {
  if (width >= 1024) return "lg";
  if (width >= 640) return "md";
  return "sm";
}
```

- [ ] **Step 5: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/grid.test.ts`
Expected: PASS (existing `moveItem`/`resizeItem`/`styleFor` tests still pass — those functions are untouched).

- [ ] **Step 6: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/api/types.ts shell/src/builder/grid.ts shell/src/builder/grid.test.ts
git commit -m "feat(shell): per-breakpoint layout helpers (posFor/moveItemAt/breakpointForWidth)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: `GridCanvas` rend à un breakpoint donné

**Files:**
- Modify: `shell/src/builder/GridCanvas.tsx`
- Test: `shell/src/builder/GridCanvas.test.tsx`

**Interfaces:**
- Consumes: `posFor`, `styleForPos`, `Breakpoint` (Task 1).
- Produces: `GridCanvas` gains a **required** prop `breakpoint: Breakpoint`. It positions each item via `posFor(item, breakpoint)`, exposes `data-breakpoint` on the grid container and `data-col`/`data-row` on each item wrapper (test/E2E hooks). `onMoveItem(id, dx, dy)` signature unchanged.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/GridCanvas.test.tsx`:

```tsx
import { posFor } from "./grid";

test("positions items at the active breakpoint and exposes data hooks", () => {
  const bpItems: WidgetItem[] = [
    { id: "a", widget: "text", x: 0, y: 0, w: 4, h: 2, props: {}, layouts: { sm: { x: 5, y: 1, w: 6, h: 2 } } },
  ];
  const { container } = render(
    <GridCanvas
      items={bpItems}
      breakpoint="sm"
      editable={false}
      selectedId={null}
      onSelect={vi.fn()}
      onMoveItem={vi.fn()}
      renderItem={(item) => <div>widget-{item.id}</div>}
    />,
  );
  expect(container.querySelector("[data-breakpoint='sm']")).toBeInTheDocument();
  const wrapper = container.querySelector("[data-col]");
  expect(wrapper).toHaveAttribute("data-col", "5"); // sm override, not base 0
  expect(wrapper).toHaveAttribute("data-row", "1");
  // sanity: matches the pure helper
  expect(posFor(bpItems[0], "sm")).toEqual({ x: 5, y: 1, w: 6, h: 2 });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx`
Expected: FAIL — `breakpoint` prop unknown / no `data-breakpoint`/`data-col`. (Existing tests also fail to type-check because `breakpoint` is now required — fixed in Step 3.)

- [ ] **Step 3: Make `GridCanvas` breakpoint-aware**

Replace `shell/src/builder/GridCanvas.tsx` with:

```tsx
import type { ReactNode } from "react";
import type { WidgetItem } from "../api/types";
import { GRID_COLS, posFor, styleForPos, type Breakpoint } from "./grid";

export function GridCanvas({
  items,
  breakpoint,
  editable,
  selectedId,
  onSelect,
  onMoveItem,
  renderItem,
}: {
  items: WidgetItem[];
  breakpoint: Breakpoint;
  editable: boolean;
  selectedId: string | null;
  onSelect: (id: string | null) => void;
  onMoveItem: (id: string, dxCells: number, dyCells: number) => void;
  renderItem: (item: WidgetItem) => ReactNode;
}) {
  return (
    <div
      className="grid h-full w-full gap-1 bg-slate-50"
      data-breakpoint={breakpoint}
      style={{ gridTemplateColumns: `repeat(${GRID_COLS}, 1fr)`, gridAutoRows: "40px" }}
      onClick={() => editable && onSelect(null)}
    >
      {items.map((item) => {
        const pos = posFor(item, breakpoint);
        const selected = editable && item.id === selectedId;
        return (
          <div
            key={item.id}
            data-col={pos.x}
            data-row={pos.y}
            style={styleForPos(pos)}
            className={`relative overflow-hidden rounded ${selected ? "outline outline-2 outline-blue-500" : ""}`}
          >
            {editable && (
              <button
                type="button"
                aria-label={`Sélectionner widget-${item.id}`}
                className="absolute inset-0 z-10 cursor-pointer"
                onClick={(e) => {
                  e.stopPropagation();
                  onSelect(item.id);
                }}
              />
            )}
            <div className="pointer-events-none h-full w-full p-1">{renderItem(item)}</div>
            {selected && (
              <div className="absolute right-0 top-0 z-20 flex gap-0.5">
                <button type="button" aria-label={`Déplacer widget-${item.id} à gauche`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, -1, 0); }}>←</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} à droite`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 1, 0); }}>→</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} en bas`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 0, 1); }}>↓</button>
                <button type="button" aria-label={`Déplacer widget-${item.id} en haut`}
                  className="bg-blue-500 px-1 text-xs text-white" onClick={(e) => { e.stopPropagation(); onMoveItem(item.id, 0, -1); }}>↑</button>
              </div>
            )}
          </div>
        );
      })}
    </div>
  );
}
```

- [ ] **Step 4: Fix the existing GridCanvas tests to pass a breakpoint**

Edit `shell/src/builder/GridCanvas.test.tsx` — add `breakpoint="lg"` to the `renderCanvas` helper's `<GridCanvas>` (so the three existing tests keep working):

```tsx
    <GridCanvas
      items={items}
      breakpoint="lg"
      editable
      selectedId={null}
      onSelect={over.onSelect ?? vi.fn()}
      onMoveItem={over.onMoveItem ?? vi.fn()}
      renderItem={(item) => <div>widget-{item.id}</div>}
      {...over}
    />,
```

- [ ] **Step 5: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/GridCanvas.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/GridCanvas.tsx shell/src/builder/GridCanvas.test.tsx
git commit -m "feat(shell): GridCanvas positions items per active breakpoint

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: `AppRenderer` — breakpoint contrôlé (édition) + auto-détecté (runtime)

**Files:**
- Modify: `shell/src/builder/AppRenderer.tsx`
- Test: `shell/src/builder/AppRenderer.test.tsx` (extend)

**Interfaces:**
- Consumes: `moveItemAt`, `breakpointForWidth`, `Breakpoint`, `posFor` (Task 1) ; `GridCanvas` `breakpoint` prop (Task 2).
- Produces: `AppRenderer` gains an optional prop `breakpoint?: Breakpoint`. When provided (editor), it is used directly. When absent (runtime), the component measures its container via `ResizeObserver` and derives the breakpoint (default `lg` if `ResizeObserver` is unavailable, e.g. jsdom). Edits route through `moveItemAt(item, activeBreakpoint, dx, dy)`.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/builder/AppRenderer.test.tsx` (it already imports `render`, `screen`, `userEvent`, `AppConfig`, `Wrapper`, `registerBuiltinWidgets`, `vi`; add nothing new):

```tsx
test("edits the sm layout when the breakpoint prop is sm, leaving the base intact", async () => {
  let latest: AppConfig | null = null;
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  render(
    <AppRenderer config={cfg} mode="edit" breakpoint="sm" selectedId="w1" onSelect={() => {}} onChange={(c) => { latest = c; }} />,
    { wrapper: Wrapper },
  );
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  expect(latest!.layout.items[0].x).toBe(0); // base untouched
  expect(latest!.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
});

test("renders the item at its sm override when breakpoint=sm", () => {
  const cfg: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" }, layouts: { sm: { x: 6, y: 2, w: 6, h: 2 } } },
    ] },
  };
  const { container } = render(<AppRenderer config={cfg} mode="runtime" breakpoint="sm" />, { wrapper: Wrapper });
  expect(container.querySelector("[data-col]")).toHaveAttribute("data-col", "6");
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx`
Expected: FAIL — `breakpoint` prop unknown / edits still write the base `x`.

- [ ] **Step 3: Wire the breakpoint into `AppRenderer`**

Replace `shell/src/builder/AppRenderer.tsx` with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import type { AppConfig, RenderMode } from "../api/types";
import { GridCanvas } from "./GridCanvas";
import { WidgetHost } from "./WidgetHost";
import { moveItemAt, breakpointForWidth, type Breakpoint } from "./grid";
import { DataProvider } from "./DataContext";
import { ActionBus } from "./ActionBus";
import { ActionBusProvider } from "./ActionBusContext";

export function AppRenderer({
  config,
  mode,
  onChange,
  selectedId = null,
  onSelect,
  breakpoint,
}: {
  config: AppConfig;
  mode: RenderMode;
  onChange?: (config: AppConfig) => void;
  selectedId?: string | null;
  onSelect?: (id: string | null) => void;
  breakpoint?: Breakpoint;
}) {
  const editable = mode === "edit";
  const bus = useMemo(() => new ActionBus(), []);
  useEffect(() => {
    bus.configure(config.messages);
  }, [bus, config.messages]);

  // When no breakpoint is controlled (runtime/preview without a switcher),
  // auto-detect from the container width. jsdom has no ResizeObserver → keep lg.
  const containerRef = useRef<HTMLDivElement>(null);
  const [autoBp, setAutoBp] = useState<Breakpoint>("lg");
  useEffect(() => {
    if (breakpoint) return;
    const el = containerRef.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const update = () => setAutoBp(breakpointForWidth(el.clientWidth));
    update();
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => ro.disconnect();
  }, [breakpoint]);
  const bp = breakpoint ?? autoBp;

  function handleMove(id: string, dx: number, dy: number) {
    if (!onChange) return;
    onChange({
      ...config,
      layout: {
        ...config.layout,
        items: config.layout.items.map((it) => (it.id === id ? moveItemAt(it, bp, dx, dy) : it)),
      },
    });
  }

  return (
    <div ref={containerRef} className="h-full w-full">
      <ActionBusProvider bus={bus}>
        <DataProvider sources={config.dataSources}>
          <GridCanvas
            items={config.layout.items}
            breakpoint={bp}
            editable={editable}
            selectedId={selectedId}
            onSelect={(id) => onSelect?.(id)}
            onMoveItem={handleMove}
            renderItem={(item) => <WidgetHost item={item} mode={mode} />}
          />
        </DataProvider>
      </ActionBusProvider>
    </div>
  );
}
```

- [ ] **Step 4: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/AppRenderer.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (Existing AppRenderer tests pass no `breakpoint` → `autoBp` stays `lg` → `posFor(lg)` = base → unchanged rendering; `handleMove` at `lg` writes `x/y` exactly like the old `moveItem`.)

```bash
git add shell/src/builder/AppRenderer.tsx shell/src/builder/AppRenderer.test.tsx
git commit -m "feat(shell): AppRenderer picks breakpoint (controlled in edit, auto at runtime)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Sélecteur de breakpoint dans la toolbar du builder

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Test: `shell/src/pages/AppBuilderPage.test.tsx` (extend)

**Interfaces:**
- Consumes: `AppRenderer` `breakpoint` prop (Task 3), `BREAKPOINTS`/`Breakpoint` (Task 1).
- Produces: `AppBuilderPage` holds a `breakpoint` state (default `"lg"`), renders three switch buttons (`aria-label` `Éditer en sm|md|lg`) in the toolbar, and passes `breakpoint` to `AppRenderer`. Editing at a non-`lg` breakpoint persists `layouts[bp]` on save.

- [ ] **Step 1: Write the failing test**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (reuses the existing `renderPage`, `screen`, `userEvent`, `waitFor`, `vi`, `AppConfig`):

```tsx
test("edits a position at the sm breakpoint and persists layouts.sm", async () => {
  const withItem: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Éditer en sm" }));
  await userEvent.click(screen.getByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0); // base untouched
  expect(saved.layout.items[0].layouts?.sm).toEqual({ x: 1, y: 0, w: 4, h: 2 });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — no "Éditer en sm" button.

- [ ] **Step 3: Add the breakpoint switcher**

Edit `shell/src/pages/AppBuilderPage.tsx`.

Add to the imports:

```tsx
import { BREAKPOINTS, type Breakpoint } from "../builder/grid";
```

Add state next to the other `useState` hooks:

```tsx
  const [breakpoint, setBreakpoint] = useState<Breakpoint>("lg");
```

In the toolbar, after the Aperçu button and before the `<div className="flex-1" />`, add the switcher:

```tsx
        <div className="ml-2 flex items-center gap-1">
          {BREAKPOINTS.map((bp) => (
            <Button
              key={bp}
              size="sm"
              variant={breakpoint === bp ? "default" : "outline"}
              aria-label={`Éditer en ${bp}`}
              onClick={() => setBreakpoint(bp)}
            >
              {bp}
            </Button>
          ))}
        </div>
```

Pass the breakpoint to the renderer — update the `<AppRenderer .../>` in the `<main>`:

```tsx
          <AppRenderer
            config={draft}
            mode={mode}
            onChange={setDraft}
            selectedId={selectedId}
            onSelect={setSelectedId}
            breakpoint={breakpoint}
          />
```

- [ ] **Step 4: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (Existing AppBuilderPage tests never touch the switcher → default `lg`, unchanged behaviour.)

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): breakpoint switcher in the app builder toolbar

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Backend — `LayoutItem.layouts` round-trip

**Files:**
- Modify: `builder-service/app/schemas.py`
- Test: `builder-service/tests/test_schemas.py`

**Interfaces:**
- Produces: `LayoutItem.layouts: dict[str, dict] | None = None` — accepté et conservé par `BuilderConfig.model_validate` / `model_dump(by_alias=True)`, donc persistant via le repository. Configs sans `layouts` restent valides.

- [ ] **Step 1: Write the failing test**

Append to `builder-service/tests/test_schemas.py`:

```python
def test_layout_item_layouts_round_trip():
    payload = _valid_payload("app")
    payload["layout"]["items"][0]["layouts"] = {"sm": {"x": 1, "y": 2, "w": 6, "h": 3}}
    config = BuilderConfig.model_validate(payload)
    assert config.layout.items[0].layouts == {"sm": {"x": 1, "y": 2, "w": 6, "h": 3}}
    dumped = config.model_dump(by_alias=True)
    assert dumped["layout"]["items"][0]["layouts"]["sm"]["x"] == 1


def test_layout_item_layouts_optional():
    config = BuilderConfig.model_validate(_valid_payload("app"))
    assert config.layout.items[0].layouts is None
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd builder-service && python -m pytest tests/test_schemas.py -q`
Expected: FAIL — `layouts` is stripped (unknown field), so it never appears on the dumped item.

- [ ] **Step 3: Add `layouts` to `LayoutItem`**

Edit `builder-service/app/schemas.py`. In the `LayoutItem` model, add the field after `props`:

```python
class LayoutItem(BaseModel):
    id: str | None = None
    widget: str
    x: int
    y: int
    w: int
    h: int
    props: dict = Field(default_factory=dict)
    layouts: dict[str, dict] | None = None
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd builder-service && python -m pytest tests/test_schemas.py -q`
Expected: PASS.

- [ ] **Step 5: Run the full backend suite, then commit**

Run: `cd builder-service && python -m pytest -q`
Expected: all pass.

```bash
git add builder-service/app/schemas.py builder-service/tests/test_schemas.py
git commit -m "feat(builder-service): persist per-breakpoint LayoutItem.layouts (additive)

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: E2E — éditer une position par breakpoint, la voir au runtime

**Files:**
- Create: `shell/e2e/responsive.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existant), the toolbar switcher (Task 4), `data-breakpoint`/`data-col` hooks (Task 2), runtime auto-detect (Task 3).
- Produces: an E2E that creates an App, moves a widget at the `sm` breakpoint, saves, then verifies the runtime auto-selects `sm` at a narrow viewport (widget at its `sm` column) and `lg` at a wide viewport (base column).

- [ ] **Step 1: Write the E2E**

Create `shell/e2e/responsive.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("a per-breakpoint position is applied by the runtime at the matching viewport", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App responsive");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add a Text widget (lands at column 0).
  await page.getByRole("button", { name: "Texte" }).click();

  // Switch to the sm breakpoint and nudge the widget one column right.
  await page.getByRole("button", { name: "Éditer en sm" }).click();
  await page.getByLabel(/^Sélectionner widget-/).click();
  await page.getByLabel(/Déplacer widget-.* à droite/).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Narrow viewport → runtime auto-detects sm → widget at its sm column (1).
  await page.setViewportSize({ width: 500, height: 800 });
  await page.goto("/apps/9");
  await expect(page.locator("[data-breakpoint='sm']")).toBeVisible();
  await expect(page.locator("[data-col]").first()).toHaveAttribute("data-col", "1");

  // Wide viewport → runtime auto-detects lg → base column (0), unchanged.
  await page.setViewportSize({ width: 1280, height: 800 });
  await page.reload();
  await expect(page.locator("[data-breakpoint='lg']")).toBeVisible();
  await expect(page.locator("[data-col]").first()).toHaveAttribute("data-col", "0");
});
```

- [ ] **Step 2: Run the new E2E**

Run: `cd shell && npx playwright test responsive`
Expected: PASS — sm viewport shows `data-col="1"`, lg viewport shows `data-col="0"`.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/responsive.spec.ts
git commit -m "test(shell): E2E per-breakpoint layout applied by the runtime viewport

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design 0d.5 §5a « Responsive par breakpoint ») :** `LayoutItem.layouts` + `x/y/w/h` défaut → Task 1 (type + helpers) & Task 5 (backend persistant). Choix `layouts[bp]` par largeur via ResizeObserver (fallback base) → Task 3. Éditeur : sélecteur de breakpoint, édition écrivant `layouts[bp]` → Task 2 (rendu) + Task 4 (toolbar). Breakpoints lg≥1024/md≥640/sm<640 → `breakpointForWidth` (Task 1). Rendu responsive validé end-to-end → Task 6.
- **Placeholder scan :** aucun — chaque étape porte le code complet ou un edit exact contre une ancre citée.
- **Type consistency :** `Breakpoint = "sm"|"md"|"lg"`, `Pos`, `posFor`/`styleForPos`/`moveItemAt`/`breakpointForWidth`, `BREAKPOINTS` définis en Task 1 et consommés à l'identique par `GridCanvas` (Task 2), `AppRenderer` (Task 3), `AppBuilderPage` (Task 4). `WidgetItem.layouts?` (front) et `LayoutItem.layouts` (backend) portent la même forme `{ [bp]: {x,y,w,h} }`. `GridCanvas.breakpoint` requis ; `AppRenderer.breakpoint?` optionnel ; les data-hooks `data-breakpoint`/`data-col`/`data-row` sont produits en Task 2 et lus en Task 3/6.
- **Rétrocompatibilité :** `x/y/w/h` inchangés = `lg` ; les configs sans `layouts` rendent comme avant (Task 1 `posFor` fallback, Task 3 `autoBp` défaut `lg`, `handleMove` à `lg` = ancien `moveItem`). Les fonctions `moveItem`/`resizeItem`/`styleFor` existantes sont conservées (non supprimées). Backend additif (défaut `None`). Le seul test existant à ajuster est le helper `renderCanvas` de `GridCanvas.test.tsx` (prop `breakpoint` désormais requise) — corrigé en Task 2 Step 4.
- **jsdom / ResizeObserver :** l'auto-détection est gardée (`typeof ResizeObserver === "undefined"`) → tests unitaires stables sur `lg` ; l'auto-détection réelle est prouvée en E2E (Task 6, viewport Playwright).
