import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi } from "vitest";
import type { ReactNode } from "react";
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
};

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
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
