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
