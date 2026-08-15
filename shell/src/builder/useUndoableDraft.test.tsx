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
