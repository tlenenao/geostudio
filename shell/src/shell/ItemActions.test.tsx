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
  await waitFor(() => expect(screen.queryByRole("button", { name: "Publier" })).not.toBeInTheDocument());
});


// Revue finale SP-17b (I3) : la création d'un ReportSchedule est refusée en
// 403 par le cœur quand la capacité export est coupée — l'entrée du menu suit
// la même garde que l'option « Pipeline » de NewItemButton sur etlEnabled.
function renderBookmarkActions(exportEnabled: boolean) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = {
    getInstanceInfo: vi.fn().mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled }),
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
  await waitFor(() => expect(
    screen.getByRole("button", { name: "Programmer un rapport" }),
  ).toBeInTheDocument());
});

test("masque « Programmer un rapport » quand la capacité export est coupée", async () => {
  renderBookmarkActions(false);
  await userEvent.click(screen.getByRole("button", { name: /actions/i }));
  await waitFor(() => expect(screen.getByRole("button", { name: /modifier/i })).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Programmer un rapport" })).not.toBeInTheDocument();
});
