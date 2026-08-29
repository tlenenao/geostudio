// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item, ItemClient } from "../api/types";
import { ItemActions } from "./ItemActions";
import { OWNER_PERMISSIONS } from "../auth/permissions";

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

test("renames an item via the edit dialog", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /modifier/i }));
  const title = screen.getByLabelText("Titre");
  await userEvent.clear(title);
  await userEvent.type(title, "Renamed");
  await userEvent.click(screen.getByRole("button", { name: /enregistrer/i }));
  await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
});

test("opens the share dialog from the menu", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /partager/i }));
  expect(await screen.findByRole("dialog", { name: /partager/i })).toBeInTheDocument();
});

test("deletes an item after confirmation and calls onDeleted", async () => {
  const onDeleted = vi.fn();
  render(
    <Harness>
      <ItemActions item={item} onDeleted={onDeleted} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await userEvent.click(screen.getByRole("button", { name: /supprimer/i }));
  const dialog = screen.getByRole("dialog");
  await userEvent.click(within(dialog).getByRole("button", { name: "Supprimer" }));
  await waitFor(() => expect(onDeleted).toHaveBeenCalled());
});

test("toggles publication from the menu", async () => {
  render(
    <Harness>
      <ItemActions item={item} />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  const publish = screen.getByRole("button", { name: "Publier" });
  await userEvent.click(publish);
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Publier" })).not.toBeInTheDocument(),
  );
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
    expect(screen.getByRole("button", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
});

test("masque « Programmer un rapport » quand la capacité export est coupée", async () => {
  renderBookmarkActions(false);
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await waitFor(() =>
    expect(screen.getByRole("button", { name: /modifier/i })).toBeInTheDocument(),
  );
  expect(screen.queryByRole("button", { name: "Programmer un rapport" })).not.toBeInTheDocument();
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
};

const editorItem: Item = {
  ...viewerItem,
  pk: "43",
  permissions: { read: true, write: true, delete: false, share: false },
};

describe("ItemActions et les droits", () => {
  it("un lecteur ne voit ni Partager ni Supprimer", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.queryByRole("button", { name: "Partager" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("un lecteur voit Modifier verrouillée, avec sa raison", async () => {
    render(<ItemActions item={viewerItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    const edit = screen.getByRole("button", { name: "Modifier" });
    expect(edit).toBeDisabled();
    // Publier et Miniature sont aussi verrouillées par `write` pour ce même
    // item et affichent la même raison (`locked.needWrite`) : plusieurs
    // occurrences du texte sont donc attendues, `getAllByText` remplace le
    // `getByText` du brief (piège n°3 — texte littéral faux face au rendu réel).
    expect(
      screen.getAllByText("Modification réservée aux éditeurs de cet élément.")[0],
    ).toBeVisible();
  });

  it("un éditeur peut modifier et publier, mais pas supprimer ni partager", async () => {
    render(<ItemActions item={editorItem} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    expect(screen.getByRole("button", { name: "Modifier" })).toBeEnabled();
    expect(screen.getByRole("button", { name: "Publier" })).toBeEnabled();
    expect(screen.queryByRole("button", { name: "Supprimer" })).not.toBeInTheDocument();
  });

  it("le propriétaire garde les cinq commandes", async () => {
    const owned: Item = {
      ...viewerItem,
      pk: "44",
      permissions: { read: true, write: true, delete: true, share: true },
    };
    render(<ItemActions item={owned} />, { wrapper });
    await userEvent.click(screen.getByRole("button", { name: "Actions" }));
    for (const name of ["Modifier", "Publier", "Miniature", "Partager", "Supprimer"]) {
      expect(screen.getByRole("button", { name })).toBeEnabled();
    }
  });
});
