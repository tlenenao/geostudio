// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LlmGovernancePage } from "./LlmGovernancePage";

beforeEach(() => {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "me",
        firstName: "Moi",
        lastName: "Même",
        email: "me@example.com",
        tenantId: "t1",
        tenantSlug: "demo",
        role: { id: "r", name: "A", slug: "admin" },
        privileges: ["settings.instance.manage"],
        version: "0.1.0",
      }),
    ),
    http.get("https://core.test/v1/copilot/usage", () =>
      HttpResponse.json({
        dailyLimit: 1000,
        usedToday: 250,
        days: [{ day: "2026-10-18", calls: 3, promptTokens: 200, completionTokens: 50 }],
      }),
    ),
  );
});
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <LlmGovernancePage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("affiche la consommation du jour et le tableau par jour", async () => {
  server.use(
    http.get("https://core.test/v1/copilot/llm-settings", () =>
      HttpResponse.json({ configured: false, hasApiKey: false }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText(/250 jetons sur 1\s000 autorisés/)).toBeVisible();
  const table = screen.getByRole("table", { name: "Consommation de jetons" });
  expect(within(table).getByRole("rowheader", { name: "2026-10-18" })).toBeVisible();
});

test("enregistre sans renvoyer la clé quand le champ est vide, puis la supprime", async () => {
  let body: unknown = null;
  let deleted = false;
  server.use(
    http.get("https://core.test/v1/copilot/llm-settings", () =>
      HttpResponse.json(
        deleted
          ? { configured: false, hasApiKey: false }
          : {
              configured: true,
              model: "m1",
              apiUrl: "https://api.example.com/v1",
              hasApiKey: true,
            },
      ),
    ),
    http.put("https://core.test/v1/copilot/llm-settings", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ configured: true, model: "m2", hasApiKey: true });
    }),
    http.delete("https://core.test/v1/copilot/llm-settings", () => {
      deleted = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  const model = await screen.findByLabelText("Modèle");
  await waitFor(() => expect(model).toHaveValue("m1"));
  expect(
    screen.getByText("Une clé est enregistrée ; laissez vide pour la conserver."),
  ).toBeVisible();
  await userEvent.clear(model);
  await userEvent.type(model, "m2");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText("Réglages enregistrés.")).toBeVisible();
  expect(body).toEqual({
    model: "m2",
    apiUrl: "https://api.example.com/v1",
    dailyTokenLimit: null,
  });

  await userEvent.click(
    screen.getByRole("button", { name: "Revenir au fournisseur de l'instance" }),
  );
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Revenir au fournisseur de l'instance" }),
  );
  expect(await screen.findByText("Réglages supprimés.")).toBeVisible();
});

test("affiche l'erreur 422 du cœur (URL refusée)", async () => {
  server.use(
    http.get("https://core.test/v1/copilot/llm-settings", () =>
      HttpResponse.json({ configured: false, hasApiKey: false }),
    ),
    http.put("https://core.test/v1/copilot/llm-settings", () =>
      HttpResponse.json(
        {
          type: "about:blank",
          title: "Unprocessable",
          status: 422,
          detail: "URL du fournisseur refusée : interne",
        },
        { status: 422, headers: { "content-type": "application/problem+json" } },
      ),
    ),
  );
  render(<Harness />);
  await userEvent.type(await screen.findByLabelText("URL de l'API"), "http://10.0.0.1");
  await userEvent.type(screen.getByLabelText("Clé d'API"), "k");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("URL du fournisseur refusée");
});
