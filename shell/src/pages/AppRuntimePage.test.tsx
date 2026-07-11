import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRuntimePage } from "./AppRuntimePage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false, isAuthenticated: true, username: "tanguy",
  error: null, getAccessToken: () => "t", signIn: vi.fn(), signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

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

const okItem: Item = {
  pk: "9", resourceType: "app", title: "App", abstract: "", owner: "alice",
  thumbnailUrl: null, date: "", configId: null, isPublished: true,
};

test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(config) });
  await userEvent.click(await screen.findByRole("button", { name: "Détails" }));
  expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/a%2Fb");
});

test("shows an access-denied message and never fetches the config when getItem fails", async () => {
  const getAppConfig = vi.fn().mockResolvedValue(config);
  renderRuntime({ getItem: vi.fn().mockRejectedValue(new Error("403")), getAppConfig });
  expect(await screen.findByRole("alert")).toHaveTextContent(/accès/i);
  expect(getAppConfig).not.toHaveBeenCalled();
});

test("proceeds to fetch and render the config once getItem succeeds", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(config) });
  expect(await screen.findByRole("button", { name: "Accueil" })).toBeInTheDocument();
});
