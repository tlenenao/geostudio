// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AdminInfrastructurePage } from "./AdminInfrastructurePage";

function stubMatchMedia(matches: boolean) {
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
}

beforeEach(() => stubMatchMedia(false));
afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

function Harness() {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <MemoryRouter>
      <QueryClientProvider client={queryClient}>
        <ItemClientProvider client={client}>
          <AdminInfrastructurePage />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>
  );
}

test("affiche les trois boutons protégés et le lien MinIO quand la capacité est active", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Martin" });
  expect(screen.getByRole("button", { name: "Titiler" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Grafana" })).toBeInTheDocument();
  const minioLink = screen.getByRole("link", { name: /MinIO/ });
  expect(minioLink).toHaveAttribute("href", expect.stringContaining(":9001"));
});

test("masque les trois boutons protégés quand la capacité est désactivée, garde le lien MinIO", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ adminToolsEnabled: false }),
    ),
  );
  render(<Harness />);
  await screen.findByRole("link", { name: /MinIO/ });
  expect(screen.queryByRole("button", { name: "Martin" })).not.toBeInTheDocument();
});

test("cliquer sur Martin appelle launch et ouvre l'URL retournée dans un nouvel onglet", async () => {
  const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    http.post("https://core.test/v1/admin-tools/launch/martin", () =>
      HttpResponse.json({ url: "https://core.test/admin-tools/session/martin?_at=abc" }),
    ),
  );
  render(<Harness />);
  const button = await screen.findByRole("button", { name: "Martin" });
  await userEvent.click(button);
  await waitFor(() =>
    expect(openSpy).toHaveBeenCalledWith(
      "https://core.test/admin-tools/session/martin?_at=abc",
      "_blank",
      "noopener",
    ),
  );
});
