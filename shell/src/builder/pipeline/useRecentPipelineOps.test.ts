// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from "@testing-library/react";
import { beforeEach, expect, test } from "vitest";
import { useRecentPipelineOps } from "./useRecentPipelineOps";

beforeEach(() => localStorage.clear());

test("recordUse adds an op to the front of the recent list", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => result.current.recordUse("reader.collection"));
  expect(result.current.recent).toEqual(["reader.collection"]);
});

test("recordUse moves an already-recorded op to the front instead of duplicating it", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => result.current.recordUse("reader.collection"));
  act(() => result.current.recordUse("transform.filter"));
  act(() => result.current.recordUse("reader.collection"));
  expect(result.current.recent).toEqual(["reader.collection", "transform.filter"]);
});

test("keeps only the 5 most recently used ops", () => {
  const { result } = renderHook(() => useRecentPipelineOps());
  act(() => {
    for (const op of ["a", "b", "c", "d", "e", "f"]) result.current.recordUse(op);
  });
  expect(result.current.recent).toEqual(["f", "e", "d", "c", "b"]);
});

test("persists across hook instances via localStorage", () => {
  const first = renderHook(() => useRecentPipelineOps());
  act(() => first.result.current.recordUse("reader.collection"));
  const second = renderHook(() => useRecentPipelineOps());
  expect(second.result.current.recent).toEqual(["reader.collection"]);
});
