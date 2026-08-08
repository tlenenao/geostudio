// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AlertEvaluation, AlertRuleSummary, ItemClient } from "../api/types";
import { AlertRuleEditor } from "./AlertRuleEditor";

function renderWithClient(client: Partial<ItemClient>) {
  const queryClient = new QueryClient();
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client as ItemClient}>
        <AlertRuleEditor datasetItemId="ds-1" owner="alice" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("renders the list of existing rules with their firing state", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue(
    [{ itemId: "rule-1", title: "High counts" }] satisfies AlertRuleSummary[],
  );
  const getAlertEvaluations = vi.fn().mockResolvedValue(
    [{ id: "e1", value: 150, state: "firing", transitioned: true, error: null, createdAt: "2026-08-07T00:00:00Z" }] satisfies AlertEvaluation[],
  );
  renderWithClient({ listAlertRulesForDataset, getAlertEvaluations });

  expect(await screen.findByText("High counts")).toBeInTheDocument();
  expect(await screen.findByText(/firing/i)).toBeInTheDocument();
});

test("creating a rule calls createAlertRuleItem with the form values", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue([]);
  const createAlertRuleItem = vi.fn().mockResolvedValue({ pk: "rule-2" });
  renderWithClient({ listAlertRulesForDataset, createAlertRuleItem });

  await userEvent.type(await screen.findByLabelText("Nom de la règle"), "Trop de signalements");
  await userEvent.type(screen.getByLabelText("Condition (expression)"), "value > 50");
  await userEvent.click(screen.getByLabelText("URL du webhook"));
  await userEvent.type(screen.getByLabelText("URL du webhook"), "https://example.test/hook");
  await userEvent.click(screen.getByRole("button", { name: "Créer la règle" }));

  await waitFor(() => expect(createAlertRuleItem).toHaveBeenCalledTimes(1));
  const call = createAlertRuleItem.mock.calls[0][0];
  expect(call.alert.datasetItemId).toBe("ds-1");
  expect(call.alert.condition.expr).toBe("value > 50");
  expect(call.alert.channels).toEqual([{ kind: "webhook", url: "https://example.test/hook" }]);
});

test("shows a save error inline instead of failing silently", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue([]);
  const createAlertRuleItem = vi.fn().mockRejectedValue(new Error("Request failed: 422"));
  renderWithClient({ listAlertRulesForDataset, createAlertRuleItem });

  await userEvent.type(await screen.findByLabelText("Nom de la règle"), "R");
  await userEvent.type(screen.getByLabelText("Condition (expression)"), "value > 1");
  await userEvent.click(screen.getByLabelText("URL du webhook"));
  await userEvent.type(screen.getByLabelText("URL du webhook"), "https://example.test/hook");
  await userEvent.click(screen.getByRole("button", { name: "Créer la règle" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("Échec de la création de la règle.");
});
