// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { MemoryRouter } from "react-router-dom";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { Item } from "../api/types";
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
