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
import { RolesAdminPage } from "./RolesAdminPage";

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

// Checkbox (Radix) appelle ResizeObserver sans garde côté jsdom — stub local
// à ce fichier, même patron que KitGalleryPage.test.tsx/Slider.test.tsx.
// Ne pas ajouter à src/test/setup.ts (piège documenté).
class NoopResizeObserver {
  observe() {}
  unobserve() {}
  disconnect() {}
}

beforeEach(() => {
  stubMatchMedia(false);
  vi.stubGlobal("ResizeObserver", NoopResizeObserver);
});
afterEach(() => vi.unstubAllGlobals());

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <RolesAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

const CATALOG = [
  {
    privilege: "admin.harvest.manage",
    domain: "admin",
    labelKey: "roles.privilege.adminHarvestManage",
  },
  {
    privilege: "admin.collections.manage",
    domain: "admin",
    labelKey: "roles.privilege.adminCollectionsManage",
  },
];

test("admin crée un rôle sur mesure en cochant des privilèges", async () => {
  let created: Record<string, unknown> | null = null;
  server.use(
    http.get("https://core.test/v1/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/v1/roles", () =>
      HttpResponse.json(
        created
          ? [
              {
                id: "role-1",
                name: "Support",
                slug: "abc",
                isBuiltIn: false,
                privileges: created.privileges,
              },
            ]
          : [],
      ),
    ),
    http.post("https://core.test/v1/roles", async ({ request }) => {
      created = (await request.json()) as Record<string, unknown>;
      return HttpResponse.json(
        { id: "role-1", slug: "abc", isBuiltIn: false, ...created },
        { status: 201 },
      );
    }),
  );

  render(<Harness />);
  await userEvent.click(await screen.findByRole("button", { name: /ajouter un rôle/i }));
  await userEvent.type(screen.getByLabelText(/nom/i), "Support");
  await userEvent.click(screen.getByLabelText(/gérer le moissonnage/i));
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));

  await waitFor(() => expect(screen.getByText("Support")).toBeInTheDocument());
  expect(created).not.toBeNull();
  expect(created!.privileges).toEqual(["admin.harvest.manage"]);
});

test("cliquer Éditer sur un rôle sur mesure câble aria-expanded/aria-controls", async () => {
  server.use(
    http.get("https://core.test/v1/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/v1/roles", () =>
      HttpResponse.json([
        {
          id: "role-1",
          name: "Support",
          slug: "abc",
          isBuiltIn: false,
          privileges: ["admin.harvest.manage"],
        },
      ]),
    ),
  );

  render(<Harness />);
  const editButton = await screen.findByRole("button", { name: /éditer/i });
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, false);
  await userEvent.click(editButton);
  expect(await screen.findByLabelText(/nom/i)).toBeInTheDocument();
  expectAriaWired(editButton, editButton.getAttribute("aria-controls")!, true);
});

test("aria-expanded est câblé par ligne, pas partagé entre toutes les lignes (revue finale SP-43, Important I2)", async () => {
  // Fixture à 2 rôles sur mesure : le défaut trouvé en revue finale
  // (aria-expanded posé une seule fois pour toute la page via
  // {...editPanel.triggerProps} dans .map()) était invisible avec un seul
  // rôle — tous les boutons Éditer basculaient aria-expanded="true" en
  // même temps.
  server.use(
    http.get("https://core.test/v1/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/v1/roles", () =>
      HttpResponse.json([
        { id: "role-1", name: "Support", slug: "support", isBuiltIn: false, privileges: [] },
        { id: "role-2", name: "Terrain", slug: "terrain", isBuiltIn: false, privileges: [] },
      ]),
    ),
  );

  render(<Harness />);
  const editButtons = await screen.findAllByRole("button", { name: /éditer/i });
  expect(editButtons).toHaveLength(2);
  editButtons.forEach((button) => expect(button).toHaveAttribute("aria-expanded", "false"));

  await userEvent.click(editButtons[0]);
  await screen.findByLabelText(/nom/i);

  expect(editButtons[0]).toHaveAttribute("aria-expanded", "true");
  expect(editButtons[1]).toHaveAttribute("aria-expanded", "false");
});

test("un rôle prédéfini ne propose ni éditer ni supprimer", async () => {
  server.use(
    http.get("https://core.test/v1/roles/catalog", () => HttpResponse.json(CATALOG)),
    http.get("https://core.test/v1/roles", () =>
      HttpResponse.json([
        {
          id: "role-admin",
          name: "Administrateur",
          slug: "admin",
          isBuiltIn: true,
          privileges: [],
        },
      ]),
    ),
  );

  render(<Harness />);
  const row = await screen.findByText("Administrateur");
  const cell = row.closest("tr") as HTMLElement;
  expect(within(cell).queryByRole("button", { name: /éditer/i })).not.toBeInTheDocument();
  expect(within(cell).queryByRole("button", { name: /supprimer/i })).not.toBeInTheDocument();
});
