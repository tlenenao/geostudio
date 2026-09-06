// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { ItemClient, PipelineWebhookToken } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineWebhookTrigger } from "./PipelineWebhookTrigger";

function renderTrigger(clientOverrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    listPipelineWebhookTokens: () => Promise.resolve([]),
    ...clientOverrides,
  };
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineWebhookTrigger pipelineId="p1" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("le jeton généré s'affiche une seule fois avec un avertissement", async () => {
  const createPipelineWebhookToken = vi
    .fn()
    .mockResolvedValue({ id: "t1", token: "clear-value", createdAt: "2026-09-05T00:00:00Z" });
  renderTrigger({ createPipelineWebhookToken });

  fireEvent.click(await screen.findByText("Générer un jeton"));
  await screen.findByText("clear-value");
  expect(screen.getByText(/ne sera plus jamais affiché/)).toBeInTheDocument();
});

test("liste les jetons existants et permet la révocation", async () => {
  const tokens: PipelineWebhookToken[] = [
    { id: "t1", createdAt: "2026-09-01T00:00:00Z", lastUsedAt: null },
  ];
  const revokePipelineWebhookToken = vi.fn().mockResolvedValue(undefined);
  renderTrigger({
    listPipelineWebhookTokens: () => Promise.resolve(tokens),
    revokePipelineWebhookToken,
  });

  await waitFor(() => expect(screen.getByText(/t1/)).toBeInTheDocument());
  fireEvent.click(screen.getByLabelText("Révoquer t1"));
  await waitFor(() => expect(revokePipelineWebhookToken).toHaveBeenCalledWith("p1", "t1"));
});

test("l'URL de déclenchement complète est affichée après génération", async () => {
  const createPipelineWebhookToken = vi
    .fn()
    .mockResolvedValue({ id: "t2", token: "abc", createdAt: "2026-09-05T00:00:00Z" });
  renderTrigger({ createPipelineWebhookToken });

  fireEvent.click(await screen.findByText("Générer un jeton"));
  await screen.findByText("abc");
  expect(screen.getByText(/\/pipelines\/p1\/trigger/)).toBeInTheDocument();
});
