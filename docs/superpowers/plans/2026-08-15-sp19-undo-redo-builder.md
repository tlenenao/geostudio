# SP-19 — Undo/redo général du builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the app/dashboard builder (`shell/src/pages/AppBuilderPage.tsx`) a
general undo/redo mechanism — `Ctrl+Z`/`Ctrl+Shift+Z` plus toolbar buttons —
that covers every panel's edits uniformly, without touching any individual
panel or widget settings component.

**Architecture:** A single ephemeral in-memory undo/redo stack (past/future
arrays of full `AppConfig` snapshots, capped at 50) sits behind one new hook,
`useUndoableDraft`, that replaces `AppBuilderPage`'s
`useState<AppConfig | null>(null)` for its `draft`. Every panel already funnels
every edit through this one `draft`/`setDraft` pair (verified against the real
code, not assumed) — `GridCanvas`'s per-cell moves, `PropsPanel`'s prop/
`visibleWhen` edits, `DataSourcePanel`, `ThemePanel`, `VariablesPanel`,
`ActionsPanel`, `NavigationPanel`, `PageManager`, all of it — so wrapping this
one setter is sufficient; no other file that currently calls `setDraft` needs
to change.

**Tech Stack:** React 19 (existing `useState`/`useCallback`/`useRef`), Vitest +
`@testing-library/react` (`renderHook`, fake timers), Playwright (existing
`shell/e2e/app-builder.spec.ts`) — no new dependencies.

## Global Constraints

- **Corrected against the spec, 2026-08-15 (see
  `docs/superpowers/specs/2026-08-05-undo-redo-builder-design.md` §3 for the
  full record):** the spec originally assumed panels already buffer text
  input locally and only commit on blur/drag-release. That's false for this
  codebase — every text/textarea field across ~20 widget `PropsPanel`s plus
  `PropsPanel`, `ThemePanel`, `VariablesPanel`, `ActionsPanel`,
  `NavigationPanel`, `DataSourcePanel` calls `onChange` (→ `setDraft`) on
  every keystroke, with zero local buffering anywhere. `GridCanvas` has no
  drag at all — moves are discrete arrow-button clicks, each already an
  atomic commit needing no batching. **Decided with Tanguy:** granularity is
  handled by a **single centralized idle-flush debounce** inside
  `useUndoableDraft` (§below) — not by adding local state to ~20+ files. This
  is a decided correction to the spec, not an open question.
- **Ephemeral only.** The stack lives in the hook's `useRef`s, scoped to one
  mount of `AppBuilderPage`. No persistence, no cross-item history — exactly
  the spec's §4 "hors périmètre v1".
- **Depth cap: 50.** The 51st push drops the oldest entry (`undoStack.ts`,
  Task 1).
- **Coalesce window: 400ms**, defined once as `COALESCE_WINDOW_MS` in
  `useUndoableDraft.ts`. `undo()`/`redo()` always flush any pending burst
  synchronously first — pressing `Ctrl+Z` immediately after an edit is always
  correct, it never has to wait for the window to elapse. Only the visible
  "Annuler" button's enabled state lags by up to the window's length.
- **Keyboard shortcut ignored while focus is in a text field** (`<input>`,
  `<textarea>`, or `contentEditable`) — preserves the browser's native
  per-field undo, matches spec acceptance criterion 4. A user undoes a text
  edit by tabbing/clicking out of the field first, then `Ctrl+Z` — standard
  editor convention.
- **Seeding the initial config is not an edit.** `AppBuilderPage`'s existing
  effect that seeds `draft` from the loaded config must not create an undo
  step (undoing it would set `draft` back to `null` and break rendering) —
  handled by a dedicated `seedDraft` function on the hook, separate from
  `setDraft`.
- Every code step in this plan follows TDD (failing test → minimal
  implementation → passing test → commit), per this repo's CLAUDE.md.

---

## File structure

**Create:**
- `shell/src/builder/undoStack.ts` — pure past/future stack logic (no React).
- `shell/src/builder/undoStack.test.ts`
- `shell/src/builder/useUndoableDraft.ts` — React hook wiring the stack to
  `AppConfig` state with idle-flush coalescing.
- `shell/src/builder/useUndoableDraft.test.tsx`

**Modify:**
- `shell/src/pages/AppBuilderPage.tsx` — swap `useState` for
  `useUndoableDraft`, add toolbar buttons + keyboard shortcut.
- `shell/src/pages/AppBuilderPage.test.tsx` — integration tests.
- `shell/e2e/app-builder.spec.ts` — one E2E test.

---

### Task 1: pure undo/redo stack

**Files:**
- Create: `shell/src/builder/undoStack.ts`
- Create: `shell/src/builder/undoStack.test.ts`

**Interfaces:**
- Produces: `UndoStack<T> = { past: T[]; future: T[] }`,
  `UNDO_STACK_MAX_DEPTH = 50`, `createUndoStack<T>(): UndoStack<T>`,
  `pushUndo<T>(stack: UndoStack<T>, snapshot: T): UndoStack<T>`,
  `applyUndo<T>(stack: UndoStack<T>, current: T): { stack: UndoStack<T>; value: T } | null`,
  `applyRedo<T>(stack: UndoStack<T>, current: T): { stack: UndoStack<T>; value: T } | null`.

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/undoStack.test.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import {
  applyRedo, applyUndo, createUndoStack, pushUndo, UNDO_STACK_MAX_DEPTH,
} from "./undoStack";

test("a fresh stack has empty past and future", () => {
  const stack = createUndoStack<number>();
  expect(stack).toEqual({ past: [], future: [] });
});

test("pushUndo appends to past and clears future", () => {
  let stack = createUndoStack<number>();
  stack = pushUndo(stack, 1);
  stack = { ...stack, future: [99] };
  stack = pushUndo(stack, 2);
  expect(stack).toEqual({ past: [1, 2], future: [] });
});

test(`pushUndo caps past at ${UNDO_STACK_MAX_DEPTH}, dropping the oldest`, () => {
  let stack = createUndoStack<number>();
  for (let i = 0; i < UNDO_STACK_MAX_DEPTH + 1; i++) stack = pushUndo(stack, i);
  expect(stack.past).toHaveLength(UNDO_STACK_MAX_DEPTH);
  expect(stack.past[0]).toBe(1); // snapshot 0 was dropped
  expect(stack.past[UNDO_STACK_MAX_DEPTH - 1]).toBe(UNDO_STACK_MAX_DEPTH);
});

test("applyUndo returns null when past is empty", () => {
  const stack = createUndoStack<number>();
  expect(applyUndo(stack, 1)).toBeNull();
});

test("applyUndo pops the last past entry and pushes current onto future", () => {
  const stack = pushUndo(createUndoStack<number>(), 1);
  const result = applyUndo(stack, 2);
  expect(result).not.toBeNull();
  expect(result?.value).toBe(1);
  expect(result?.stack).toEqual({ past: [], future: [2] });
});

test("applyRedo returns null when future is empty", () => {
  const stack = createUndoStack<number>();
  expect(applyRedo(stack, 1)).toBeNull();
});

test("applyRedo pops the first future entry and pushes current onto past", () => {
  const afterUndo = applyUndo(pushUndo(createUndoStack<number>(), 1), 2);
  const result = applyRedo(afterUndo!.stack, afterUndo!.value);
  expect(result).not.toBeNull();
  expect(result?.value).toBe(2);
  expect(result?.stack).toEqual({ past: [1], future: [] });
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/undoStack.test.ts`
Expected: FAIL — `Cannot find module './undoStack'`.

- [ ] **Step 3: Implement `undoStack.ts`**

Create `shell/src/builder/undoStack.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Pure past/future stack of full snapshots (SP-19). No React here — kept
// framework-free so it's trivially unit-testable and reusable by
// useUndoableDraft.ts's debounce wrapper.
export type UndoStack<T> = { past: T[]; future: T[] };

export const UNDO_STACK_MAX_DEPTH = 50;

export function createUndoStack<T>(): UndoStack<T> {
  return { past: [], future: [] };
}

// Pushes `snapshot` (the state *before* the change about to be applied) onto
// `past`, discarding `future` — same convention as any editor: a new edit
// after an undo replaces whatever could have been redone. Caps at
// UNDO_STACK_MAX_DEPTH, dropping the oldest entry once exceeded.
export function pushUndo<T>(stack: UndoStack<T>, snapshot: T): UndoStack<T> {
  const past = [...stack.past, snapshot];
  if (past.length > UNDO_STACK_MAX_DEPTH) past.shift();
  return { past, future: [] };
}

// Pops the most recent snapshot off `past`, pushes `current` onto `future`
// so a following applyRedo can restore it. Returns null when there's
// nothing to undo (caller keeps whatever state it already has).
export function applyUndo<T>(
  stack: UndoStack<T>, current: T,
): { stack: UndoStack<T>; value: T } | null {
  if (stack.past.length === 0) return null;
  const value = stack.past[stack.past.length - 1];
  const past = stack.past.slice(0, -1);
  const future = [current, ...stack.future];
  return { stack: { past, future }, value };
}

// Mirror of applyUndo: pops the oldest `future` entry, pushes `current`
// back onto `past`.
export function applyRedo<T>(
  stack: UndoStack<T>, current: T,
): { stack: UndoStack<T>; value: T } | null {
  if (stack.future.length === 0) return null;
  const value = stack.future[0];
  const future = stack.future.slice(1);
  const past = [...stack.past, current];
  return { stack: { past, future }, value };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/undoStack.test.ts`
Expected: PASS (7 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/undoStack.ts shell/src/builder/undoStack.test.ts
git commit -m "feat(shell): pure undo/redo stack module (SP-19)"
```

---

### Task 2: `useUndoableDraft` hook

**Files:**
- Create: `shell/src/builder/useUndoableDraft.ts`
- Create: `shell/src/builder/useUndoableDraft.test.tsx`

**Interfaces:**
- Consumes: `createUndoStack`, `pushUndo`, `applyUndo`, `applyRedo`,
  `UndoStack` (Task 1, `./undoStack`), `AppConfig` (`../api/types`).
- Produces:
  ```ts
  export type UndoableDraft = {
    draft: AppConfig | null;
    setDraft: (update: AppConfig | null | ((prev: AppConfig | null) => AppConfig | null)) => void;
    seedDraft: (value: AppConfig) => void;
    undo: () => void;
    redo: () => void;
    canUndo: boolean;
    canRedo: boolean;
  };
  export function useUndoableDraft(): UndoableDraft;
  ```
  `setDraft` has the exact same call signature as the `useState` setter it
  replaces (value or updater function) — every existing call site in
  `AppBuilderPage.tsx` (`setDraft(d => ...)` and `setDraft(value)` both) keeps
  working unchanged (Task 3).

- [ ] **Step 1: Write the failing tests**

Create `shell/src/builder/useUndoableDraft.test.tsx`:

```tsx
// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { AppConfig } from "../api/types";
import { useUndoableDraft } from "./useUndoableDraft";

function config(text: string): AppConfig {
  return {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text } },
    ] },
  };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

test("seedDraft sets the initial draft without creating an undo step", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  expect(result.current.draft).toEqual(config("A"));
  expect(result.current.canUndo).toBe(false);
});

test("seedDraft never overwrites an already-seeded draft", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.seedDraft(config("B")));
  expect(result.current.draft).toEqual(config("A"));
});

test("canUndo flips true once the coalesce window elapses after a setDraft call", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  expect(result.current.canUndo).toBe(false); // still pending
  act(() => vi.advanceTimersByTime(400));
  expect(result.current.canUndo).toBe(true);
});

test("undo restores the pre-edit config and flushes a still-pending burst immediately", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  // No advanceTimersByTime: the window hasn't elapsed, but undo() must not
  // need it to act correctly.
  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("A"));
  expect(result.current.canUndo).toBe(false);
  expect(result.current.canRedo).toBe(true);
});

test("a rapid burst of setDraft calls within the window collapses into one undo step", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => {
    result.current.setDraft(config("Ab"));
    vi.advanceTimersByTime(100);
    result.current.setDraft(config("Abc"));
    vi.advanceTimersByTime(100);
    result.current.setDraft(config("Abcd"));
  });
  act(() => vi.advanceTimersByTime(400));
  expect(result.current.draft).toEqual(config("Abcd"));
  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("A")); // one step back past the whole burst
  expect(result.current.canUndo).toBe(false);
});

test("redo restores what undo just reverted", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  act(() => vi.advanceTimersByTime(400));
  act(() => result.current.undo());
  act(() => result.current.redo());
  expect(result.current.draft).toEqual(config("B"));
  expect(result.current.canRedo).toBe(false);
  expect(result.current.canUndo).toBe(true);
});

test("a new edit after undo purges the redo branch", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  act(() => vi.advanceTimersByTime(400));
  act(() => result.current.undo());
  act(() => result.current.setDraft(config("C")));
  act(() => vi.advanceTimersByTime(400));
  expect(result.current.canRedo).toBe(false);
  expect(result.current.draft).toEqual(config("C"));
});

test("setDraft supports the functional-updater form", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft((prev) => (prev ? config(`${String(prev.layout.items[0].props.text)}!`) : prev)));
  expect(result.current.draft).toEqual(config("A!"));
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/builder/useUndoableDraft.test.tsx`
Expected: FAIL — `Cannot find module './useUndoableDraft'`.

- [ ] **Step 3: Implement `useUndoableDraft.ts`**

Create `shell/src/builder/useUndoableDraft.ts`:

```ts
// SPDX-License-Identifier: Apache-2.0
// Undo/redo for the builder's edited AppConfig (SP-19). Wraps the single
// setDraft setter every panel already funnels edits through (verified
// against the real code, not assumed — cf. docs/superpowers/specs/
// 2026-08-05-undo-redo-builder-design.md §3): no other panel/widget file
// needs to change.
//
// No panel buffers text input locally (every keystroke calls onChange →
// setDraft directly, across ~20 widget PropsPanels plus PropsPanel/
// ThemePanel/VariablesPanel/ActionsPanel/NavigationPanel/DataSourcePanel).
// Pushing an undo snapshot on every call would explode the stack one entry
// per keystroke. Instead: the *first* setDraft call after the stack was
// last flushed captures the pre-burst config as the pending baseline; later
// calls within COALESCE_WINDOW_MS extend the same burst without
// re-capturing. A discrete action (one GridCanvas arrow click, one "add
// widget" click) naturally flushes on its own since nothing else calls
// setDraft within the window. undo()/redo() always flush a still-pending
// burst synchronously first, so Ctrl+Z is correct even mid-burst.
import { useCallback, useRef, useState } from "react";
import type { AppConfig } from "../api/types";
import { applyRedo, applyUndo, createUndoStack, pushUndo, type UndoStack } from "./undoStack";

const COALESCE_WINDOW_MS = 400;

export type UndoableDraft = {
  draft: AppConfig | null;
  setDraft: (update: AppConfig | null | ((prev: AppConfig | null) => AppConfig | null)) => void;
  seedDraft: (value: AppConfig) => void;
  undo: () => void;
  redo: () => void;
  canUndo: boolean;
  canRedo: boolean;
};

export function useUndoableDraft(): UndoableDraft {
  const [draft, setDraftState] = useState<AppConfig | null>(null);
  const stackRef = useRef<UndoStack<AppConfig>>(createUndoStack());
  const pendingBaselineRef = useRef<AppConfig | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [canUndo, setCanUndo] = useState(false);
  const [canRedo, setCanRedo] = useState(false);

  const flush = useCallback(() => {
    if (timerRef.current !== null) {
      clearTimeout(timerRef.current);
      timerRef.current = null;
    }
    if (pendingBaselineRef.current === null) return;
    stackRef.current = pushUndo(stackRef.current, pendingBaselineRef.current);
    pendingBaselineRef.current = null;
    setCanUndo(true);
    setCanRedo(false);
  }, []);

  const setDraft = useCallback<UndoableDraft["setDraft"]>((update) => {
    setDraftState((prev) => {
      const next = typeof update === "function"
        ? (update as (p: AppConfig | null) => AppConfig | null)(prev)
        : update;
      if (next !== prev && prev !== null) {
        if (pendingBaselineRef.current === null) pendingBaselineRef.current = prev;
        if (timerRef.current !== null) clearTimeout(timerRef.current);
        timerRef.current = setTimeout(flush, COALESCE_WINDOW_MS);
      }
      return next;
    });
  }, [flush]);

  // Seeds the initial config once loaded, bypassing history entirely — the
  // starting point of the session, not an edit. Undoing it would set draft
  // back to null and break rendering. `prev ?? value` mirrors the original
  // AppBuilderPage seeding effect (never clobbers in-flight edits on a
  // refetch).
  const seedDraft = useCallback((value: AppConfig) => {
    setDraftState((prev) => prev ?? value);
  }, []);

  const undo = useCallback(() => {
    flush();
    setDraftState((prev) => {
      if (prev === null) return prev;
      const result = applyUndo(stackRef.current, prev);
      if (result === null) return prev;
      stackRef.current = result.stack;
      setCanUndo(result.stack.past.length > 0);
      setCanRedo(true);
      return result.value;
    });
  }, [flush]);

  const redo = useCallback(() => {
    flush();
    setDraftState((prev) => {
      if (prev === null) return prev;
      const result = applyRedo(stackRef.current, prev);
      if (result === null) return prev;
      stackRef.current = result.stack;
      setCanUndo(true);
      setCanRedo(result.stack.future.length > 0);
      return result.value;
    });
  }, [flush]);

  return { draft, setDraft, seedDraft, undo, redo, canUndo, canRedo };
}
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/builder/useUndoableDraft.test.tsx`
Expected: PASS (8 tests)

- [ ] **Step 5: Commit**

```bash
git add shell/src/builder/useUndoableDraft.ts shell/src/builder/useUndoableDraft.test.tsx
git commit -m "feat(shell): useUndoableDraft — debounced undo/redo for the builder config (SP-19)"
```

---

### Task 3: wire into `AppBuilderPage`

**Files:**
- Modify: `shell/src/pages/AppBuilderPage.tsx`
- Modify: `shell/src/pages/AppBuilderPage.test.tsx`

**Interfaces:**
- Consumes: `useUndoableDraft` (Task 2, `../builder/useUndoableDraft`).
- Produces: two new toolbar buttons with visible text "Annuler" and
  "Rétablir" (accessible name = visible text, no separate aria-label
  needed), disabled per `canUndo`/`canRedo`. Global `Ctrl+Z`/`Cmd+Z` (undo)
  and `Ctrl+Shift+Z`/`Cmd+Shift+Z` (redo) keyboard shortcuts, ignored when
  `document.activeElement` is a text-editing element.

- [ ] **Step 1: Write the failing tests**

Append to `shell/src/pages/AppBuilderPage.test.tsx` (all existing tests stay
as-is above this):

```tsx


test("a GridCanvas move can be undone with Ctrl+Z", async () => {
  const withItem: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(0);
});

test("Ctrl+Shift+Z redoes an undone GridCanvas move", async () => {
  const withItem: AppConfig = {
    kind: "app", theme: {}, dataSources: [], messages: [],
    layout: { type: "grid", breakpoints: {}, items: [
      { id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text: "Hi" } },
    ] },
  };
  const saveAppConfig = vi.fn().mockResolvedValue(undefined);
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(withItem), saveAppConfig });

  await userEvent.click(await screen.findByRole("button", { name: "Sélectionner widget-w1" }));
  await userEvent.click(screen.getByRole("button", { name: "Déplacer widget-w1 à droite" }));
  await userEvent.keyboard("{Control>}z{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeEnabled();

  await userEvent.keyboard("{Control>}{Shift>}z{/Shift}{/Control}");
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveAppConfig).toHaveBeenCalled());
  const saved = saveAppConfig.mock.calls[0][1] as AppConfig;
  expect(saved.layout.items[0].x).toBe(1);
});

test("a burst of keystrokes in visibleWhen collapses into one undo step once blurred", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x == 'a'");
  // Move focus to a non-text element — tabbing would only land in the "text"
  // widget's own textarea just below visibleWhen in the same panel, still a
  // text field, so it wouldn't actually exercise the "focus left every text
  // field" path the keyboard shortcut check depends on.
  await userEvent.click(screen.getByRole("button", { name: "Édition" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.keyboard("{Control>}z{/Control}");
  expect(area).toHaveValue("");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
});

test("Ctrl+Z while focus is in a text field does not trigger the builder's undo", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  await userEvent.click(screen.getByRole("button", { name: "Texte" }));
  const area = screen.getByLabelText("Condition d'affichage (visibleWhen)");
  await userEvent.type(area, "vars.x");
  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled());

  await userEvent.type(area, "{Control>}z{/Control}"); // focus stays in `area`
  expect(area).toHaveValue("vars.x");
  expect(screen.getByRole("button", { name: "Annuler" })).toBeEnabled();
});

test("Annuler and Rétablir start disabled and stay disabled with no edits", async () => {
  renderPage({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await screen.findByRole("button", { name: "Texte" });
  expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Rétablir" })).toBeDisabled();
});
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: FAIL — no element with role `button` and name `Annuler`/`Rétablir`
exists yet.

- [ ] **Step 3: Update `AppBuilderPage.tsx`**

Change the import block — replace:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
```

with:

```tsx
import { useEffect, useMemo, useRef, useState } from "react";
import { useUndoableDraft } from "../builder/useUndoableDraft";
```

Replace the `draft`/`selectedId` state declarations:

```tsx
  const [draft, setDraft] = useState<AppConfig | null>(null);
  const [selectedId, setSelectedId] = useState<string | null>(null);
```

with:

```tsx
  const { draft, setDraft, seedDraft, undo, redo, canUndo, canRedo } = useUndoableDraft();
  const [selectedId, setSelectedId] = useState<string | null>(null);
```

Replace the seeding effect:

```tsx
  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    if (query.data) setDraft((d) => d ?? query.data);
  }, [query.data]);
```

with:

```tsx
  useEffect(() => {
    // Seed the draft once on first load. Re-seeding on every query.data change
    // (e.g. the refetch after a save) would clobber in-flight local edits.
    // seedDraft (not setDraft) — this is the session's starting point, not
    // an edit, and must not create an undo step (SP-19).
    if (query.data) seedDraft(query.data);
  }, [query.data, seedDraft]);
```

Add the keyboard shortcut effect right after it (still before the
`query.isLoading` early return, alongside the other hooks):

```tsx
  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField = target instanceof HTMLInputElement
        || target instanceof HTMLTextAreaElement
        || (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);
```

Add the toolbar buttons — replace:

```tsx
          <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
          <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
          <div className="ml-2 flex items-center gap-1">
```

with:

```tsx
          <Button size="sm" variant={mode === "edit" ? "default" : "outline"} onClick={() => setMode("edit")}>Édition</Button>
          <Button size="sm" variant={mode === "preview" ? "default" : "outline"} onClick={() => setMode("preview")}>Aperçu</Button>
          <div className="ml-2 flex items-center gap-1">
            <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>Annuler</Button>
            <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>Rétablir</Button>
          </div>
          <div className="ml-2 flex items-center gap-1">
```

(This introduces a second `ml-2` group right after the first — matching the
existing breakpoint-buttons group's own styling, just placed before it.)

- [ ] **Step 4: Run to verify it passes**

Run: `cd shell && npx vitest run src/pages/AppBuilderPage.test.tsx`
Expected: PASS (all tests, existing + 5 new)

- [ ] **Step 5: Run the full shell unit suite to confirm nothing broke**

Run: `cd shell && npm run test`
Expected: PASS (no regressions elsewhere — `AppRenderer`'s own `onChange`
prop type is unchanged, still `(config: AppConfig) => void`, satisfied by
the hook's `setDraft`).

- [ ] **Step 6: Typecheck**

Run: `cd shell && npx tsc --noEmit`
Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add shell/src/pages/AppBuilderPage.tsx shell/src/pages/AppBuilderPage.test.tsx
git commit -m "feat(shell): AppBuilderPage gains undo/redo — Ctrl+Z/Ctrl+Shift+Z + toolbar buttons (SP-19)"
```

---

### Task 4: E2E proof

**Files:**
- Modify: `shell/e2e/app-builder.spec.ts`

**Interfaces:**
- Consumes: `mockCore` (`./mocks`, unchanged).

- [ ] **Step 1: Append the E2E test**

Append to `shell/e2e/app-builder.spec.ts` (existing test stays as-is above
this):

```ts

test("undo/redo: adding a widget can be undone and redone", async ({ page }) => {
  await mockCore(page);
  await page.goto("/");

  await page.getByRole("button", { name: "Nouveau" }).click();
  const dialog = page.getByRole("dialog", { name: "Nouvel élément" });
  await dialog.getByLabel("Type").selectOption("app");
  await page.getByLabel("Titre").fill("Mon app");
  await page.getByRole("button", { name: "Créer" }).click();
  await expect(page).toHaveURL(/\/apps\/9\/edit$/);

  await page.getByRole("button", { name: "Texte" }).click();
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();

  await page.keyboard.press("Control+z");
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Annuler" })).toBeDisabled();

  await page.keyboard.press("Control+Shift+z");
  await expect(page.getByRole("button", { name: /^Sélectionner widget-/ })).toBeVisible();
});
```

- [ ] **Step 2: Run it**

Run: `cd shell && npx playwright test e2e/app-builder.spec.ts`
Expected: PASS (2 tests — the pre-existing one and this new one).

- [ ] **Step 3: Commit**

```bash
git add shell/e2e/app-builder.spec.ts
git commit -m "test(e2e): undo/redo an added widget in the app builder (SP-19)"
```

---

## Self-review notes

- **Spec coverage:** §3 architecture (single stack behind the one existing
  commit point) → Tasks 2–3. §3 granularity (corrected 2026-08-15, centralized
  debounce) → Task 2's `COALESCE_WINDOW_MS` mechanism, verified in Task 3's
  "collapses into one undo step" and "flushes immediately on undo" tests. §5
  risk (single-commit-point audit) → resolved by construction: every panel
  reads from the same `AppBuilderPage.tsx` `setDraft` (confirmed by reading
  `PropsPanel`/`ActionsPanel`/`DataSourcePanel`/`ThemePanel`/
  `VariablesPanel`/`NavigationPanel`/`GridCanvas`/every widget's `PropsPanel`
  before writing this plan — none of them hold a second, parallel path to
  the config), so no per-panel fix task is needed. §6 acceptance criteria:
  (1) any panel's committed mutation undoable → Task 3 GridCanvas test +
  Task 4 E2E; (2) one step per gesture, not per intermediate event → Task 2
  burst test + Task 3 visibleWhen burst test; (3) 50-step cap → Task 1; (4)
  `Ctrl+Z` ignored while typing → Task 3's dedicated test.
- **Placeholder scan:** none — every step has complete, real code.
- **Type consistency:** `UndoStack<T>`/`pushUndo`/`applyUndo`/`applyRedo`
  used identically in Task 1 (definition) and Task 2 (`useUndoableDraft`'s
  only consumer). `UndoableDraft`'s five fields (`draft`, `setDraft`,
  `seedDraft`, `undo`, `redo`, `canUndo`, `canRedo`) used identically in Task
  2 (definition) and Task 3 (destructured in `AppBuilderPage.tsx`, same
  names, no renaming).
