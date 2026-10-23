// SPDX-License-Identifier: Apache-2.0
// L8 : mise en file des créations hors réseau depuis le formulaire d'app.
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { _resetRegistry, getWidget } from "../registry";
import { registerBuiltinWidgets } from "./index";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { CoreUnreachableError } from "../../api/CoreUnreachableError";
import type { ItemClient } from "../../api/types";
import type { WidgetContext } from "../registry";
import { OutboxStorageError } from "../../offline/outbox";
import { OutboxContext, type OutboxApi } from "../../offline/useOutbox";

beforeEach(() => {
  _resetRegistry();
  registerBuiltinWidgets();
});
afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

const fields = [
  {
    name: "titre",
    type: "string" as const,
    label: "Titre",
    order: 0,
    hidden: false,
    required: true,
  },
];

function setup(
  enqueue: OutboxApi["enqueue"],
  createFeature = vi.fn().mockResolvedValue({ id: 1 }),
) {
  const client = {
    createFeature,
    getCollectionPermission: vi.fn().mockResolvedValue(true),
  } as unknown as ItemClient;
  const api: OutboxApi = {
    ownerKey: "t:u",
    entries: [],
    pending: 0,
    paused: null,
    enqueue,
    syncNow: vi.fn(),
    resume: vi.fn(),
    remove: vi.fn(),
  };
  const Form = getWidget("form")!.Component;
  render(
    <QueryClientProvider
      client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
    >
      <ItemClientProvider client={client}>
        <OutboxContext.Provider value={api}>
          <Form
            props={{ dataSourceId: "ds1", fields, submitLabel: "Enregistrer" }}
            ctx={
              {
                mode: "runtime",
                data: { loading: false, error: false, records: [], layer: "incidents" },
                widgetId: "f1",
              } as WidgetContext
            }
          />
        </OutboxContext.Provider>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { createFeature, api };
}

test("hors réseau : la création est mise en file (même opId), aucun appel réseau, formulaire vidé APRÈS l'écriture locale", async () => {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  let release!: () => void;
  const enqueue = vi.fn(() => new Promise<void>((r) => (release = r)));
  const { createFeature } = setup(enqueue);
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(enqueue).toHaveBeenCalledTimes(1));
  // L'écriture IndexedDB n'est pas finie : la saisie est encore à l'écran.
  expect(screen.getByLabelText("Titre")).toHaveValue("Fuite");
  release();
  await waitFor(() => expect(screen.getByLabelText("Titre")).toHaveValue(""));
  expect(createFeature).not.toHaveBeenCalled();
  const [entry] = enqueue.mock.calls[0] as unknown as [{ opId: string; payload: unknown }];
  expect(entry.opId).toMatch(/^[0-9a-f-]{36}$/);
  expect(entry.payload).toEqual({ properties: { titre: "Fuite" }, geometry: null });
  expect(screen.getByRole("status")).toHaveTextContent(/Hors-ligne/);
});

test("échec de l'écriture locale : le formulaire reste ouvert avec un message", async () => {
  vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
  setup(vi.fn().mockRejectedValue(new OutboxStorageError()));
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await screen.findByText(/Impossible d'enregistrer sur cet appareil/);
  expect(screen.getByLabelText("Titre")).toHaveValue("Fuite");
});

test("en ligne mais cœur injoignable : l'envoi échoue puis la saisie est mise en file avec la MÊME clé d'idempotence", async () => {
  const createFeature = vi.fn().mockRejectedValue(new CoreUnreachableError());
  const enqueue = vi.fn().mockResolvedValue(undefined);
  setup(enqueue, createFeature);
  await userEvent.type(screen.getByLabelText("Titre"), "Fuite");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(enqueue).toHaveBeenCalledTimes(1));
  const key = (createFeature.mock.calls[0][2] as { idempotencyKey: string }).idempotencyKey;
  expect((enqueue.mock.calls[0][0] as { opId: string }).opId).toBe(key);
});
