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
import { AdminExtensionsPage } from "./AdminExtensionsPage";

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

function mockMe(privileges: string[]) {
  server.use(
    http.get("https://core.test/v1/me", () =>
      HttpResponse.json({
        id: "u1",
        username: "alice",
        firstName: "Alice",
        lastName: "Martin",
        role: { id: "role-1", name: "Administrateur", slug: "admin" },
        privileges,
      }),
    ),
  );
}

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminExtensionsPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("shows the shared LoadingState (role=status, spinner) while /v1/extensions is in flight", () => {
  server.use(http.get("https://core.test/v1/extensions", () => new Promise(() => {})));
  render(<Harness />);
  const status = screen.getByRole("status");
  expect(status).toHaveTextContent("Chargement…");
  expect(status.querySelector('[aria-hidden="true"]')).not.toBeNull();
});

test("lists extensions (including disabled) and toggles enabled via PATCH", async () => {
  let patchedBody: unknown;
  server.use(
    http.get("https://core.test/v1/extensions", ({ request }) => {
      expect(new URL(request.url).searchParams.get("all")).toBe("true");
      return HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      });
    }),
    http.patch("https://core.test/v1/extensions/acme.gauge", async ({ request }) => {
      patchedBody = await request.json();
      return HttpResponse.json({ id: "acme.gauge", enabled: true });
    }),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).not.toBeChecked();
  await userEvent.click(toggle);
  await waitFor(() => expect(patchedBody).toEqual({ enabled: true }));
});

test("surfaces an alert when the PATCH to toggle an extension fails", async () => {
  server.use(
    http.get("https://core.test/v1/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.patch("https://core.test/v1/extensions/acme.gauge", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  await userEvent.click(toggle);
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour de l'extension."),
  );
});

test("disables the enabled toggle when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/v1/extensions", () =>
      HttpResponse.json({
        extensions: [
          {
            id: "acme.gauge",
            tag: "gauge-extension-widget",
            label: "Jauge (extension)",
            moduleUrl: "https://example.com/gauge.js",
            props: [],
            events: [],
            actions: [],
            defaultSize: { w: 2, h: 2 },
            permissions: { collections: "all" },
            enabled: false,
          },
        ],
      }),
    ),
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  const toggle = await screen.findByRole("checkbox", { name: "Actif : Jauge (extension)" });
  expect(toggle).toBeDisabled();
});

test("le volet Catalogue propose un lien vers /admin/roles quand le privilège est détenu", async () => {
  mockMe(["admin.roles.manage"]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toHaveAttribute(
    "href",
    "/admin/roles",
  );
});

test("le volet Catalogue propose un lien vers /admin/users quand le privilège est détenu", async () => {
  mockMe(["admin.users.manage"]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toHaveAttribute(
    "href",
    "/admin/users",
  );
});

test("masque le lien vers /admin/infrastructure quand le privilège est absent", async () => {
  mockMe([]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.queryByRole("link", { name: "Outils d'infrastructure →" })).not.toBeInTheDocument();
});

test("masque le lien vers /admin/roles quand le privilège est absent", async () => {
  mockMe([]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.queryByRole("link", { name: "Rôles et privilèges →" })).not.toBeInTheDocument();
});

test("masque le lien vers /admin/users quand le privilège est absent", async () => {
  mockMe([]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.queryByRole("link", { name: "Utilisateurs →" })).not.toBeInTheDocument();
});

test("un profil qui détient plusieurs privilèges admin voit tous les liens correspondants", async () => {
  mockMe([
    "admin.roles.manage",
    "admin.users.manage",
    "admin.collections.manage",
    "admin.harvest.manage",
    "settings.instance.manage",
  ]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.getByRole("link", { name: "Outils d'infrastructure →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Rôles et privilèges →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Utilisateurs →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Collections →" })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toBeInTheDocument();
});

test("le volet Catalogue propose un lien vers /admin/collections quand le privilège est détenu", async () => {
  mockMe(["admin.collections.manage"]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.getByRole("link", { name: "Collections →" })).toHaveAttribute(
    "href",
    "/admin/collections",
  );
});

test("masque le lien vers /admin/collections quand le privilège est absent", async () => {
  mockMe([]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.queryByRole("link", { name: "Collections →" })).not.toBeInTheDocument();
});

test("le volet Catalogue propose un lien vers /admin/harvest quand le privilège est détenu", async () => {
  mockMe(["admin.harvest.manage"]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.getByRole("link", { name: "Moissonnage →" })).toHaveAttribute(
    "href",
    "/admin/harvest",
  );
});

test("masque le lien vers /admin/harvest quand le privilège est absent", async () => {
  mockMe([]);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  expect(screen.queryByRole("link", { name: "Moissonnage →" })).not.toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Extensions/Détail avec Extensions actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
  );
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Extensions", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Extensions");
});

test("le formulaire d'enregistrement poste sur /extensions (j08-009)", async () => {
  let posted: unknown;
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
    http.post("https://core.test/v1/extensions", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({ id: "acme.x" }, { status: 201 });
    }),
  );
  render(<Harness />);
  await screen.findByText("Aucune extension enregistrée.");
  await userEvent.type(screen.getByLabelText("Identifiant"), "acme.x");
  await userEvent.type(screen.getByLabelText("Balise"), "x-widget");
  await userEvent.type(screen.getByLabelText("Étiquette"), "X");
  await userEvent.type(screen.getByLabelText("URL du module (https)"), "https://e.com/x.js");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(posted).toEqual({
      id: "acme.x",
      tag: "x-widget",
      label: "X",
      moduleUrl: "https://e.com/x.js",
      defaultSize: { w: 2, h: 2 },
    }),
  );
});

test("supprimer une extension demande confirmation puis appelle DELETE (j08-009)", async () => {
  let deleted = false;
  server.use(
    http.get("https://core.test/v1/extensions", () =>
      HttpResponse.json({
        extensions: deleted
          ? []
          : [
              {
                id: "acme.gauge",
                tag: "gauge-extension-widget",
                label: "Jauge (extension)",
                moduleUrl: "https://example.com/gauge.js",
                props: [],
                defaultSize: { w: 2, h: 2 },
                enabled: true,
              },
            ],
      }),
    ),
    http.delete("https://core.test/v1/extensions/acme.gauge", () => {
      deleted = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(
    await screen.findByRole("button", { name: "Supprimer : Jauge (extension)" }),
  );
  expect(deleted).toBe(false);
  const dialog = await screen.findByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleted).toBe(true));
  expect(await screen.findByText("Aucune extension enregistrée.")).toBeInTheDocument();
});

// --- L10 (AUD-110) : manifeste complet en JSON, édition, badge d'intégrité ----------------------
const FULL_EXT = {
  id: "acme.gauge",
  tag: "gauge-extension-widget",
  label: "Jauge",
  moduleUrl: "https://example.com/gauge.js",
  props: [{ name: "initial", type: "number", label: "Valeur", default: 0 }],
  events: ["changed"],
  actions: ["reset"],
  defaultSize: { w: 2, h: 2 },
  permissions: { collections: "all" },
  sdkVersion: 1,
  integrity: "sha384-" + "A".repeat(64),
  connectHosts: ["https://api.example.org"],
  imgHosts: [],
  enabled: true,
};

test("affiche le badge d'intégrité épinglée ou absente", async () => {
  server.use(
    http.get("https://core.test/v1/extensions", () =>
      HttpResponse.json({
        extensions: [FULL_EXT, { ...FULL_EXT, id: "acme.bare", label: "Nue", integrity: null }],
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("Épinglée (SRI)")).toBeVisible();
  expect(screen.getByText("Sans intégrité")).toBeVisible();
});

test("importe un manifeste JSON complet par POST et affiche l'erreur 422 du cœur", async () => {
  const bodies: unknown[] = [];
  server.use(
    http.get("https://core.test/v1/extensions", () => HttpResponse.json({ extensions: [] })),
    http.post("https://core.test/v1/extensions", async ({ request }) => {
      const body = (await request.json()) as { sdkVersion?: number };
      bodies.push(body);
      if (body.sdkVersion === 2) {
        return HttpResponse.json(
          {
            type: "about:blank",
            title: "Unprocessable",
            status: 422,
            detail: "sdkVersion inconnu",
          },
          { status: 422, headers: { "content-type": "application/problem+json" } },
        );
      }
      return HttpResponse.json({}, { status: 201 });
    }),
  );
  render(<Harness />);
  const area = await screen.findByLabelText("Manifeste JSON");
  await userEvent.click(area);
  await userEvent.paste(JSON.stringify({ ...FULL_EXT, sdkVersion: 2 }));
  await userEvent.click(screen.getByRole("button", { name: "Importer le manifeste" }));
  expect(await screen.findByText(/sdkVersion inconnu/)).toBeVisible();

  await userEvent.clear(area);
  await userEvent.click(area);
  await userEvent.paste(JSON.stringify(FULL_EXT));
  await userEvent.click(screen.getByRole("button", { name: "Importer le manifeste" }));
  expect(await screen.findByText("Manifeste enregistré.")).toBeVisible();
  expect(bodies[1]).toMatchObject({ id: "acme.gauge", integrity: FULL_EXT.integrity });

  await userEvent.click(area);
  await userEvent.paste("{pas du json");
  await userEvent.click(screen.getByRole("button", { name: "Importer le manifeste" }));
  expect(await screen.findByText("Le manifeste n'est pas un JSON valide.")).toBeVisible();
});

test("édite une extension existante par PATCH (identifiant verrouillé)", async () => {
  let patched: unknown = null;
  server.use(
    http.get("https://core.test/v1/extensions", () =>
      HttpResponse.json({ extensions: [FULL_EXT] }),
    ),
    http.patch("https://core.test/v1/extensions/acme.gauge", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({});
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Modifier : Jauge" }));
  const area = (await screen.findByLabelText("Manifeste JSON")) as HTMLTextAreaElement;
  await waitFor(() => expect(area.value).toContain('"integrity"'));
  const edited = { ...JSON.parse(area.value), label: "Jauge v2" };
  await userEvent.clear(area);
  await userEvent.click(area);
  await userEvent.paste(JSON.stringify(edited));
  await userEvent.click(screen.getByRole("button", { name: "Mettre à jour" }));
  expect(await screen.findByText("Manifeste enregistré.")).toBeVisible();
  expect(patched).toMatchObject({ label: "Jauge v2", sdkVersion: 1 });
  expect(patched).not.toHaveProperty("id");
});
