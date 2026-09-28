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
import { enableMockAuth } from "../auth/useAuth";
import { SqlLabPage } from "./SqlLabPage";

// Le panneau copilote (SqlLabCopilotPanel → CopilotChat → useMcpToken)
// bascule sur un jeton MCP factice en mode mock plutôt que d'exiger un
// vrai <AuthProvider> react-oidc-context autour de ce Harness — même
// patron que CopilotChat.test.tsx. Sans effet sur les tests existants de
// ce fichier (SqlLabPage n'appelle useAuth()/useMcpToken() nulle part
// ailleurs).
enableMockAuth();

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que ReportEditPage.test.tsx
// et PipelineBuilderPage.test.tsx) — SqlLabPage ne rendait pas
// TriptychLayout avant ce plan, ce stub est nouveau dans ce fichier.
// jsdom n'implémente ni Range.prototype.getClientRects ni
// Range.prototype.getBoundingClientRect (piège n°10 CLAUDE.md, même classe
// que ResizeObserver/hasPointerCapture/scrollIntoView/PointerEvent) —
// CodeMirror 6 les appelle pour mesurer le texte à chaque rendu. Sans ce
// polyfill minimal, local à ce fichier de test, toute assertion après un
// rendu de <CodeMirror> lève une TypeError asynchrone (rAF de mesure).
if (!Range.prototype.getClientRects) {
  Range.prototype.getClientRects = function () {
    return [] as unknown as DOMRectList;
  };
}
if (!Range.prototype.getBoundingClientRect) {
  Range.prototype.getBoundingClientRect = function () {
    return {
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      top: 0,
      right: 0,
      bottom: 0,
      left: 0,
      toJSON() {
        return this;
      },
    } as DOMRect;
  };
}

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

function Harness({ initialEntries }: { initialEntries?: string[] } = {}) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter initialEntries={initialEntries ?? ["/"]}>
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
  const textarea = await screen.findByRole("textbox", { name: "Requête SQL" });
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
  const textarea = await screen.findByRole("textbox", { name: "Requête SQL" });
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
  const textarea = await screen.findByRole("textbox", { name: "Requête SQL" });
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Parser Error: syntax error");
  // `textarea` est un div contenteditable (CodeMirror) : `toHaveValue` ne
  // s'applique qu'aux éléments de formulaire natifs (input/textarea/select),
  // le contenu se lit via `textContent` — vérifié empiriquement.
  expect(textarea).toHaveTextContent("select * fro x");
});

test("affiche la ligne et l'extrait SQL quand le message DuckDB porte une position", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json(
        {
          errors: [
            {
              field: "sql",
              code: "sql_error",
              message:
                'Parser Error: syntax error at or near "fro"\n\nLINE 1: select * fro x\n                ^',
            },
          ],
        },
        { status: 400 },
      ),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByRole("textbox", { name: "Requête SQL" });
  await userEvent.type(textarea, "select * fro x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  const alert = await screen.findByRole("alert");
  expect(alert).toHaveTextContent("Parser Error");
  expect(alert).toHaveTextContent('syntax error at or near "fro"');
  expect(alert).toHaveTextContent("Ligne 1");
  expect(alert).toHaveTextContent("select * fro x");
});

test("enregistre l'historique au succès et recharge une requête passée au clic", async () => {
  server.use(
    http.post("https://core.test/v1/analytics/sql", () =>
      HttpResponse.json({ columns: ["id"], rows: [["1"]], truncated: false }),
    ),
  );
  render(<Harness />);
  const textarea = await screen.findByRole("textbox", { name: "Requête SQL" });
  await userEvent.type(textarea, "select id from x");
  await userEvent.click(screen.getByRole("button", { name: "Exécuter" }));
  await screen.findByRole("columnheader", { name: "id" });
  await userEvent.clear(textarea);
  const historyButton = await screen.findByRole("button", {
    name: "Recharger la requête : select id from x",
  });
  await userEvent.click(historyButton);
  expect(textarea).toHaveTextContent("select id from x");
});

test("restaure la requête sélectionnée dans l'historique via l'URL", async () => {
  localStorage.setItem(
    "geostudio.sqlLab.history",
    JSON.stringify([
      { id: "h1", sql: "select 2", executedAt: "2026-09-26T00:00:00Z", status: "ok", rowCount: 1 },
    ]),
  );
  render(<Harness initialEntries={["/analytics/sql?historyId=h1"]} />);
  expect(await screen.findByRole("textbox", { name: /requête/i })).toHaveTextContent("select 2");
});

test("ignore un historyId inconnu dans l'URL sans planter, et laisse le SQL inchangé", async () => {
  localStorage.setItem(
    "geostudio.sqlLab.history",
    JSON.stringify([
      { id: "h1", sql: "select 2", executedAt: "2026-09-26T00:00:00Z", status: "ok", rowCount: 1 },
    ]),
  );
  render(<Harness initialEntries={["/analytics/sql?historyId=inconnu"]} />);
  // `toHaveTextContent("")` matcherait n'importe quel contenu (sous-chaîne
  // vide toujours incluse) : comparer le textContent brut à la place.
  expect((await screen.findByRole("textbox", { name: /requête/i })).textContent).toBe("");
});

test("affiche un état vide dans l'onglet Historique tant qu'aucune requête n'a été exécutée", async () => {
  render(<Harness />);
  await screen.findByRole("textbox", { name: "Requête SQL" });
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

test("n'affiche pas le panneau copilote quand copilotEnabled est faux (défaut du handler /instance)", async () => {
  render(<Harness />);
  await screen.findByRole("textbox", { name: "Requête SQL" });
  expect(screen.queryByLabelText("Message au copilote")).not.toBeInTheDocument();
});

function mockCollectionsList() {
  return http.get("https://core.test/v1/collections", () =>
    HttpResponse.json({
      collections: [
        {
          id: "parcs",
          title: "Parcs urbains",
          description: "",
          tableName: "parcs",
          isPublic: false,
          editable: true,
          geometryType: "Point",
          srid: 4326,
          pkColumn: "id",
          permissions: { read: true, write: true, delete: true, share: true },
          featureCount: 3,
          owner: "alice",
          attachmentFields: [],
        },
      ],
      numberMatched: 1,
      numberReturned: 1,
    }),
  );
}

test("affiche le panneau copilote et insère le brouillon SQL généré sans l'exécuter", async () => {
  let executed = false;
  server.use(
    mockCollectionsList(),
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, copilotEnabled: true }),
    ),
    http.post("https://core.test/v1/copilot/turn", () =>
      HttpResponse.json({
        reply: "Voici un brouillon.",
        clientOps: [{ op: "applySqlDraft", args: { sql: "select 1" } }],
      }),
    ),
    http.post("https://core.test/v1/analytics/sql", async ({ request }) => {
      executed = true;
      return HttpResponse.json(await request.json());
    }),
  );
  render(<Harness />);
  await userEvent.type(await screen.findByLabelText("Message au copilote"), "une requête simple");
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  expect(await screen.findByRole("textbox", { name: "Requête SQL" })).toHaveTextContent("select 1");
  expect(executed).toBe(false);
});

// I1 (revue finale de branche GAP-17) : sans la liste des collections dans
// le contexte, `generate_sql_query` — qui EXIGE un `collectionId` — est
// inutilisable sur SQL Lab avec un vrai fournisseur LLM : aucun des 8 outils
// MCP de l'allowlist du copilote n'énumère les collections (explain_dataset
// omet délibérément `collectionId`, search_collections/list_collections ne
// sont pas allowlistés) et le volet Catalogue de cette page n'est qu'un lien
// de retour. Même mécanisme que `baseCollectionId` déjà passé par
// VisualQueryCopilotPanel.
test("transmet au copilote la liste des collections visibles dans le contexte", async () => {
  let payload: { currentConfig?: { sql?: string; collections?: unknown } } | null = null;
  server.use(
    mockCollectionsList(),
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, copilotEnabled: true }),
    ),
    http.post("https://core.test/v1/copilot/turn", async ({ request }) => {
      payload = (await request.json()) as typeof payload;
      return HttpResponse.json({ reply: "ok", clientOps: [] });
    }),
  );
  render(<Harness />);
  await userEvent.type(await screen.findByLabelText("Message au copilote"), "les parcs");
  await waitFor(() => expect(screen.getByRole("button", { name: "Envoyer" })).toBeEnabled());
  await userEvent.click(screen.getByRole("button", { name: "Envoyer" }));
  await waitFor(() => expect(payload).not.toBeNull());
  expect(payload!.currentConfig).toEqual({
    sql: "",
    collections: [{ id: "parcs", title: "Parcs urbains" }],
  });
});
