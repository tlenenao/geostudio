// SPDX-License-Identifier: Apache-2.0
import { renderHook } from "@testing-library/react";
import { describe, expect, test } from "vitest";

import { usePanelTrigger } from "./usePanelTrigger";

describe("usePanelTrigger", () => {
  test("wires aria-expanded=false and a shared id when closed", () => {
    const { result } = renderHook(() => usePanelTrigger(false));
    expect(result.current.triggerProps["aria-expanded"]).toBe(false);
    expect(result.current.triggerProps["aria-controls"]).toBe(result.current.panelId);
    expect(result.current.panelProps.id).toBe(result.current.panelId);
    expect(result.current.panelProps.role).toBe("region");
  });

  test("wires aria-expanded=true when open", () => {
    const { result } = renderHook(() => usePanelTrigger(true));
    expect(result.current.triggerProps["aria-expanded"]).toBe(true);
  });

  test("panelId is stable across re-renders", () => {
    const { result, rerender } = renderHook(({ open }) => usePanelTrigger(open), {
      initialProps: { open: false },
    });
    const firstId = result.current.panelId;
    rerender({ open: true });
    expect(result.current.panelId).toBe(firstId);
  });
});
