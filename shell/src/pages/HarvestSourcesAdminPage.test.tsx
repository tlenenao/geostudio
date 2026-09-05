// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { expectAriaWired } from "../test/expectAriaWired";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { HarvestSourcesAdminPage } from "./HarvestSourcesAdminPage";

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. Stub local, avec vi.unstubAllGlobals()
// en afterEach dès son introduction (même patron que SqlLabPage.test.tsx,
// SP-30i).
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

beforeEach(() => stubMatchMedia(false));
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <HarvestSourcesAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("admin creates a STAC source and triggers a manual run", async () => {
  let created: Record<string, unknown> | null = null;
  let ran = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: created
          ? [
              {
                id: "src-1",
                type: "stac",
                url: "https://stac.example.com/collections",
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: null,
                lastStatus: ran ? "ok" : null,
                lastError: null,
              },
            ]
          : [],
      }),
    ),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      created = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { id: "src-1", ...created, lastRunAt: null, lastStatus: null, lastError: null },
        { status: 201 },
      );
    }),
    http.post("https://core.test/harvest/sources/src-1/run", () => {
      ran = true;
      return HttpResponse.json({ status: "queued" }, { status: 202 });
    }),
  );
  render(<Harness />);
  const addButton = await screen.findByRole("button", { name: "Ajouter une source" });
  expectAriaWired(addButton, addButton.getAttribute("aria-controls")!, false);
  await userEvent.click(addButton);
  expectAriaWired(addButton, addButton.getAttribute("aria-controls")!, true);
  await userEvent.type(await screen.findByLabelText("URL"), "https://stac.example.com/collections");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(created).not.toBeNull());
  expect(await screen.findByText("https://stac.example.com/collections")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Moissonner maintenant" }));
  await waitFor(() => expect(ran).toBe(true));
});

test("edits a source via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
    http.patch("https://core.test/harvest/sources/src-1", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({
        id: "src-1",
        type: "stac",
        url: "https://a (édité)",
        mode: "reference",
        enabled: true,
        intervalMinutes: null,
        lastRunAt: null,
        lastStatus: null,
        lastError: null,
      });
    }),
  );
  render(<Harness />);
  const editButton = await screen.findByRole("button", { name: "Éditer" });
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, false);
  await userEvent.click(editButton);
  const urlInput = await screen.findByLabelText("URL");
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, true);
  await userEvent.clear(urlInput);
  await userEvent.type(urlInput, "https://a (édité)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ url: "https://a (édité)" }));
});

test("aria-expanded est câblé par ligne, pas partagé entre toutes les lignes (revue finale SP-43, Important I2)", async () => {
  // Fixture à 2 sources : le défaut trouvé en revue finale (aria-expanded
  // posé une seule fois pour toute la page via {...editPanel.triggerProps}
  // dans .map()) était invisible avec une seule source — tous les boutons
  // Éditer basculaient aria-expanded="true" en même temps.
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
          {
            id: "src-2",
            type: "stac",
            url: "https://b",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
  );

  render(<Harness />);
  const editButtons = await screen.findAllByRole("button", { name: "Éditer" });
  expect(editButtons).toHaveLength(2);
  editButtons.forEach((button) => expect(button).toHaveAttribute("aria-expanded", "false"));

  await userEvent.click(editButtons[0]);
  await screen.findByLabelText("URL");

  expect(editButtons[0]).toHaveAttribute("aria-expanded", "true");
  expect(editButtons[1]).toHaveAttribute("aria-expanded", "false");
});

test("cliquer « Ajouter une source » pendant l'édition ferme le panneau d'édition", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  expect(await screen.findByRole("region", { name: "Éditer https://a" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  expect(screen.queryByRole("region", { name: "Éditer https://a" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Ajouter une source" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Enregistrer" })).toHaveLength(1);
});

test("cliquer « Éditer » pendant la création ferme le panneau d'ajout", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  expect(await screen.findByRole("region", { name: "Ajouter une source" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Éditer" }));
  expect(screen.queryByRole("region", { name: "Ajouter une source" })).not.toBeInTheDocument();
  expect(screen.getByRole("region", { name: "Éditer https://a" })).toBeInTheDocument();
  expect(screen.getAllByRole("button", { name: "Enregistrer" })).toHaveLength(1);
});

test("supprimer la source en cours d'édition ferme le panneau Éditer (croisement editing/deleting)", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://a",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: null,
            lastError: null,
          },
        ],
      }),
    ),
    http.delete("https://core.test/harvest/sources/src-1", () =>
      HttpResponse.text("", { status: 204 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  expect(await screen.findByRole("region", { name: "Éditer https://a" })).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));

  await waitFor(() =>
    expect(screen.queryByRole("region", { name: "Éditer https://a" })).not.toBeInTheDocument(),
  );
});

test("delete removes the source from the list", async () => {
  let deleted = false;
  server.use(
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: deleted
          ? []
          : [
              {
                id: "src-1",
                type: "stac",
                url: "https://a",
                mode: "reference",
                enabled: true,
                intervalMinutes: null,
                lastRunAt: null,
                lastStatus: null,
                lastError: null,
              },
            ],
      }),
    ),
    http.delete("https://core.test/harvest/sources/src-1", () => {
      deleted = true;
      return HttpResponse.text("", { status: 204 });
    }),
  );
  render(<Harness />);
  await screen.findByText("https://a");
  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  // Le bouton de la ligne et celui du ConfirmDialog partagent le même nom
  // accessible une fois le dialogue ouvert — on scope au dialogue (même
  // patron que CollectionsAdminPage.test.tsx : within(dialog).getByRole).
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleted).toBe(true));
  await waitFor(() => expect(screen.queryByText("https://a")).not.toBeInTheDocument());
});

test("masque les boutons d'écriture en mode démo (read-only)", async () => {
  server.use(
    http.get("https://core.test/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/harvest/sources", () =>
      HttpResponse.json({
        sources: [
          {
            id: "s1",
            type: "stac",
            url: "https://stac/x",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: "ok",
            lastError: null,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await screen.findByText("https://stac/x");
  expect(screen.queryByRole("button", { name: "Ajouter une source" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Moissonner maintenant" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Éditer" })).toBeNull();
  expect(screen.queryByRole("button", { name: "Supprimer" })).toBeNull();
});

test("sends the selected type (arcgis) on creation", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "arcgis",
          url: "https://x/FeatureServer",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://x/FeatureServer");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "arcgis");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "arcgis",
      url: "https://x/FeatureServer",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("envoie le type WMS et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "wms",
          url: "https://ows/x",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://ows/x");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "wms");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({ type: "wms", url: "https://ows/x", mode: "reference", enabled: true }),
  );
});

test("garde le mode copie disponible pour WFS", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "wfs");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});

test("envoie le type CSW et force le mode référence (copie désactivée)", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "csw",
          url: "https://geonetwork.example.com/csw",
          mode: "reference",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://geonetwork.example.com/csw");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "csw");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "csw",
      url: "https://geonetwork.example.com/csw",
      mode: "reference",
      enabled: true,
    }),
  );
});

test("garde le mode copie désactivé pour OGC API - Records", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "ogc-records");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(true);
});

test("envoie le type CKAN en mode copie", async () => {
  let body: unknown = null;
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
    http.post("https://core.test/harvest/sources", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        {
          id: "s1",
          type: "ckan",
          url: "https://demo.data.gouv.fr",
          mode: "copy",
          enabled: true,
          intervalMinutes: null,
          lastRunAt: null,
          lastStatus: null,
          lastError: null,
        },
        { status: 201 },
      );
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.type(await screen.findByLabelText("URL"), "https://demo.data.gouv.fr");
  await userEvent.selectOptions(screen.getByLabelText("Type"), "ckan");
  await userEvent.selectOptions(screen.getByLabelText("Mode"), "copy");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(body).toEqual({
      type: "ckan",
      url: "https://demo.data.gouv.fr",
      mode: "copy",
      enabled: true,
    }),
  );
});

test("garde le mode copie disponible pour CKAN", async () => {
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Ajouter une source" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "ckan");
  const copyOption = screen.getByRole("option", { name: "Copie" }) as HTMLOptionElement;
  expect(copyOption.disabled).toBe(false);
});

test("sous viewport étroit, affiche trois onglets Catalogue/Moissonnage/Détail avec Moissonnage actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(
    http.get("https://core.test/harvest/sources", () => HttpResponse.json({ sources: [] })),
  );
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Moissonnage", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Moissonnage");
});
