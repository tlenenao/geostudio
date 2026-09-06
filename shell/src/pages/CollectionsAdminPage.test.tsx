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
import { CollectionsAdminPage } from "./CollectionsAdminPage";

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

type CollectionAdminFixture = {
  id: string;
  title: string;
  description: string;
  tableName: string;
  isPublic: boolean;
  editable: boolean;
  geometryType: string | null;
  srid: number | null;
  pkColumn: string;
  permissions: { read: boolean; write: boolean; delete: boolean; share: boolean };
  featureCount: number | null;
  owner: string | null;
  attachmentFields: { key: string; label: string }[];
};

const INCIDENTS: CollectionAdminFixture = {
  id: "incidents",
  title: "Incidents",
  description: "",
  tableName: "incidents",
  isPublic: false,
  editable: true,
  geometryType: "Point",
  srid: 4326,
  pkColumn: "id",
  permissions: { read: true, write: true, delete: false, share: true },
  featureCount: 3,
  owner: "admin",
  attachmentFields: [],
};

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <CollectionsAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("lists collections and registers a new one via the panel", async () => {
  let posted: unknown;
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
    http.post("https://core.test/v1/collections", async ({ request }) => {
      posted = await request.json();
      return HttpResponse.json({ ...INCIDENTS, id: "points_interet", title: "points_interet" });
    }),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  expect(screen.getByText("admin")).toBeInTheDocument(); // owner column

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  // No title typed here — isPublic is still always sent (a real `false`,
  // never dropped by JSON.stringify), only the untouched title/description
  // fields drop out (empty string → undefined via `.trim() || undefined`).
  await waitFor(() => expect(posted).toEqual({ tableName: "points_interet", isPublic: false }));
});

test("shows an empty-state message when there are no candidate tables", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await waitFor(() => expect(screen.getByText(/Aucune table à enregistrer/)).toBeInTheDocument());
});

test("disables a non-registrable candidate and shows its reason", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          { tableName: "widgets", registrable: false, reason: "table has no primary key" },
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await screen.findByLabelText("Table");
  const widgetsOption = screen.getByRole("option", { name: /widgets.*table has no primary key/ });
  expect(widgetsOption).toBeDisabled();
  const poiOption = screen.getByRole("option", { name: "points_interet" });
  expect(poiOption).not.toBeDisabled();
});

test("disables the register submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () => HttpResponse.json({ collections: [] })),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({
        candidates: [
          {
            tableName: "points_interet",
            registrable: true,
            geometryType: "Point",
            srid: 4326,
            columnCount: 3,
          },
        ],
      }),
    ),
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Enregistrer une table" }));
  await userEvent.selectOptions(await screen.findByLabelText("Table"), "points_interet");
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("edits a collection via the row action", async () => {
  let patched: unknown;
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.patch("https://core.test/v1/collections/incidents", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({ ...INCIDENTS, title: "Incidents (v2)" });
    }),
  );
  render(<Harness />);
  const editButton = await screen.findByRole("button", { name: "Éditer" });
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, false);
  await userEvent.click(editButton);
  const titleInput = await screen.findByLabelText("Titre");
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, true);
  await userEvent.clear(titleInput);
  await userEvent.type(titleInput, "Incidents (v2)");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(patched).toMatchObject({ title: "Incidents (v2)" }));
});

test("aria-expanded est câblé par ligne, pas partagé entre toutes les lignes (revue finale SP-43, Important I2)", async () => {
  // Fixture à 2 collections : le défaut trouvé en revue finale (aria-expanded
  // posé une seule fois pour toute la page via {...editPanel.triggerProps}
  // dans .map()) était invisible avec une seule ligne — toutes les lignes
  // basculaient aria-expanded="true" en même temps.
  const other: CollectionAdminFixture = { ...INCIDENTS, id: "parcs", title: "Parcs" };
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS, other] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
  );
  render(<Harness />);
  const editButtons = await screen.findAllByRole("button", { name: "Éditer" });
  expect(editButtons).toHaveLength(2);
  editButtons.forEach((button) => expect(button).toHaveAttribute("aria-expanded", "false"));

  await userEvent.click(editButtons[0]);
  await screen.findByLabelText("Titre");

  expect(editButtons[0]).toHaveAttribute("aria-expanded", "true");
  expect(editButtons[1]).toHaveAttribute("aria-expanded", "false");
});

test("surfaces an alert when editing a collection fails", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.patch("https://core.test/v1/collections/incidents", () =>
      HttpResponse.json({}, { status: 500 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  await screen.findByLabelText("Titre");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() =>
    expect(screen.getByRole("alert")).toHaveTextContent("Échec de la mise à jour."),
  );
});

test("disables the edit submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("deletes a collection after confirming", async () => {
  let deleteCalled = false;
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.delete("https://core.test/v1/collections/incidents", () => {
      deleteCalled = true;
      return new HttpResponse(null, { status: 204 });
    }),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(deleteCalled).toBe(true));
});

test("supprimer la ligne en cours d'édition ferme le panneau Éditer (croisement editing/deleting)", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.delete(
      "https://core.test/v1/collections/incidents",
      () => new HttpResponse(null, { status: 204 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Éditer" }));
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));

  await waitFor(() => expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument());
});

test("supprimer la ligne en cours de partage ferme le panneau Partager (croisement sharing/deleting)", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/v1/groups", () => HttpResponse.json([])),
    http.get("https://core.test/v1/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.delete(
      "https://core.test/v1/collections/incidents",
      () => new HttpResponse(null, { status: 204 }),
    ),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await screen.findByText("Partager la collection");

  await userEvent.click(screen.getByRole("button", { name: "Supprimer" }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));

  await waitFor(() => expect(screen.queryByText("Partager la collection")).not.toBeInTheDocument());
});

test("shares a collection via the row action", async () => {
  let putBody: unknown;
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/v1/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/v1/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/v1/collections/incidents/sharing", async ({ request }) => {
      putBody = await request.json();
      return HttpResponse.json({ public: true, groups: [] });
    }),
  );
  render(<Harness />);
  const shareButton = await screen.findByRole("button", { name: "Partager" });
  expectAriaWired(shareButton, shareButton.getAttribute("aria-controls")!, false);
  await userEvent.click(shareButton);
  await userEvent.click(await screen.findByLabelText("Public"));
  expectAriaWired(shareButton, shareButton.getAttribute("aria-controls")!, true);
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(putBody).toEqual({ public: true, groups: [] }));
});

test("disables the share submit button when the instance is in read-only demo mode", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/v1/groups", () =>
      HttpResponse.json([{ id: "g1", name: "Équipe terrain" }]),
    ),
    http.get("https://core.test/v1/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
  );
  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: "Partager" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Enregistrer" })).toBeDisabled());
});

test("switching from edit to share on a different row closes the edit panel (exclusivité mutuelle)", async () => {
  const other: CollectionAdminFixture = { ...INCIDENTS, id: "parcs", title: "Parcs" };
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS, other] }),
    ),
    http.get("https://core.test/v1/collections/candidates", () =>
      HttpResponse.json({ candidates: [] }),
    ),
    http.get("https://core.test/v1/groups", () => HttpResponse.json([])),
    http.get("https://core.test/v1/collections/parcs/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.get("https://core.test/v1/collections/incidents/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
  );
  render(<Harness />);
  const editButtons = await screen.findAllByRole("button", { name: "Éditer" });
  const shareButtons = screen.getAllByRole("button", { name: "Partager" });
  const registerButton = screen.getByRole("button", { name: "Enregistrer une table" });

  // edit -> share (sens déjà couvert avant ce correctif) : Éditer puis
  // Partager sur une autre ligne ferme le panneau Éditer (setEditing(null)
  // dans le gestionnaire Partager).
  await userEvent.click(editButtons[0]);
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
  await userEvent.click(shareButtons[1]);
  await screen.findByText("Partager la collection");
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();

  // share -> edit (sens inverse) : ferme le panneau Partager
  // (setSharing(null) dans le gestionnaire Éditer).
  await userEvent.click(editButtons[0]);
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
  expect(screen.queryByText("Partager la collection")).not.toBeInTheDocument();

  // edit -> "Enregistrer une table" : ferme le panneau Éditer
  // (setEditing(null) dans le gestionnaire Enregistrer une table).
  await userEvent.click(registerButton);
  await screen.findByRole("heading", { name: "Enregistrer une table" });
  expect(screen.queryByLabelText("Titre")).not.toBeInTheDocument();

  // "Enregistrer une table" -> share : ferme le panneau Enregistrer
  // (setRegistering(false) dans le gestionnaire Partager).
  await userEvent.click(shareButtons[0]);
  await screen.findByText("Partager la collection");
  expect(screen.queryByRole("heading", { name: "Enregistrer une table" })).not.toBeInTheDocument();

  // share -> "Enregistrer une table" : ferme le panneau Partager
  // (setSharing(null) dans le gestionnaire Enregistrer une table).
  await userEvent.click(registerButton);
  await screen.findByRole("heading", { name: "Enregistrer une table" });
  expect(screen.queryByText("Partager la collection")).not.toBeInTheDocument();

  // "Enregistrer une table" -> edit : ferme le panneau Enregistrer
  // (setRegistering(false) dans le gestionnaire Éditer).
  await userEvent.click(editButtons[0]);
  expect(await screen.findByLabelText("Titre")).toBeInTheDocument();
  expect(screen.queryByRole("heading", { name: "Enregistrer une table" })).not.toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Collections/Détail avec Collections actif par défaut", async () => {
  stubMatchMedia(true);
  server.use(
    http.get("https://core.test/v1/collections", () => HttpResponse.json({ collections: [] })),
  );
  render(<Harness />);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Collections", "Détail"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Collections");
});

test("SP-42/F-securite-autorisation-06 : verrouille Éditer/Partager quand permissions.write/share sont faux", async () => {
  const RESTRICTED = {
    ...INCIDENTS,
    id: "restricted",
    title: "Restreinte",
    permissions: { read: true, write: false, delete: false, share: false },
  };
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [RESTRICTED] }),
    ),
  );
  render(<Harness />);
  const editButton = await screen.findByRole("button", { name: "Éditer" });
  const shareButton = screen.getByRole("button", { name: "Partager" });
  expect(editButton).toBeDisabled();
  expect(shareButton).toBeDisabled();
  expect(
    screen.getByText("Modification réservée aux éditeurs de cet élément."),
  ).toBeInTheDocument();
  expect(screen.getByText("Partage réservé au propriétaire et aux éditeurs.")).toBeInTheDocument();
  // Supprimer n'est pas concerné par cette trouvaille (le cœur ne gate pas
  // la suppression sur write/share) : reste actionnable.
  expect(screen.getByRole("button", { name: "Supprimer" })).not.toBeDisabled();
});

test("GAP-40 : un champ de recherche relaie q à listCollections", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/v1/collections", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ collections: [INCIDENTS] });
    }),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  await userEvent.type(
    screen.getByRole("searchbox", { name: /rechercher une collection/i }),
    "inci",
  );
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("q")).toBe("inci"));
});

// GET /collections pagine déjà côté cœur (limit/offset, SP-50) mais aucun
// consommateur shell n'exploitait ces paramètres — cette page tronquait
// silencieusement toute liste au-delà de la limite par défaut du cœur (100)
// sans que rien ne le signale à l'écran.
test("un bouton « Charger plus » apparaît quand la page est pleine et relaie une limite agrandie", async () => {
  const many = Array.from({ length: 100 }, (_, i) => ({
    ...INCIDENTS,
    id: `c${i}`,
    title: `Collection ${i}`,
  }));
  let lastUrl = "";
  server.use(
    http.get("https://core.test/v1/collections", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({ collections: many });
    }),
  );
  render(<Harness />);
  await screen.findByText("Collection 0");
  expect(new URL(lastUrl).searchParams.get("limit")).toBe("100");
  const loadMore = await screen.findByRole("button", { name: "Charger plus" });
  await userEvent.click(loadMore);
  await waitFor(() => expect(new URL(lastUrl).searchParams.get("limit")).toBe("200"));
});

test("le bouton « Charger plus » n'apparaît pas quand la page renvoyée est incomplète", async () => {
  server.use(
    http.get("https://core.test/v1/collections", () =>
      HttpResponse.json({ collections: [INCIDENTS] }),
    ),
  );
  render(<Harness />);
  await screen.findByText("Incidents");
  expect(screen.queryByRole("button", { name: "Charger plus" })).not.toBeInTheDocument();
});
