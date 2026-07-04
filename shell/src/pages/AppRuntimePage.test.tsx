import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRuntimePage } from "./AppRuntimePage";

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };
const config: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  layout: { type: "grid", breakpoints: {}, items: [
    { id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} },
  ] },
  pages: [
    { id: "page-1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
      { id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} },
    ] } },
    { id: "a/b", name: "Détails", layout: emptyLayout },
  ],
};

function LocationDisplay() {
  const location = useLocation();
  return <p data-testid="loc">{location.pathname}</p>;
}

function renderRuntime(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={["/apps/9/page-1"]}>
          <AppRuntimePage pk="9" pageId="page-1" />
          <LocationDisplay />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({ getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Détails" }));
  expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/a%2Fb");
});
