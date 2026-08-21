// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { PublicItemPage } from "./PublicItemPage";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: false,
  username: null,
  error: null,
  getAccessToken: () => undefined,
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

function renderPage(client: Partial<ItemClient>, pk = "8") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/public/items/${pk}`]}>
          <PublicItemPage pk={pk} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [
      { id: "t1", widget: "text", x: 0, y: 0, w: 4, h: 1, props: { text: "Detail de l'article" } },
    ],
  },
};

test("200: renders the published item's runtime layout via AppRenderer", async () => {
  renderPage({ getPublicAppConfig: vi.fn().mockResolvedValue(config) });
  expect(await screen.findByText("Detail de l'article")).toBeInTheDocument();
  expect(screen.queryByText(/introuvable/i)).not.toBeInTheDocument();
});

test("404: shows a not-found message without leaking whether the item exists", async () => {
  renderPage({ getPublicAppConfig: vi.fn().mockRejectedValue(new Error("404")) }, "does-not-exist");
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/does-not-exist/i);
});
