// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ApiError } from "../../api/ApiError";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { ItemClient, PipelineRun } from "../../api/types";
import { PipelineRunPanel } from "./PipelineRunPanel";

// REV-310 : le 409 « un run est déjà en cours » a son message et suit le run actif.
test("un 409 au lancement affiche un message dédié et charge l'historique des runs", async () => {
  const getPipelineRuns = vi.fn().mockResolvedValue([] as PipelineRun[]);
  const client = {
    runPipeline: vi.fn().mockRejectedValue(new ApiError(409, { detail: "déjà en cours (core)" })),
    getPipelineRuns,
  } as unknown as ItemClient;
  render(
    <QueryClientProvider client={new QueryClient()}>
      <ItemClientProvider client={client}>
        <PipelineRunPanel pipelineId="p-1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(getPipelineRuns).toHaveBeenCalledTimes(1));
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent(/déjà en cours ou en file/);
  await waitFor(() => expect(getPipelineRuns.mock.calls.length).toBeGreaterThan(1));
  expect(screen.getByRole("button", { name: "Exécuter" })).toBeEnabled();
});
