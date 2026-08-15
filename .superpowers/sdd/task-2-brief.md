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

