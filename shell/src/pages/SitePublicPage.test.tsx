// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { SitePublicPage } from "./SitePublicPage";
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

function renderSite(client: Partial<ItemClient>, slug = "mon-portail") {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={[`/sites/${slug}`]}>
          <SitePublicPage slug={slug} />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

const siteItem: Item = {
  pk: "42",
  resourceType: "site",
  title: "Mon Portail",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: "cfg-1",
  isPublished: true,
  slug: "mon-portail",
};

const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [
      {
        id: "t1",
        widget: "text",
        x: 0,
        y: 0,
        w: 4,
        h: 1,
        props: { text: "Bienvenue sur le portail" },
      },
    ],
  },
};

test("200: renders the published site's runtime layout via AppRenderer", async () => {
  renderSite({
    getItemBySlug: vi.fn().mockResolvedValue(siteItem),
    getPublicAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(await screen.findByText("Bienvenue sur le portail")).toBeInTheDocument();
  expect(screen.queryByText(/introuvable/i)).not.toBeInTheDocument();
});

test("404: shows a not-found message without leaking whether the slug exists, and never fetches the config", async () => {
  const getPublicAppConfig = vi.fn().mockResolvedValue(config);
  renderSite(
    {
      getItemBySlug: vi.fn().mockRejectedValue(new Error("404")),
      getPublicAppConfig,
    },
    "nexiste-pas",
  );
  expect(await screen.findByRole("alert")).toHaveTextContent(/introuvable/i);
  expect(screen.getByRole("alert")).not.toHaveTextContent(/nexiste-pas/i);
  expect(getPublicAppConfig).not.toHaveBeenCalled();
});
