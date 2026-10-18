// SPDX-License-Identifier: Apache-2.0
// L8 : libellés de choix (XLSForm `choices.label`) et `select_multiple` dans le formulaire.
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { CollectionSchema, ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import { applyDomains, type FormField } from "./form";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});

const base = { order: 0, hidden: false, required: false };
const schema: CollectionSchema = {
  collection: "c",
  pk: "id",
  geometry: null,
  fields: [
    {
      name: "etat",
      type: "string",
      required: false,
      domain: {
        type: "list",
        values: ["bon", "hs"],
        labels: { bon: "Bon état", hs: "Hors service" },
      },
    },
    {
      name: "usages",
      type: "list",
      itemType: "string",
      required: false,
      domain: { type: "list", values: ["a", "b", "c"], labels: { a: "Alpha" } },
    },
  ],
};

function renderForm(fields: FormField[], createFeature = vi.fn().mockResolvedValue({ id: 1 })) {
  const client = {
    createFeature,
    getCollectionSchema: vi.fn().mockResolvedValue(schema),
    getCollectionPermission: vi.fn().mockResolvedValue(true),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <Form
          props={{ dataSourceId: "ds", fields, submitLabel: "Envoyer", geometryType: null }}
          ctx={
            {
              mode: "runtime",
              data: { loading: false, error: false, records: [], layer: "c" },
            } as WidgetContext
          }
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return createFeature;
}

test("applyDomains : le libellé du domaine remplace la valeur, repli sur la valeur", () => {
  const f: FormField = { ...base, name: "usages", type: "string", label: "Usages" };
  const out = applyDomains([f], schema, {});
  expect(out[0].options).toEqual([
    { value: "a", label: "Alpha" },
    { value: "b", label: "b" },
    { value: "c", label: "c" },
  ]);
});

test("une liste à libellés affiche le libellé et stocke la valeur", async () => {
  const create = renderForm([{ ...base, name: "etat", type: "string", label: "État" }]);
  const select = await screen.findByRole("option", { name: "Hors service" });
  expect(select).toHaveValue("hs");
  await userEvent.selectOptions(screen.getByLabelText("État"), "hs");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(create).toHaveBeenCalled());
  expect(create.mock.calls[0][1].properties.etat).toBe("hs");
});

test("select_multiple : cases à cocher, valeurs envoyées en tableau", async () => {
  const create = renderForm([
    { ...base, name: "usages", type: "string", label: "Usages", multiple: true },
  ]);
  const group = await screen.findByRole("group", { name: "Usages" });
  expect(group).toBeInTheDocument();
  await userEvent.click(await screen.findByRole("checkbox", { name: "Alpha" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "c" }));
  await userEvent.click(screen.getByRole("checkbox", { name: "c" })); // décoché
  await userEvent.click(screen.getByRole("checkbox", { name: "b" }));
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(create).toHaveBeenCalled());
  expect(create.mock.calls[0][1].properties.usages).toEqual(["a", "b"]);
});

test("select_multiple requis : aucun choix bloque l'envoi", async () => {
  const create = renderForm([
    { ...base, name: "usages", type: "string", label: "Usages", multiple: true, required: true },
  ]);
  await screen.findByRole("checkbox", { name: "Alpha" });
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findAllByText(/obligatoire|requis/i)).not.toHaveLength(0);
  expect(create).not.toHaveBeenCalled();
});
