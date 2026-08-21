// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { ItemClient, ReportSchedulePayload } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
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

test("persisted mode: affiche le panneau d'historique", async () => {
  const payload: ReportSchedulePayload = {
    bookmarkItemId: "bm-1",
    refreshPolicy: { enabled: true, cron: "0 8 * * MON" },
    channels: [{ kind: "webhook", url: "" }],
  };
  renderPage("r-1", {
    getReportScheduleConfig: () => Promise.resolve(payload),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});

test("unsaved mode: no history panel before the first save (no report id yet)", async () => {
  renderPage(null);
  await waitFor(() =>
    expect(screen.getByRole("heading", { name: "Programmer un rapport" })).toBeInTheDocument(),
  );
  expect(screen.queryByText("Historique")).not.toBeInTheDocument();
});
