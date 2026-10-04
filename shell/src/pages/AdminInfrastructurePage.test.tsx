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

const okProbe = { ok: true };
const statusBody = (minioConsolePublished: boolean) => ({
  checkedAt: "2026-10-02T10:00:00Z",
  minioConsolePublished,
  postgres: okProbe,
  s3: okProbe,
  cdc: { ok: true, slotActive: true },
  jobs: { ok: true, queues: [], stalled: 0 },
});
const minioPublished = (published: boolean) =>
  http.get("https://core.test/v1/instance/status", () => HttpResponse.json(statusBody(published)));

test("affiche les trois boutons protégés et le lien MinIO quand la capacité est active", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    minioPublished(true),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Martin" });
  await screen.findByRole("link", { name: /MinIO/ });
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
    minioPublished(true),
  );
  render(<Harness />);
  await screen.findByRole("link", { name: /MinIO/ });
  expect(screen.queryByRole("button", { name: "Martin" })).not.toBeInTheDocument();
});

test("affiche l'utilisation avec les plafonds configurés", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ adminToolsEnabled: false }),
    ),
    http.get("https://core.test/v1/admin/usage", () =>
      HttpResponse.json({
        itemCount: 12,
        collectionCount: 3,
        userCount: 5,
        storageBytes: 2_000_000,
        maxItems: 100,
        maxCollections: null,
        maxStorageBytes: null,
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("Éléments : 12 / 100")).toBeInTheDocument();
  expect(screen.getByText(/Collections : 3/)).toBeInTheDocument();
  expect(screen.getByText(/pas de limite configurée/)).toBeInTheDocument();
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

test("masque le lien MinIO quand le port n'est pas publié", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    minioPublished(false),
  );
  render(<Harness />);
  await screen.findByRole("button", { name: "Martin" });
  await screen.findByText(/PostgreSQL/);
  expect(screen.queryByRole("link", { name: /MinIO/ })).not.toBeInTheDocument();
});

test("le lien MinIO annonce l'ouverture dans un nouvel onglet", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () =>
      HttpResponse.json({ adminToolsEnabled: false }),
    ),
    minioPublished(true),
  );
  render(<Harness />);
  expect(await screen.findByRole("link", { name: /nouvel onglet/ })).toBeInTheDocument();
});

test("affiche l'état de l'instance (santé, file de jobs)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({})),
    http.get("https://core.test/v1/instance/status", () =>
      HttpResponse.json({
        checkedAt: "2026-10-02T10:00:00Z",
        minioConsolePublished: false,
        postgres: { ok: true },
        s3: { ok: false, error: "EndpointConnectionError" },
        cdc: { ok: true, slotActive: true },
        jobs: {
          ok: true,
          queues: [{ queue: "default", status: "todo", count: 4 }],
          stalled: 1,
        },
      }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText(/PostgreSQL : opérationnel/)).toBeInTheDocument();
  expect(screen.getByText(/S3 : en échec/)).toBeInTheDocument();
  expect(
    screen.getByText(/File de jobs : en échec \(4 en attente ou en cours, 1 bloqué/),
  ).toBeInTheDocument();
});

test("affiche « non configuré » quand le slot CDC est absent (REV-274c)", async () => {
  server.use(
    http.get("https://core.test/v1/instance", () => HttpResponse.json({ adminToolsEnabled: true })),
    http.get("https://core.test/v1/instance/status", () =>
      HttpResponse.json({ ...statusBody(false), cdc: { ok: true, configured: false } }),
    ),
  );
  render(<Harness />);
  expect(await screen.findByText("CDC : non configuré")).toBeInTheDocument();
});
