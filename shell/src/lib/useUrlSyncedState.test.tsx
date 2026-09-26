// SPDX-License-Identifier: Apache-2.0
import { act, renderHook } from "@testing-library/react";
import type { ReactElement } from "react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { useUrlSyncedState } from "./useUrlSyncedState";

function renderHookWithRouter(paramName: string, defaultValue: string | null, initialPath = "/") {
  return renderHook(() => useUrlSyncedState(paramName, defaultValue), {
    wrapper: ({ children }) => (
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="*" element={children as ReactElement} />
        </Routes>
      </MemoryRouter>
    ),
  });
}

describe("useUrlSyncedState", () => {
  it("lit la valeur initiale depuis le paramètre d'URL", () => {
    const { result } = renderHookWithRouter("page", null, "/?page=p2");
    expect(result.current[0]).toBe("p2");
  });

  it("retombe sur la valeur par défaut si le paramètre est absent", () => {
    const { result } = renderHookWithRouter("page", "p1", "/");
    expect(result.current[0]).toBe("p1");
  });

  it("met à jour l'URL quand le setter est appelé", () => {
    const { result } = renderHookWithRouter("page", null, "/");
    act(() => result.current[1]("p3"));
    expect(result.current[0]).toBe("p3");
  });

  it("retire le paramètre de l'URL quand le setter reçoit null", () => {
    const { result } = renderHookWithRouter("page", null, "/?page=p2");
    act(() => result.current[1](null));
    expect(result.current[0]).toBeNull();
  });
});
