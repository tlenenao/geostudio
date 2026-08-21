// SPDX-License-Identifier: Apache-2.0
import { StrictMode } from "react";
import { act, renderHook } from "@testing-library/react";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { AppConfig } from "../api/types";
import { useUndoableDraft } from "./useUndoableDraft";

function config(text: string): AppConfig {
  return {
    kind: "app",
    theme: {},
    dataSources: [],
    messages: [],
    layout: {
      type: "grid",
      breakpoints: {},
      items: [{ id: "w1", widget: "text", x: 0, y: 0, w: 4, h: 2, props: { text } }],
    },
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
  void act(() => vi.advanceTimersByTime(400));
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
  void act(() => vi.advanceTimersByTime(400));
  expect(result.current.draft).toEqual(config("Abcd"));
  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("A")); // one step back past the whole burst
  expect(result.current.canUndo).toBe(false);
});

test("redo restores what undo just reverted", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  void act(() => vi.advanceTimersByTime(400));
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
  void act(() => vi.advanceTimersByTime(400));
  act(() => result.current.undo());
  act(() => result.current.setDraft(config("C")));
  void act(() => vi.advanceTimersByTime(400));
  expect(result.current.canRedo).toBe(false);
  expect(result.current.draft).toEqual(config("C"));
});

test("setDraft supports the functional-updater form", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() =>
    result.current.setDraft((prev) =>
      prev ? config(`${String(prev.layout.items[0].props.text)}!`) : prev,
    ),
  );
  expect(result.current.draft).toEqual(config("A!"));
});

// AppBuilderPage.tsx relies on two setDraft(prev => ...) calls issued back to
// back in the same event handler each seeing the previous call's effect as
// `prev` (e.g. DataSourceSelect's onAdd via DataSourcesEditContext firing
// right before PropsPanel's onChange, when a newly-added widget is bound to
// a shared dataset in the same handler — see the comments around addWidget/
// updateSelectedProps there). C1's fix reads `draftRef.current` synchronously
// at call time instead of relying on React's setState-updater batching/
// chaining, so this must keep holding — verified directly here rather than
// assumed (SP-19 final-branch-review fix pass, finding C1).
test("two setDraft calls issued synchronously in the same handler each build on the other's result", () => {
  const { result } = renderHook(() => useUndoableDraft());
  act(() => result.current.seedDraft(config("A")));
  act(() => {
    result.current.setDraft((prev) =>
      prev ? config(`${String(prev.layout.items[0].props.text)}B`) : prev,
    );
    result.current.setDraft((prev) =>
      prev ? config(`${String(prev.layout.items[0].props.text)}C`) : prev,
    );
  });
  expect(result.current.draft).toEqual(config("ABC"));
});

// SP-19 final-branch-review fix pass, finding C1: React <StrictMode> (which
// wraps the whole app in dev, see shell/src/main.tsx) may invoke a useState
// updater function twice to help surface impurities. The pre-fix undo()/
// redo() mutated stackRef.current *inside* the updater passed to
// setDraftState, so under double-invocation the mutation happened twice
// against the same stack — corrupting/losing history — while the *second*
// invocation's return value is what actually lands as the new draft. This
// test only fails under <StrictMode>; it's the only way to catch this class
// of regression, since the E2E suite runs a production build (no
// double-invoke) and the other unit tests above never wrap in <StrictMode>.
test("undo/redo remain correct under <StrictMode> double-invocation of state updaters", () => {
  const { result } = renderHook(() => useUndoableDraft(), { wrapper: StrictMode });
  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  void act(() => vi.advanceTimersByTime(400));
  act(() => result.current.setDraft(config("C")));
  void act(() => vi.advanceTimersByTime(400));
  expect(result.current.draft).toEqual(config("C"));

  // Depth-2 stack: a single Ctrl+Z must revert exactly one step, not corrupt
  // or skip the middle state.
  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("B"));
  expect(result.current.canUndo).toBe(true);
  expect(result.current.canRedo).toBe(true);

  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("A"));
  expect(result.current.canUndo).toBe(false);
  expect(result.current.canRedo).toBe(true);

  act(() => result.current.redo());
  act(() => result.current.redo());
  expect(result.current.draft).toEqual(config("C"));
  expect(result.current.canRedo).toBe(false);
});

test("resetDraft remplace le brouillon et vide la pile", () => {
  const { result } = renderHook(() => useUndoableDraft());

  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B")));
  void act(() => vi.advanceTimersByTime(500));
  expect(result.current.canUndo).toBe(true);

  act(() => result.current.resetDraft(config("C")));

  expect(result.current.draft).toEqual(config("C"));
  expect(result.current.canUndo).toBe(false);
  expect(result.current.canRedo).toBe(false);

  // Un undo après reset ne doit rien faire, pas revenir à CONFIG_B.
  act(() => result.current.undo());
  expect(result.current.draft).toEqual(config("C"));
});

test("resetDraft annule un burst d'édition encore en attente", () => {
  const { result } = renderHook(() => useUndoableDraft());

  act(() => result.current.seedDraft(config("A")));
  act(() => result.current.setDraft(config("B"))); // burst armé, pas encore flushé
  act(() => result.current.resetDraft(config("C")));
  void act(() => vi.advanceTimersByTime(500)); // le timer ne doit rien flusher

  expect(result.current.canUndo).toBe(false);
});
