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

