// SPDX-License-Identifier: Apache-2.0
import { createElement, type ReactNode } from "react";
import { describe, expect, it } from "vitest";
import { renderHook } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { useIsExportRender } from "./useIsExportRender";

// Plain .ts (not .tsx): use createElement rather than JSX syntax, which
// esbuild refuses to parse in a .ts file.
function wrapper(initialPath: string) {
  return ({ children }: { children: ReactNode }) =>
    createElement(MemoryRouter, { initialEntries: [initialPath] }, children);
}

describe("useIsExportRender", () => {
  it("is false without the query param", () => {
    const { result } = renderHook(() => useIsExportRender(), { wrapper: wrapper("/maps/1") });
    expect(result.current).toBe(false);
  });

  it("is true with exportRender=1", () => {
    const { result } = renderHook(() => useIsExportRender(), {
      wrapper: wrapper("/maps/1?exportRender=1"),
    });
    expect(result.current).toBe(true);
  });

  it('is false for other values of exportRender (not exactly "1")', () => {
    const { result } = renderHook(() => useIsExportRender(), {
      wrapper: wrapper("/maps/1?exportRender=true"),
    });
    expect(result.current).toBe(false);
  });
});
