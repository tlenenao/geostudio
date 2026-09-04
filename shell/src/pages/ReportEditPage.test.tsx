// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { Item, ItemClient, ReportSchedulePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { ReportEditPage } from "./ReportEditPage";

// ReportEditPage calls useAuth() for `username` on create — same mock as
// PipelineBuilderPage.test.tsx, needed because the real hook calls
// react-oidc-context's useAuth(), which throws without an AuthProvider.
vi.mock("../auth/useAuth", () => ({
  useAuth: () => ({
    isLoading: false,
    isAuthenticated: true,
    username: "alice",
    getAccessToken: () => "t",
    signIn: vi.fn(),
    signOut: vi.fn(),
    error: null,
  }),
}));

// jsdom n'implémente pas window.matchMedia (piège n°10) ; TriptychLayout
// l'appelle via useNarrowViewport. ReportEditPage ne rendait pas
// TriptychLayout avant ce plan, donc ce stub est nouveau dans ce fichier —
// stub local, jamais dans shell/src/test/setup.ts. matches: false => le
// layout "large" (3 volets simultanés), pas les onglets — la valeur par
// défaut de tous les tests de ce fichier qui n'affirment pas sur la
// largeur. vi.unstubAllGlobals() en afterEach dès l'introduction du stub —
// contrairement à DatasetEditPage.test.tsx/AppBuilderPage.test.tsx, qui ne
// l'ont pas — dette non répétée ici.
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

beforeEach(() => {
  stubMatchMedia(false);
});
afterEach(() => vi.unstubAllGlobals());

const item: Item = {
  pk: "r-1",
  resourceType: "report",
  title: "Rapport planifié",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-08-31",
  configId: "cfg-r1",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
};

function renderPage(pk: string | null, overrides: Partial<ItemClient> = {}) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = {
    getReportRuns: vi.fn().mockResolvedValue([]),
    ...overrides,
  };
  render(
    <MemoryRouter>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <ReportEditPage pk={pk} initialBookmarkItemId="bm-1" />
        </ItemClientProvider>
      </QueryClientProvider>
    </MemoryRouter>,
  );
  return { client };
}

test("persisted mode: affiche le panneau d'historique et la fiche Catalogue", async () => {
  const payload: ReportSchedulePayload = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
  renderPage("r-1", {
    getItem: vi.fn().mockResolvedValue(item),
    getReportScheduleConfig: () => Promise.resolve(payload),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
  expect(await screen.findByText("Rapport")).toBeInTheDocument();
  expect(screen.getByText("2026-08-31")).toBeInTheDocument();
});

test("unsaved mode: no history panel before the first save (no report id yet)", async () => {
  renderPage(null);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  expect(screen.queryByText("Historique")).not.toBeInTheDocument();
});

test("unsaved mode: le volet Catalogue ne montre aucune fiche d'item avant le premier Enregistrer", async () => {
  renderPage(null);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  expect(screen.getByRole("link", { name: "← Retour au catalogue" })).toBeInTheDocument();
  expect(screen.queryByText("Type")).not.toBeInTheDocument();
});

test("sous viewport étroit, affiche trois onglets Catalogue/Rapport/Réglages avec Rapport actif par défaut", async () => {
  stubMatchMedia(true);
  renderPage(null);
  const tabs = await screen.findAllByRole("tab");
  expect(tabs.map((t) => t.textContent)).toEqual(["Catalogue", "Rapport", "Réglages"]);
  const activeTab = tabs.find((t) => t.getAttribute("aria-selected") === "true");
  expect(activeTab).toHaveTextContent("Rapport");
});
