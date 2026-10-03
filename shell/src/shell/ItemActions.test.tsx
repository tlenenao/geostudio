// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { MemoryRouter, Route, Routes, useSearchParams } from "react-router-dom";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item, ItemClient } from "../api/types";
import { ItemActions } from "./ItemActions";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { server } from "../test/msw/server";

// Radix DropdownMenu sous jsdom : repositionnement lent (cf. ui/kit/Menu.test.tsx).
vi.setConfig({ testTimeout: 45000 });

const item: Item = {
  pk: "7",
  resourceType: "app",
  title: "Old",
  abstract: "A",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
  isPublished: false,
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>{children}</ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

// Alias pour l'option `wrapper` de `render` (RTL) — même composant que
// `Harness`, pas un second wrapper.
const wrapper = Harness;

function ShowSearch() {
  const [params] = useSearchParams();
  return <p>Fiche ouverte : {params.toString()}</p>;
}

function HarnessWithRouter({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <Routes>
            <Route path="/" element={children} />
            <Route path="/items/:pk" element={<ShowSearch />} />
          </Routes>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("« Modifier » navigue vers la fiche avec ?panel=edit", async () => {
  render(<ItemActions item={item} />, { wrapper: HarnessWithRouter });
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("menuitem", { name: /modifier/i }));
  expect(await screen.findByText(/panel=edit/)).toBeInTheDocument();
});

test("« Partager » navigue vers la fiche avec ?panel=share", async () => {
  render(<ItemActions item={item} />, { wrapper: HarnessWithRouter });
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("menuitem", { name: /partager/i }));
  expect(await screen.findByText(/panel=share/)).toBeInTheDocument();
});

test("deletes an item after confirmation and calls onDeleted", async () => {
  const onDeleted = vi.fn();
  render(
    <Harness>
      <ItemActions item={item} onDeleted={onDeleted} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("menuitem", { name: /supprimer/i }));
  const dialog = screen.getByRole("alertdialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(onDeleted).toHaveBeenCalled());
});

test("toggles publication from the menu", async () => {
  // REV-082 : le test d'origine n'observait que la fermeture du menu — un
  // composant qui enverrait la mauvaise valeur (ou aucune) au PATCH aurait
  // fait passer ce test tel quel. Un handler MSW local capture le corps
  // réellement envoyé et l'asserte contre {isPublished: true} (item.isPublished
  // vaut false au départ, ci-dessus).
  let capturedBody: unknown;
  server.use(
    http.patch("https://core.test/v1/items/:pk", async ({ request }) => {
      capturedBody = await request.json();
      return HttpResponse.json({ ...item, isPublished: true });
    }),
  );
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  const publish = screen.getByRole("menuitem", { name: "Publier" });
  await userEvent.click(publish);
  // j03-012 : une app passe par le dialogue de publication (aucune collection
  // lue ici : un seul bouton de confirmation).
  const dialog = await screen.findByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Publier" }));
  await waitFor(() => expect(capturedBody).toEqual({ isPublished: true }));
});

test("publier une app qui lit une collection privée propose de la publier aussi", async () => {
  const puts: unknown[] = [];
  let patched: unknown;
  server.use(
    http.get("https://core.test/v1/configs/by-item/7", () =>
      HttpResponse.json({
        version: 1,
        config: {
          kind: "app",
          layout: { type: "grid", items: [] },
          dataSources: [{ id: "ds", type: "features", layer: "coll-1" }],
        },
      }),
    ),
    http.get("https://core.test/v1/collections/coll-1/sharing", () =>
      HttpResponse.json({ public: false, groups: [] }),
    ),
    http.put("https://core.test/v1/collections/coll-1/sharing", async ({ request }) => {
      puts.push(await request.json());
      return new HttpResponse(null, { status: 204 });
    }),
    http.patch("https://core.test/v1/items/:pk", async ({ request }) => {
      patched = await request.json();
      return HttpResponse.json({ ...item, isPublished: true });
    }),
  );
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Publier" }));
  const dialog = await screen.findByRole("dialog");
  expect(await within(dialog).findByText("coll-1")).toBeInTheDocument();
  await userEvent.click(
    within(dialog).getByRole("button", { name: "Publier aussi les collections" }),
  );
  await waitFor(() => expect(patched).toEqual({ isPublished: true }));
  expect(puts).toEqual([{ public: true, groups: [] }]);
});

// Revue finale SP-17b (I3) : la création d'un ReportSchedule est refusée en
// 403 par le cœur quand la capacité export est coupée — l'entrée du menu suit
// la même garde que l'option « Pipeline » de NewItemButton sur etlEnabled.
function renderBookmarkActions(exportEnabled: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = {
    getInstanceInfo: vi
      .fn()
      .mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled }),
  } as unknown as ItemClient;
  render(
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <ItemActions item={{ ...item, resourceType: "bookmark" }} />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
}

test("propose « Programmer un rapport » sur un signet quand la capacité export est active", async () => {
  renderBookmarkActions(true);
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await waitFor(() =>
    expect(screen.getByRole("menuitem", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
});

test("masque « Programmer un rapport » quand la capacité export est coupée", async () => {
  renderBookmarkActions(false);
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await waitFor(() =>
    expect(screen.getByRole("menuitem", { name: /modifier/i })).toBeInTheDocument(),
  );
  expect(screen.queryByRole("menuitem", { name: "Programmer un rapport" })).not.toBeInTheDocument();
});

const viewerItem: Item = {
  pk: "42",
  resourceType: "map",
  title: "Réseau d'eau potable",
  abstract: "",
  owner: "tanguy",
  thumbnailUrl: null,
  date: "2026-08-29T00:00:00Z",
  configId: null,
  isPublished: false,
  permissions: { read: true, write: false, delete: false, share: false },
  license: "",
  language: "fr",
};

const editorItem: Item = {
  ...viewerItem,
  pk: "43",
  permissions: { read: true, write: true, delete: false, share: false },
};

describe("ItemActions et les droits", () => {
  it("un lecteur ne voit ni Partager ni Supprimer", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: /^actions/i }));
    expect(screen.queryByRole("menuitem", { name: "Partager" })).not.toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("un lecteur voit Modifier, Publier et Miniature verrouillées en un seul message", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: /^actions/i }));
    expect(screen.getByRole("menuitem", { name: "Modifier" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: "Publier" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: "Miniature" })).toHaveAttribute(
      "aria-disabled",
      "true",
    );
    // Un seul message de raison pour les trois, pas un par action verrouillée
    // (SP-29a review finale — regroupement décidé pour SP-30a).
    expect(screen.getAllByText("Modification réservée aux éditeurs de cet élément.")).toHaveLength(
      1,
    );
  });

  it("un éditeur peut modifier et publier, mais pas supprimer ni partager", async () => {
    render(<ItemActions item={editorItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: /^actions/i }));
    expect(screen.getByRole("menuitem", { name: "Modifier" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.getByRole("menuitem", { name: "Publier" })).not.toHaveAttribute(
      "aria-disabled",
      "true",
    );
    expect(screen.queryByRole("menuitem", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("le propriétaire garde les cinq commandes", async () => {
    const owned: Item = {
      ...viewerItem,
      pk: "44",
      permissions: { read: true, write: true, delete: true, share: true },
    };
    render(<ItemActions item={owned} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: /^actions/i }));
    for (const name of ["Modifier", "Publier", "Miniature", "Partager", "Supprimer"]) {
      expect(screen.getByRole("menuitem", { name })).not.toHaveAttribute("aria-disabled", "true");
    }
  });
});

test("publier un item sans référence de données envoie le PATCH sans dialogue", async () => {
  let capturedBody: unknown;
  server.use(
    http.patch("https://core.test/v1/items/:pk", async ({ request }) => {
      capturedBody = await request.json();
      return HttpResponse.json({ ...item, resourceType: "dataset", isPublished: true });
    }),
  );
  render(
    <Harness>
      <ItemActions item={{ ...item, resourceType: "dataset" }} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("menuitem", { name: "Publier" }));
  await waitFor(() => expect(capturedBody).toEqual({ isPublished: true }));
  expect(screen.queryByRole("dialog")).toBeNull();
});

test("« Programmer un rapport » ouvre /reports/new quand l'export est actif", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: false, exportEnabled: true }),
    ),
  );
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <MemoryRouter initialEntries={["/"]}>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <Routes>
            <Route
              path="/"
              element={<ItemActions item={{ ...item, resourceType: "bookmark" }} />}
            />
            <Route path="/reports/new" element={<p>Nouveau rapport</p>} />
          </Routes>
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(await screen.findByRole("menuitem", { name: /programmer un rapport/i }));
  expect(await screen.findByText("Nouveau rapport")).toBeInTheDocument();
});

describe("ItemActions : accessibilité du menu (P33.04, P33.09, P33.10, P33.12)", () => {
  it("le déclencheur porte un nom propre à la carte, aria-haspopup=menu et aria-expanded", async () => {
    render(<ItemActions item={item} />, { wrapper });
    const trigger = screen.getByRole("button", { name: "Actions de Old" });
    expect(trigger).toHaveAttribute("aria-haspopup", "menu");
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    await userEvent.click(trigger);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    expect(await screen.findByRole("menu")).toBeInTheDocument();
  });

  it("Échap ferme le menu et rend le focus au déclencheur", async () => {
    render(<ItemActions item={item} />, { wrapper });
    const trigger = screen.getByRole("button", { name: "Actions de Old" });
    await userEvent.click(trigger);
    await screen.findByRole("menu");
    await userEvent.keyboard("{Escape}");
    await waitFor(() => expect(screen.queryByRole("menu")).not.toBeInTheDocument());
    expect(trigger).toHaveFocus();
  });

  it("annuler la confirmation de suppression rend le focus au déclencheur", async () => {
    render(<ItemActions item={item} />, { wrapper });
    const trigger = screen.getByRole("button", { name: "Actions de Old" });
    await userEvent.click(trigger);
    await userEvent.click(await screen.findByRole("menuitem", { name: "Supprimer" }));
    const dialog = await screen.findByRole("alertdialog");
    expect(dialog).toHaveAccessibleDescription(/irréversible/);
    await userEvent.click(within(dialog).getByRole("button", { name: "Annuler" }));
    await waitFor(() => expect(screen.queryByRole("alertdialog")).not.toBeInTheDocument());
    await waitFor(() => expect(trigger).toHaveFocus());
  });
});
