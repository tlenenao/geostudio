// shell/src/builder/report/ReportRunPanel.test.tsx
// SPDX-License-Identifier: Apache-2.0
import { act, render, screen, waitFor } from "@testing-library/react";
import { afterEach, expect, test, vi } from "vitest";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient, ReportRunStatus } from "../../api/types";
import { ReportRunPanel } from "./ReportRunPanel";

function run(overrides: Partial<ReportRunStatus> = {}): ReportRunStatus {
  return {
    id: "run-1", status: "done", resultUrl: "https://s3.test/renders/run-1.pdf",
    error: null, notifiedAt: null, createdAt: "2026-08-09T08:00:00Z",
    ...overrides,
  };
}

function renderPanel(getReportRuns: ItemClient["getReportRuns"]) {
  const client = { getReportRuns } as unknown as ItemClient;
  render(
    <ItemClientProvider client={client}>
      <ReportRunPanel reportId="report-1" />
    </ItemClientProvider>,
  );
}

afterEach(() => {
  vi.useRealTimers();
});

test("affiche l'historique renvoyé par getReportRuns", async () => {
  renderPanel(vi.fn().mockResolvedValue([run()]));
  await waitFor(() => expect(screen.getByText("Terminé")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "Télécharger" })).toHaveAttribute(
    "href", "https://s3.test/renders/run-1.pdf",
  );
});

test("un échec de chargement est signalé, distinct de « aucune exécution »", async () => {
  renderPanel(vi.fn().mockRejectedValue(new Error("réseau indisponible")));
  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent(
    "Impossible de charger l'historique des exécutions.",
  ));
  expect(screen.queryByText("Aucune exécution pour l'instant.")).not.toBeInTheDocument();
});

test("passe en rythme lent quand plus aucun run n'est en cours de rendu", async () => {
  vi.useFakeTimers();
  const getReportRuns = vi.fn().mockResolvedValue([run({ status: "done" })]);
  renderPanel(getReportRuns);

  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(getReportRuns).toHaveBeenCalledTimes(1);

  // Avant le correctif : un sondage toutes les 1,5 s pour toujours.
  await act(async () => { await vi.advanceTimersByTimeAsync(4500); });
  expect(getReportRuns).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(30000); });
  expect(getReportRuns).toHaveBeenCalledTimes(2);
});

test("garde le rythme rapide tant qu'un run est en cours de rendu", async () => {
  vi.useFakeTimers();
  const getReportRuns = vi.fn().mockResolvedValue([run({ status: "running", resultUrl: null })]);
  renderPanel(getReportRuns);

  await act(async () => { await vi.advanceTimersByTimeAsync(0); });
  expect(getReportRuns).toHaveBeenCalledTimes(1);

  await act(async () => { await vi.advanceTimersByTimeAsync(1500); });
  expect(getReportRuns).toHaveBeenCalledTimes(2);
});
