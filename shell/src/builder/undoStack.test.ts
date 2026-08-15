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
