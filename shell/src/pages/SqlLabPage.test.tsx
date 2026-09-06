// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { SqlLabPage } from "./SqlLabPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que ReportEditPage.test.tsx
// et PipelineBuilderPage.test.tsx) — SqlLabPage ne rendait pas
// TriptychLayout avant ce plan, ce stub est nouveau dans ce fichier.
function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => {
  stubMatchMedia(false);
  localStorage.clear();
});
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <SqlLabPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("exécute une requête et affiche le tableau de résultat", async () => {
  let posted: unknown;
  server.use(
    http.post("https://core.test/v1/analytics/sql", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({
        columns: ["nom", "surface"],
        rows: [
          ["Parc A", 12],
          ["Parc B", 30],
        ],
        truncated: false,
      });
    }),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select nom, surface from parcs");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("columnheader", { name: "nom" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "Parc A" })).toBeInTheDocument();
  expect(screen.getByRole("cell", { name: "30" })).toBeInTheDocument();
  await waitFor(() => expect(posted).toEqual({ sql: "select nom, surface from parcs" }));
});

test("affiche l'avis de troncature quand le résultat a été plafonné", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: true }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByText("Résultat tronqué aux 1 premières lignes.")).toBeInTheDocument();
});

test("affiche le message d'erreur du serveur et conserve le texte SQL en cas d'échec", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json(
        {
          errors: [{ field: "sql", code: "sql_error", message: "Parser Error: syntax error" }],
        },
        { status: 400 },
      ),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Parser Error: syntax error");
  expect(textarea).toHaveValue("select * fro x");
});

test("enregistre l'historique au succès et recharge une requête passée au clic", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: false }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByLabelText("Requête SQL");
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByRole("columnheader", { name: "id" });
  await userEvent.clear(textarea);
  const historyButton = await screen.findByRole("button", {
    name: "Recharger la requête : select id from x",
  });
  await userEvent.click(historyButton);
  expect(textarea).toHaveValue("select id from x");
});

test("affiche un état vide dans l'onglet Historique tant qu'aucune requête n'a été exécutée", async () => {
  render(<Harness />);
  await screen.findByLabelText("Requête SQL");
  expect(screen.getByText("Aucune requête exécutée pour l'instant.")).toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Requête/Historique avec Requête actif par défaut", async () => {
  stubMatchMedia(true);
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Requête", "Historique"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Requête");
});
