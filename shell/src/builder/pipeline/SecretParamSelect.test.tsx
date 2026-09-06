// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, SecretSummary } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { SecretParamSelect } from "./SecretParamSelect";

const SECRETS: SecretSummary[] = [
  { id: "s1", name: "arcgis", kind: "api_key", createdAt: "", updatedAt: "" },
  { id: "s2", name: "pg", kind: "postgres_dsn", createdAt: "", updatedAt: "" },
];

function renderSelect(
  props: Partial<Parameters<typeof SecretParamSelect>[0]> = {},
  clientOverrides: Partial<ItemClient> = {},
) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const onChange = vi.fn();
  const client: Partial<ItemClient> = {
    listSecrets: () => Promise.resolve(SECRETS),
    ...clientOverrides,
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <SecretParamSelect value="" onChange={onChange} ariaLabel="secretName" {...props} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange };
}

test("liste les secrets existants filtrés par kind", async () => {
  renderSelect({ kindFilter: "postgres_dsn" });
  await waitFor(() => expect(screen.getByRole("option", { name: "pg" })).toBeInTheDocument());
  expect(screen.queryByRole("option", { name: "arcgis" })).not.toBeInTheDocument();
});

// REV-062 (backlog 2026-09-04) : le formulaire de création peint
// `bg-sunken` sans jamais poser `text-ink` — texte des libellés noir sur
// fond quasi noir en ambiance sombre, faute d'un token de couleur de texte
// hérité d'un ancêtre.
test("the create-secret form carries the text-ink token alongside bg-sunken", async () => {
  renderSelect();
  await waitFor(() => expect(screen.getByRole("option", { name: "arcgis" })).toBeInTheDocument());
  await userEvent.click(screen.getByText("Créer un secret"));
  const form = (await screen.findByLabelText("Nom")).closest("form") as HTMLElement;
  expect(form).not.toBeNull();
  expect(form.className).toContain("bg-sunken");
  expect(form.className).toContain("text-ink");
});

test("sans kindFilter, tous les secrets sont proposés", async () => {
  renderSelect();
  await waitFor(() => expect(screen.getByRole("option", { name: "arcgis" })).toBeInTheDocument());
  expect(screen.getByRole("option", { name: "pg" })).toBeInTheDocument();
});

test("selecting an option calls onChange with the secret's name", async () => {
  const { onChange } = renderSelect();
  await waitFor(() => expect(screen.getByRole("option", { name: "arcgis" })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("secretName"), "arcgis");
  expect(onChange).toHaveBeenCalledWith("arcgis");
});

test("un nouveau secret créé est immédiatement sélectionné", async () => {
  const createSecret = vi.fn().mockResolvedValue({
    id: "s3",
    name: "smtp-prod",
    kind: "smtp",
    createdAt: "",
    updatedAt: "",
  });
  const { onChange } = renderSelect({ kindFilter: "smtp" }, { createSecret });
  await userEvent.click(screen.getByText("Créer un secret"));
  await userEvent.type(screen.getByLabelText("Nom"), "smtp-prod");
  await userEvent.type(screen.getByLabelText("Hôte"), "smtp.example.test");
  await userEvent.type(screen.getByLabelText("Port"), "587");
  await userEvent.type(screen.getByLabelText("Nom d'utilisateur"), "u");
  await userEvent.type(screen.getByLabelText("Mot de passe"), "p");
  await userEvent.type(screen.getByLabelText("Adresse d'expédition"), "noreply@example.test");
  await userEvent.click(screen.getByText("Créer"));
  await waitFor(() => expect(onChange).toHaveBeenCalledWith("smtp-prod"));
  expect(createSecret).toHaveBeenCalledWith({
    name: "smtp-prod",
    payload: {
      kind: "smtp",
      host: "smtp.example.test",
      port: 587,
      username: "u",
      password: "p",
      useTls: true,
      fromAddress: "noreply@example.test",
    },
  });
});
