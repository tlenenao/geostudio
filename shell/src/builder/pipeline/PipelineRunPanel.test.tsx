// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, PipelineRun } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineRunPanel } from "./PipelineRunPanel";

function renderPanel(overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([] as PipelineRun[]),
    ...overrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return client;
}

test("shows the run history from getPipelineRuns on mount", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-0", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null, nodeStats: {} },
    ]),
  });
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument());
});

test("clicking Exécuter runs the pipeline then polls until the run leaves queued/running", async () => {
  let call = 0;
  const getPipelineRuns = vi.fn().mockImplementation(() => {
    call += 1;
    const status = call < 2 ? "running" : "succeeded";
    return Promise.resolve([{ id: "run-1", status, startedAt: "2026-08-06T10:00:00Z", finishedAt: null, error: null, nodeStats: {} }]);
  });
  renderPanel({ getPipelineRuns });
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await waitFor(() => expect(screen.getByText("succeeded")).toBeInTheDocument(), { timeout: 5000 });
  expect(call).toBeGreaterThanOrEqual(2);
});

test("a failed run shows its error message", async () => {
  renderPanel({
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-2", status: "failed", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:01Z", error: "collection introuvable", nodeStats: {} },
    ]),
  });
  await waitFor(() => expect(screen.getByText("collection introuvable")).toBeInTheDocument());
});

test("if runPipeline itself fails, the button re-enables and shows an error instead of staying stuck", async () => {
  renderPanel({
    runPipeline: vi.fn().mockRejectedValue(new Error("réseau indisponible")),
  });
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Exécuter" })).toBeEnabled());
  expect(screen.getByRole("alert")).toHaveTextContent("réseau indisponible");
});

test("calls onLatestRunChange with the newest run whenever the run list is (re)loaded", async () => {
  const onLatestRunChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([
      { id: "run-0", status: "succeeded", startedAt: "2026-08-06T10:00:00Z", finishedAt: "2026-08-06T10:00:02Z", error: null, nodeStats: {} },
    ]),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" onLatestRunChange={onLatestRunChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(onLatestRunChange).toHaveBeenCalledWith(
    expect.objectContaining({ id: "run-0" }),
  ));
});

test("calls onLatestRunChange with null when there is no run yet", async () => {
  const onLatestRunChange = vi.fn();
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    runPipeline: vi.fn().mockResolvedValue({ runId: "run-1" }),
    getPipelineRuns: vi.fn().mockResolvedValue([]),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineRunPanel pipelineId="p-1" onLatestRunChange={onLatestRunChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(onLatestRunChange).toHaveBeenCalledWith(null));
});
