// SPDX-License-Identifier: Apache-2.0
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { act, renderHook } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import type { ReactNode } from "react";
import {
  EXPORT_SETTLE_MS,
  EXPORT_TIMEOUT_MS,
  markExportReady,
  trackExportTask,
  useExportReadiness,
} from "./exportReady";

afterEach(() => {
  delete document.body.dataset.exportReady;
  delete document.body.dataset.exportIncomplete;
  vi.useRealTimers();
});

describe("markExportReady", () => {
  it('sets data-export-ready="true" on document.body — the exact selector Task 6\'s worker waits for', () => {
    markExportReady();
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
    expect(document.body.dataset.exportReady).toBe("true");
  });

  it("is idempotent: calling it twice does not throw and leaves the same attribute", () => {
    markExportReady();
    expect(() => markExportReady()).not.toThrow();
    expect(document.body.getAttribute("data-export-ready")).toBe("true");
  });
});

describe("useExportReadiness (AUD-001 / D04-01)", () => {
  let qc: QueryClient;
  const wrapper = ({ children }: { children: ReactNode }) => (
    <QueryClientProvider client={qc}>{children}</QueryClientProvider>
  );
  const ready = () => document.body.getAttribute("data-export-ready");

  beforeEach(() => {
    vi.useFakeTimers();
    qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  });

  it("ne lève rien tant que la base (config + extensions) n'est pas prête", () => {
    renderHook(() => useExportReadiness(false), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 3));
    expect(ready()).toBeNull();
  });

  it("lève après la fenêtre de stabilité quand rien n'est en cours", () => {
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS - 1));
    expect(ready()).toBeNull();
    act(() => void vi.advanceTimersByTime(2));
    expect(ready()).toBe("true");
    expect(document.body.dataset.exportIncomplete).toBeUndefined();
  });

  it("attend la fin d'une requête React Query en cours", async () => {
    let resolve!: (v: number) => void;
    const p = new Promise<number>((r) => (resolve = r));
    void qc.fetchQuery({ queryKey: ["slow"], queryFn: () => p });
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 5));
    expect(ready()).toBeNull();
    await act(async () => {
      resolve(1);
      await p;
      // React Query notifie ses observateurs via un setTimeout(0) (faux timers)
      await vi.advanceTimersByTimeAsync(1);
    });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS + 1));
    expect(ready()).toBe("true");
  });

  it("attend une tâche suivie (widget carte) jusqu'à sa libération, libération idempotente", () => {
    const done = trackExportTask();
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS * 5));
    expect(ready()).toBeNull();
    act(() => {
      done();
      done();
    });
    act(() => void vi.advanceTimersByTime(EXPORT_SETTLE_MS + 1));
    expect(ready()).toBe("true");
  });

  it("à l'expiration, lève quand même et marque l'export incomplet", () => {
    const done = trackExportTask(); // ne se libère jamais (carte bloquée)
    renderHook(() => useExportReadiness(true), { wrapper });
    act(() => void vi.advanceTimersByTime(EXPORT_TIMEOUT_MS + 1));
    expect(ready()).toBe("true");
    expect(document.body.dataset.exportIncomplete).toBe("true");
    done();
  });
});
