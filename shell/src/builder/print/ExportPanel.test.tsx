// SPDX-License-Identifier: Apache-2.0
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ItemClient } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { ExportPanel } from "./ExportPanel";

function renderPanel(overrides: Partial<ItemClient>) {
  const client: Partial<ItemClient> = { ...overrides };
  return render(
    <ItemClientProvider client={client as ItemClient}>
      <ExportPanel itemId="item-1" />
    </ItemClientProvider>,
  );
}

describe("ExportPanel", () => {
  it("creates an export job on click and polls until done, then shows a download link", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    let call = 0;
    const getExportJob = vi.fn().mockImplementation(() => {
      call += 1;
      const status = call < 2 ? "running" : "done";
      return Promise.resolve({
        id: "job-1",
        status,
        resultUrl: status === "done" ? "https://minio.test/x.pdf" : null,
        error: null,
      });
    });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    expect(createExport).toHaveBeenCalledWith("item-1", "pdf");
    await waitFor(
      () =>
        expect(screen.getByRole("link", { name: /télécharger/i })).toHaveAttribute(
          "href",
          "https://minio.test/x.pdf",
        ),
      { timeout: 5000 },
    );
    expect(call).toBeGreaterThanOrEqual(2);
  });

  it("surfaces a job error via role=alert instead of silently stopping", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi
      .fn()
      .mockResolvedValue({ id: "job-1", status: "error", resultUrl: null, error: "render timeout" });
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PNG" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("render timeout"));
  });

  it("surfaces a failure to even create the job", async () => {
    const createExport = vi.fn().mockRejectedValue(new Error("Request failed: 403 POST /export"));
    renderPanel({ createExport, getExportJob: vi.fn() });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
  });

  it("surfaces a network failure during polling itself, not just a job status of error", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi.fn().mockRejectedValue(new Error("network down"));
    renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(/échec/i));
  });

  it("does not poll again or update state after the panel is unmounted mid-poll", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    let call = 0;
    const getExportJob = vi.fn().mockImplementation(() => {
      call += 1;
      return Promise.resolve({ id: "job-1", status: "running", resultUrl: null, error: null });
    });
    const { unmount } = renderPanel({ createExport, getExportJob });

    await userEvent.click(screen.getByRole("button", { name: "Exporter" }));
    await userEvent.click(screen.getByRole("button", { name: "PDF" }));

    await waitFor(() => expect(call).toBeGreaterThanOrEqual(1));
    const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
    unmount();
    await new Promise((r) => setTimeout(r, 2000));
    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

// Fix round (finding I7) : le job d'export ne quitte jamais "running" —
// simule export-worker mort en plein rendu (OOM, crash) sans reclaim serveur
// pour l'instant. Scoped à sa propre describe pour les mêmes raisons que
// AnalyticsContext.test.tsx (fake timers confinés pour ne pas accrocher les
// userEvent.click des tests ci-dessus).
describe("ExportPanel — plafond de poll (finding I7)", () => {
  beforeEach(() => vi.useFakeTimers());
  afterEach(() => vi.useRealTimers());

  it("stops polling after the max attempt budget and surfaces a clear error instead of polling forever", async () => {
    const createExport = vi.fn().mockResolvedValue({ jobId: "job-1" });
    const getExportJob = vi
      .fn()
      .mockResolvedValue({ id: "job-1", status: "running", resultUrl: null, error: null });
    renderPanel({ createExport, getExportJob });

    fireEvent.click(screen.getByRole("button", { name: "Exporter" }));
    fireEvent.click(screen.getByRole("button", { name: "PDF" }));

    // 200 tentatives × 1500ms (MAX_POLL_ATTEMPTS × POLL_INTERVAL_MS) suffit à
    // épuiser le plafond ; advanceTimersByTimeAsync flushe aussi les
    // microtâches (await client.getExportJob) entre chaque tick.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 200);
    });

    expect(screen.getByRole("alert")).toHaveTextContent(/toujours en cours/i);
    // Ni un lien de téléchargement (le job n'est jamais passé à "done") ni un
    // nouveau tick de poll après le plafond : le nombre d'appels doit
    // plafonner à MAX_POLL_ATTEMPTS et ne plus jamais grandir.
    const callsAtCap = getExportJob.mock.calls.length;
    await act(async () => {
      await vi.advanceTimersByTimeAsync(1500 * 10);
    });
    expect(getExportJob.mock.calls.length).toBe(callsAtCap);
  });
});
