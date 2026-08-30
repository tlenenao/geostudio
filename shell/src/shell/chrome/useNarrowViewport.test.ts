// SPDX-License-Identifier: Apache-2.0
import { renderHook, act } from "@testing-library/react";
import { vi } from "vitest";
import { useNarrowViewport } from "./useNarrowViewport";

function mockMatchMedia(initialMatches: boolean) {
  let listener: (() => void) | null = null;
  const mql = {
    matches: initialMatches,
    addEventListener: (_: string, cb: () => void) => {
      listener = cb;
    },
    removeEventListener: () => {
      listener = null;
    },
  };
  vi.stubGlobal("matchMedia", vi.fn().mockReturnValue(mql));
  return {
    fireChange(matches: boolean) {
      mql.matches = matches;
      listener?.();
    },
  };
}

test("retourne false par défaut au-dessus de 390 px", () => {
  mockMatchMedia(false);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(false);
});

test("retourne true sous 390 px et suit les changements", () => {
  const { fireChange } = mockMatchMedia(true);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(true);
  act(() => fireChange(false));
  expect(result.current).toBe(false);
});
