// SPDX-License-Identifier: Apache-2.0
import { renderHook, act } from "@testing-library/react";
import { vi } from "vitest";
import { useNarrowViewport, NARROW_QUERY } from "./useNarrowViewport";

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
  const matchMedia = vi.fn().mockReturnValue(mql);
  vi.stubGlobal("matchMedia", matchMedia);
  return {
    matchMedia,
    fireChange(matches: boolean) {
      mql.matches = matches;
      listener?.();
    },
  };
}

test("retourne false strictement au-dessus du seuil étroit", () => {
  mockMatchMedia(false);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(false);
});

test("retourne true au seuil étroit ou en-dessous, et suit les changements", () => {
  const { fireChange } = mockMatchMedia(true);
  const { result } = renderHook(() => useNarrowViewport());
  expect(result.current).toBe(true);
  act(() => fireChange(false));
  expect(result.current).toBe(false);
});

test("interroge la vraie chaîne de media query, pas seulement le booléen mocké", () => {
  const { matchMedia } = mockMatchMedia(false);
  renderHook(() => useNarrowViewport());
  expect(matchMedia).toHaveBeenCalledWith(NARROW_QUERY);
});

test("NARROW_QUERY correspond au seuil documenté par SP-33 (899px)", () => {
  expect(NARROW_QUERY).toBe("(max-width: 899px)");
});
