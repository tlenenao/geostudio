// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { HarvestSourcesAdminPage } from "./HarvestSourcesAdminPage";

// jsdom sans matchMedia (piège n°10) : stub local, retiré après chaque test.
beforeEach(() =>
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  ),
);
afterEach(() => vi.unstubAllGlobals());

// REV-323 : l'erreur de chargement de la LISTE des sources a un état d'erreur avec « Réessayer ».
test("échec du chargement des sources : message puis « Réessayer » relance la requête", async () => {
  let calls = 0;
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ readOnly: true })),
    http.get("https://core.test/v1/harvest/sources", () => {
      calls += 1;
      if (calls === 1) return new HttpResponse(null, { status: 500 });
      return HttpResponse.json({
        sources: [
          {
            id: "src-1",
            type: "stac",
            url: "https://stac.example.com/collections",
            mode: "reference",
            enabled: true,
            intervalMinutes: null,
            lastRunAt: null,
            lastStatus: "ok",
            lastError: null,
          },
        ],
      });
    }),
  );
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <MemoryRouter>
      <QueryClientProvider
        client={new QueryClient({ defaultOptions: { queries: { retry: false } } })}
      >
        <ItemClientProvider client={client}>
          <HarvestSourcesAdminPage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  await userEvent.click(await screen.findByRole("button", { name: "Réessayer" }));
  expect(await screen.findByText("https://stac.example.com/collections")).toBeInTheDocument();
});
