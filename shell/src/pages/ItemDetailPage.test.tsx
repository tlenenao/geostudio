import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import type { ReactNode } from "react";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ItemDetailPage } from "./ItemDetailPage";

function wrapper({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "test-token",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

test("shows the item detail", async () => {
  render(<ItemDetailPage pk="7" />, { wrapper });
  expect(await screen.findByRole("heading", { name: "Item 7" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /éditeur/i })).toBeDisabled();
});

test("shows an error for a missing item", async () => {
  render(<ItemDetailPage pk="404" />, { wrapper });
  expect(await screen.findByRole("alert")).toBeInTheDocument();
});
