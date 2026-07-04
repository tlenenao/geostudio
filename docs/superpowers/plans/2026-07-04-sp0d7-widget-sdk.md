# GeoStudio SP-0d.7 — SDK widgets (briques) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to invoke this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give widget authors one stable, documented import surface instead of deep relative imports into `builder/registry.ts`/`ActionBusContext.tsx`/`DataContext.tsx`/`VariablesContext.tsx`, add a lightweight collision warning to `registerWidget`, and prove the whole thing works with one example widget that imports *only* that surface and is fully usable in the real app (palette, props, events, actions) with zero changes to any core file.

**Architecture:** The extension point already works today — `WidgetPalette`/`WidgetHost`/`PropsPanel`/`ActionsPanel` are all purely registry-driven (`listWidgets()`/`getWidget()`), with no `type`-string special-casing anywhere in the core. This plan does not change that mechanism; it packages it. `shell/src/builder/sdk.ts` is a new barrel module that re-exports the existing `WidgetDefinition`/`WidgetContext`/`registerWidget`/`getWidget`/`listWidgets` (from `registry.ts`), `useBusAction` (from `ActionBusContext.tsx`), `useSetFilter` (from `DataContext.tsx`), `useVariables`/`useSetVariable` (from `VariablesContext.tsx`), and the supporting types (`DataSource`, `DataSourceState`, `Page`, from `api/types.ts`) — nothing new is implemented there, only re-exported. `registerWidget` gains a one-line `console.warn` when a `type` is overwritten. A new example widget module, `shell/src/builder/examples/counterWidget.tsx`, imports exclusively from `./sdk` (not `../registry` etc.) and registers a small "Compteur" widget (a numeric prop, an emitted `changed` event, a receivable `reset` action) — registered the same way as the builtins, from a module that visibly lives outside `builder/widgets/`.

**Tech Stack:** React 19 + TS + Vite 6 + Vitest 3 + Testing Library + Playwright. No new dependency, no backend change.

## Global Constraints

- No behavior change for any existing widget: `registerWidget`'s new warning only fires on an actual `type` collision, and every builtin `type` string is already unique — the full existing suite must stay green with no assertion changes beyond what this plan adds.
- Extension is compile-time only: a widget registers itself by calling `registerWidget(...)` before the app mounts, from a module the app statically imports. No runtime-loaded/remote plugin mechanism is built in this plan (the repo has no monorepo or module-federation infrastructure to build on).
- `PropsPanel` stays free-form: no shared field components are introduced or required — the example widget hand-rolls its own form field, exactly like every existing widget already does.
- Commits end with: `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Work on branch `dev`. Run front-end commands from `shell/` (`cd shell && ...`).

**Scope note:** This plan ships exactly one example widget. It deliberately demonstrates props + an emitted event + a receivable action (the three pieces that make a widget interactive/wireable) — it does not touch `ctx.data` (data-source binding), because that requires zero widget-authored code to work (`WidgetHost` resolves `ctx.data` automatically for any widget whose props include a `dataSourceId` string; there is nothing an SDK contract needs to document beyond "name your prop `dataSourceId` and read `ctx.data`", already covered by the barrel re-exporting `DataSourceState`).

---

### Task 1: `sdk.ts` barrel export + collision-safe `registerWidget`

**Files:**
- Create: `shell/src/builder/sdk.ts`
- Test: `shell/src/builder/sdk.test.ts`
- Modify: `shell/src/builder/registry.ts`
- Test: `shell/src/builder/registry.test.tsx` (extend)

**Interfaces:**
- Produces:
  - `shell/src/builder/sdk.ts` re-exports: `WidgetDefinition`, `WidgetContext` (types), `registerWidget`, `getWidget`, `listWidgets` (from `./registry`); `useBusAction` (from `./ActionBusContext`); `useSetFilter` (from `./DataContext`); `useVariables`, `useSetVariable` (from `./VariablesContext`); `DataSource`, `DataSourceState`, `Page` (types, from `../api/types`).
  - `registerWidget(def)`'s behavior is unchanged except it now calls `console.warn(...)` before overwriting an already-registered `type`.

- [ ] **Step 1: Write the failing `registry.ts` collision test**

Append to `shell/src/builder/registry.test.tsx`:

```tsx
test("registerWidget warns when a type is overwritten, but still overwrites it", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  registerWidget({
    type: "dup", label: "A", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div>a</div>,
  });
  registerWidget({
    type: "dup", label: "B", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div>b</div>,
  });
  expect(warn).toHaveBeenCalledWith(expect.stringContaining("dup"));
  expect(getWidget("dup")?.label).toBe("B");
  warn.mockRestore();
});

test("registerWidget does not warn for a brand-new type", () => {
  const warn = vi.spyOn(console, "warn").mockImplementation(() => {});
  registerWidget({
    type: "fresh", label: "A", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => <div />, Component: () => <div />,
  });
  expect(warn).not.toHaveBeenCalled();
  warn.mockRestore();
});
```

Add `vi` to this file's import line (`import { beforeEach, expect, test, vi } from "vitest";`).

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/registry.test.tsx`
Expected: FAIL — `registerWidget` never calls `console.warn` today, and the first test's `expect(warn).toHaveBeenCalledWith(...)` fails.

- [ ] **Step 3: Add the warning to `registerWidget`**

Edit `shell/src/builder/registry.ts`. Change:

```ts
export function registerWidget(def: WidgetDefinition): void {
  registry.set(def.type, def);
}
```

to:

```ts
export function registerWidget(def: WidgetDefinition): void {
  if (registry.has(def.type)) {
    console.warn(`registerWidget: overwriting an already-registered widget type "${def.type}"`);
  }
  registry.set(def.type, def);
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/registry.test.tsx`
Expected: PASS. The pre-existing "registers and retrieves a widget definition" test registers a fresh `"demo"` type once — no warning fires, unaffected.

- [ ] **Step 5: Write the failing `sdk.ts` test**

Create `shell/src/builder/sdk.test.ts`:

```ts
import { expect, test } from "vitest";
import * as sdk from "./sdk";

test("re-exports the widget registry functions and types", () => {
  expect(typeof sdk.registerWidget).toBe("function");
  expect(typeof sdk.getWidget).toBe("function");
  expect(typeof sdk.listWidgets).toBe("function");
});

test("re-exports the action/data/variables hooks", () => {
  expect(typeof sdk.useBusAction).toBe("function");
  expect(typeof sdk.useSetFilter).toBe("function");
  expect(typeof sdk.useVariables).toBe("function");
  expect(typeof sdk.useSetVariable).toBe("function");
});
```

- [ ] **Step 6: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/sdk.test.ts`
Expected: FAIL — module `./sdk` does not exist.

- [ ] **Step 7: Implement `sdk.ts`**

Create `shell/src/builder/sdk.ts`:

```ts
export type { WidgetContext, WidgetDefinition } from "./registry";
export { registerWidget, getWidget, listWidgets } from "./registry";
export { useBusAction } from "./ActionBusContext";
export { useSetFilter } from "./DataContext";
export { useVariables, useSetVariable } from "./VariablesContext";
export type { DataSource, DataSourceState, Page } from "../api/types";
```

- [ ] **Step 8: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/sdk.test.ts`
Expected: PASS (2/2).

- [ ] **Step 9: Full suite + build, then commit**

Run: `cd shell && npx vitest run && npm run build`
Expected: all pass; build succeeds.

```bash
git add shell/src/builder/sdk.ts shell/src/builder/sdk.test.ts shell/src/builder/registry.ts shell/src/builder/registry.test.tsx
git commit -m "feat(shell): sdk.ts barrel export + registerWidget warns on type collision

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Example "Compteur" widget, sdk-only imports, wired into the real app

**Files:**
- Create: `shell/src/builder/examples/counterWidget.tsx`
- Test: `shell/src/builder/examples/counterWidget.test.tsx`
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppRuntimePage.tsx`

**Interfaces:**
- Consumes: `registerWidget`, `useBusAction` (Task 1's `sdk.ts` — this is the only import from `builder/*` this file is allowed to use; everything else it needs is plain React).
- Produces: `registerCounterExampleWidget(): void`, registering a widget of type `"example.counter"` (label "Compteur (exemple SDK)"), `defaultProps: { initial: 0 }`, `events: ["changed"]`, `actions: ["reset"]`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/examples/counterWidget.test.tsx`:

```tsx
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget, type WidgetContext } from "../registry";
import { ActionBus } from "../ActionBus";
import { registerCounterExampleWidget } from "./counterWidget";

beforeEach(() => { _resetRegistry(); registerCounterExampleWidget(); });

test("starts at its initial value and increments on click", async () => {
  const Counter = getWidget("example.counter")!.Component;
  render(<Counter props={{ initial: 5 }} ctx={{ mode: "runtime" } as WidgetContext} />);
  expect(screen.getByText("5")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(screen.getByText("6")).toBeInTheDocument();
});

test("emits changed with the new count", async () => {
  const bus = new ActionBus();
  const handler = vi.fn();
  bus.register("t1", "setFilter", handler);
  bus.configure([{ id: "m", from: "c1", event: "changed", to: "t1", action: "setFilter" }]);
  const Counter = getWidget("example.counter")!.Component;
  render(<Counter props={{ initial: 0 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />);
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(handler).toHaveBeenCalledWith({ count: 1 });
});

test("declares a reset action that resets to the initial value", async () => {
  const bus = new ActionBus();
  bus.configure([{ id: "m", from: "emitter", event: "go", to: "c1", action: "reset" }]);
  const Counter = getWidget("example.counter")!.Component;
  render(<Counter props={{ initial: 3 }} ctx={{ mode: "runtime", bus, widgetId: "c1" } as WidgetContext} />);
  await userEvent.click(screen.getByRole("button", { name: "+1" }));
  expect(screen.getByText("4")).toBeInTheDocument();
  bus.emit("emitter", "go");
  expect(screen.getByText("3")).toBeInTheDocument();
});

test("declares the events/actions the ActionsPanel needs to wire it", () => {
  expect(getWidget("example.counter")!.events).toEqual(["changed"]);
  expect(getWidget("example.counter")!.actions).toEqual(["reset"]);
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/examples/counterWidget.test.tsx`
Expected: FAIL — module `./counterWidget` does not exist.

- [ ] **Step 3: Implement the Compteur widget**

Create `shell/src/builder/examples/counterWidget.tsx`:

```tsx
import { useState } from "react";
import { registerWidget, useBusAction } from "../sdk";

export function registerCounterExampleWidget(): void {
  registerWidget({
    type: "example.counter",
    label: "Compteur (exemple SDK)",
    defaultProps: { initial: 0 },
    defaultSize: { w: 2, h: 2 },
    events: ["changed"],
    actions: ["reset"],
    PropsPanel: ({ props, onChange }) => (
      <label className="flex flex-col gap-1 text-sm">
        Valeur initiale
        <input
          aria-label="Valeur initiale"
          type="number"
          className="h-9 rounded-md border border-slate-300 px-2"
          value={String(props.initial ?? 0)}
          onChange={(e) => onChange({ ...props, initial: Number(e.target.value) })}
        />
      </label>
    ),
    Component: ({ props, ctx }) => {
      const [count, setCount] = useState(Number(props.initial ?? 0));
      useBusAction(ctx.bus, ctx.widgetId, "reset", () => setCount(Number(props.initial ?? 0)));
      function increment() {
        const next = count + 1;
        setCount(next);
        ctx.bus?.emit(ctx.widgetId ?? "", "changed", { count: next });
      }
      return (
        <div className="flex h-full flex-col items-center justify-center gap-1">
          <span className="text-2xl font-semibold">{count}</span>
          <button
            type="button"
            className="rounded-md border border-slate-300 px-2 py-1 text-sm hover:bg-slate-100"
            onClick={increment}
          >
            +1
          </button>
        </div>
      );
    },
  });
}
```

This file imports `registerWidget`/`useBusAction` from `../sdk` only — no `../registry`, `../ActionBusContext`, or any other deep relative path into `builder/*`, which is the entire point of Task 1's barrel.

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/examples/counterWidget.test.tsx`
Expected: PASS (4/4).

- [ ] **Step 5: Wire it into the real app**

Edit `shell/src/pages/AppBuilderPage.tsx`. Add the import:

```tsx
import { registerCounterExampleWidget } from "../builder/examples/counterWidget";
```

Change the module-level registration call from:

```tsx
registerBuiltinWidgets();
```

to:

```tsx
registerBuiltinWidgets();
registerCounterExampleWidget();
```

Edit `shell/src/pages/AppRuntimePage.tsx`. Apply the exact same two changes (add the import, add the call right after `registerBuiltinWidgets();`) — this file has its own separate `registerBuiltinWidgets();` call at module scope (the app has no single central bootstrap that registers widgets once; both page modules that need widgets call it independently, guarded by `registry.ts`'s own `getWidget("text")` idempotency check — the new call follows that exact existing pattern).

- [ ] **Step 6: Run tests, full suite + build, then commit**

Run: `cd shell && npx vitest run src/builder/examples/counterWidget.test.tsx && npx vitest run && npm run build`
Expected: all pass; build succeeds. (`AppBuilderPage.test.tsx`/`AppRuntimePage.test.tsx`'s existing tests never reference `"example.counter"` or "Compteur", so registering one more widget type doesn't change any of their assertions — `WidgetPalette` simply gains one more entry, which none of those tests enumerate exhaustively.)

```bash
git add shell/src/builder/examples/counterWidget.tsx shell/src/builder/examples/counterWidget.test.tsx shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppRuntimePage.tsx
git commit -m "feat(shell): add an sdk-only example widget (Compteur), wired into the app

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: E2E — add the example widget, wire it through `ActionsPanel`, use it in the runtime

**Files:**
- Create: `shell/e2e/widget-sdk.spec.ts`

**Interfaces:**
- Consumes: the stateful by-item mock store + `mockGeoNode` (existing — no mock change needed).
- Produces: an E2E that creates an app, adds two Compteur widgets, wires the first's `changed` event to the second's `reset` action via `ActionsPanel` (proving a widget declared entirely outside `builder/widgets/` integrates with the palette, props panel, and actions panel with zero core-code special-casing), saves, opens the runtime, increments the second counter, clicks the first counter's "+1", and confirms the second counter resets to its initial value.

- [ ] **Step 1: Write the E2E**

Create `shell/e2e/widget-sdk.spec.ts`:

```ts
import { test, expect } from "@playwright/test";
import { mockGeoNode } from "./mocks";

test("an sdk-only example widget appears in the palette and wires through ActionsPanel", async ({ page }) => {
  await mockGeoNode(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  await page.getByRole("dialog", { name: "Nouvel élément" }).getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("App SDK");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  // Add two Compteur widgets — the palette lists it purely because it's
  // registered, with no special-casing anywhere in the builder.
  await page.getByRole("button", { name: "Compteur (exemple SDK)" }).click();
  await page.getByRole("button", { name: "Compteur (exemple SDK)" }).click();

  // Wire the first's "changed" event to the second's "reset" action. Both
  // counters render the identical label "Compteur (exemple SDK)", so
  // selectOption({label}) would ambiguously resolve to whichever comes
  // first in both selects — use position instead. ActionsPanel lists
  // "Widget émetteur" options as [placeholder, counter 1, counter 2] (both
  // declare `events`, in the order they were added) and "Widget cible" as
  // [placeholder, counter 1, counter 2] (both declare `actions`, same
  // order) — index 1 is counter 1, index 2 is counter 2, in both selects.
  await page.getByLabel("Widget émetteur").selectOption({ index: 1 }); // counter 1
  await page.getByLabel("Événement").selectOption("changed");
  await page.getByLabel("Widget cible").selectOption({ index: 2 }); // counter 2
  await page.getByLabel("Action").selectOption("reset");
  await page.getByRole("button", { name: "Ajouter une action" }).click();

  await page.getByRole("button", { name: "Enregistrer" }).click();

  // Runtime: increment the second counter, then click the first's "+1" —
  // the wired reset action should bring the second counter back to 0.
  await page.goto("/apps/9");
  const plusButtons = page.getByRole("button", { name: "+1" });
  await plusButtons.nth(1).click();
  await expect(page.getByText("1")).toBeVisible();
  await plusButtons.nth(0).click();
  await expect(page.getByText("0")).toBeVisible();
});
```

- [ ] **Step 2: Run the new E2E**

Run: `cd shell && npx playwright test widget-sdk`
Expected: PASS.

- [ ] **Step 3: Run the full E2E suite**

Run: `cd shell && npx playwright test`
Expected: all specs pass (catalog + map-editor + app-builder + data-widget + actions + chart + responsive + theme + pages-navigation + templates + variables + widget-sdk, plus any specs added by plans executed after this one).

- [ ] **Step 4: Commit**

```bash
git add shell/e2e/widget-sdk.spec.ts
git commit -m "test(shell): E2E sdk-only example widget through the palette and ActionsPanel

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage (design §5/§13 SP-0d.7, as refined):** documented, stable contract → Task 1 (`sdk.ts` barrel, re-exporting the *actual* implemented shape, not the stale doc block this plan also corrected). Collision safety → Task 1's `registerWidget` warning. Third-party registration model (compile-time, no runtime plugin loading) → proven by Task 2's widget living outside `builder/widgets/` and importing only `../sdk`. Example widget → Task 2. End-to-end proof that it needs zero core-code changes → Task 3 (palette discovery, `PropsPanel`, `ActionsPanel` wiring, runtime behavior, all through the unmodified core).
- **Placeholder scan:** none — every step carries complete code or an exact edit against a quoted anchor.
- **Type consistency:** `sdk.ts` re-exports the *exact* names already defined elsewhere (`WidgetDefinition`/`WidgetContext` from `registry.ts`, `useBusAction` from `ActionBusContext.tsx`, etc.) — no renaming, no new type introduced. `registerCounterExampleWidget()`'s registered `type: "example.counter"` and its `events`/`actions` arrays are referenced identically across Task 2's tests and Task 3's E2E (`"changed"`, `"reset"`).
- **Backward compatibility:** `registerWidget`'s new warning only fires on an actual collision — every existing call site registers a unique `type` exactly once (confirmed during investigation: `text`/`image`/`button`/`list`/`table`/`indicator`/`map`/`filter`/`chart`/`nav`, all distinct), so no existing test's console output changes. Registering one more widget (`example.counter`) is purely additive to the palette/registry; no existing test enumerates `listWidgets()`'s full contents exhaustively (confirmed via `registry.test.tsx`'s own assertions, which use `arrayContaining`, not exact-length checks).
- **Façade discipline:** no network access added; this plan touches only the widget-registration/extension surface, not any data-fetching path.
- **Engine unity:** unaffected — `AppRenderer` itself is untouched; the example widget renders through the exact same `WidgetHost`/`GridCanvas` path as every builtin, in edit/preview/runtime alike.
- **Backend:** confirmed no change needed — this entire plan is front-end only.
