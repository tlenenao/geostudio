// SPDX-License-Identifier: Apache-2.0
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { AlertEvaluation, AlertRuleSummary, ItemClient } from "../api/types";
import { AlertRuleEditor } from "./AlertRuleEditor";

function renderWithClient(client: Partial<ItemClient>) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client as ItemClient}>
        <AlertRuleEditor datasetItemId="ds-1" owner="alice" />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("renders the list of existing rules with their firing state", async () => {
  const listAlertRulesForDataset = vi
    .fn()
    .mockResolvedValue([{ itemId: "rule-1", title: "High counts" }] satisfies AlertRuleSummary[]);
  const getAlertEvaluations = vi.fn().mockResolvedValue([
    {
      id: "e1",
      value: 150,
      state: "firing",
      transitioned: true,
      error: null,
      createdAt: "2026-08-07T00:00:00Z",
    },
  ] satisfies AlertEvaluation[]);
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

test("shows an error banner instead of a silent empty list when the rules fetch fails", async () => {
  const listAlertRulesForDataset = vi.fn().mockRejectedValue(new Error("Request failed: 500"));
  renderWithClient({ listAlertRulesForDataset });

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Impossible de charger les règles d'alerte.",
  );
});

test("le canal email envoie AlertChannelEmail avec smtpSecretName choisi via SecretParamSelect", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue([]);
  const createAlertRuleItem = vi.fn().mockResolvedValue({ pk: "rule-3" });
  const listSecrets = vi
    .fn()
    .mockResolvedValue([
      { id: "s1", name: "smtp-prod", kind: "smtp", createdAt: "", updatedAt: "" },
    ]);
  renderWithClient({ listAlertRulesForDataset, createAlertRuleItem, listSecrets });

  await userEvent.type(await screen.findByLabelText("Nom de la règle"), "R");
  await userEvent.type(screen.getByLabelText("Condition (expression)"), "value > 1");
  await userEvent.selectOptions(screen.getByLabelText("Canal"), "email");
  await userEvent.type(screen.getByLabelText("Destinataire"), "a@b.c");
  await waitFor(() =>
    expect(screen.getByRole("option", { name: "smtp-prod" })).toBeInTheDocument(),
  );
  await userEvent.selectOptions(screen.getByLabelText("secretName"), "smtp-prod");
  await userEvent.click(screen.getByRole("button", { name: "Créer la règle" }));

  await waitFor(() => expect(createAlertRuleItem).toHaveBeenCalledTimes(1));
  const call = createAlertRuleItem.mock.calls[0][0];
  expect(call.alert.channels).toEqual([
    { kind: "email", to: "a@b.c", smtpSecretName: "smtp-prod" },
  ]);
});

test("la requête envoyée reflète agg/field/p choisis, pas {agg:'count'} figé", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue([]);
  const createAlertRuleItem = vi.fn().mockResolvedValue({ pk: "rule-4" });
  renderWithClient({ listAlertRulesForDataset, createAlertRuleItem });

  await userEvent.type(await screen.findByLabelText("Nom de la règle"), "R");
  await userEvent.type(screen.getByLabelText("Condition (expression)"), "value > 1");
  await userEvent.click(screen.getByLabelText("URL du webhook"));
  await userEvent.type(screen.getByLabelText("URL du webhook"), "https://example.test/hook");
  await userEvent.selectOptions(screen.getByLabelText("Agrégat"), "percentile");
  await userEvent.type(screen.getByLabelText("Champ"), "amount");
  await userEvent.clear(screen.getByLabelText("Centile"));
  await userEvent.type(screen.getByLabelText("Centile"), "90");
  await userEvent.click(screen.getByRole("button", { name: "Créer la règle" }));

  await waitFor(() => expect(createAlertRuleItem).toHaveBeenCalledTimes(1));
  const call = createAlertRuleItem.mock.calls[0][0];
  expect(call.alert.query).toEqual({ agg: "percentile", field: "amount", p: 90 });
});

test("l'agrégat count n'envoie ni field ni p", async () => {
  const listAlertRulesForDataset = vi.fn().mockResolvedValue([]);
  const createAlertRuleItem = vi.fn().mockResolvedValue({ pk: "rule-5" });
  renderWithClient({ listAlertRulesForDataset, createAlertRuleItem });

  await userEvent.type(await screen.findByLabelText("Nom de la règle"), "R");
  await userEvent.type(screen.getByLabelText("Condition (expression)"), "value > 1");
  await userEvent.click(screen.getByLabelText("URL du webhook"));
  await userEvent.type(screen.getByLabelText("URL du webhook"), "https://example.test/hook");
  await userEvent.click(screen.getByRole("button", { name: "Créer la règle" }));

  await waitFor(() => expect(createAlertRuleItem).toHaveBeenCalledTimes(1));
  const call = createAlertRuleItem.mock.calls[0][0];
  expect(call.alert.query).toEqual({ agg: "count" });
});

test("affiche un bouton Charger plus quand la page d'évaluations est pleine, et récupère une page plus grande au clic", async () => {
  const listAlertRulesForDataset = vi
    .fn()
    .mockResolvedValue([
      { itemId: "rule-1", title: "Historique complet" },
    ] satisfies AlertRuleSummary[]);
  const fullPage: AlertEvaluation[] = Array.from({ length: 100 }, (_, i) => ({
    id: `e${i}`,
    value: i,
    state: "ok",
    transitioned: false,
    error: null,
    createdAt: "2026-08-07T00:00:00Z",
  }));
  const getAlertEvaluations = vi.fn().mockResolvedValue(fullPage);
  renderWithClient({ listAlertRulesForDataset, getAlertEvaluations });

  expect(await screen.findByText("Historique complet")).toBeInTheDocument();
  const loadMoreButton = await screen.findByRole("button", { name: "Charger plus" });

  await userEvent.click(loadMoreButton);

  await waitFor(() => expect(getAlertEvaluations).toHaveBeenCalledTimes(2));
  expect(getAlertEvaluations).toHaveBeenLastCalledWith("rule-1", {
    limit: 200,
    offset: undefined,
  });
});

test("n'affiche pas de bouton Charger plus quand la page d'évaluations n'est pas pleine", async () => {
  const listAlertRulesForDataset = vi
    .fn()
    .mockResolvedValue([
      { itemId: "rule-1", title: "Peu d'historique" },
    ] satisfies AlertRuleSummary[]);
  const getAlertEvaluations = vi.fn().mockResolvedValue([
    {
      id: "e1",
      value: 1,
      state: "ok",
      transitioned: false,
      error: null,
      createdAt: "2026-08-07T00:00:00Z",
    },
  ] satisfies AlertEvaluation[]);
  renderWithClient({ listAlertRulesForDataset, getAlertEvaluations });

  expect(await screen.findByText("Peu d'historique")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Charger plus" })).not.toBeInTheDocument();
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
