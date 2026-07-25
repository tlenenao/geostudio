// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigationType } from "react-router-dom";
import { expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRuntimePage } from "./AppRuntimePage";
import type { AuthState } from "../auth/useAuth";
import { EXTENT_DEBOUNCE_MS, useAnalyticsContext } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import { getWidget, registerWidget } from "../builder/registry";

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
  const navigationType = useNavigationType();
  return (
    <div>
      <p data-testid="loc">{location.pathname}</p>
      <p data-testid="search">{location.search}</p>
      <p data-testid="navtype">{navigationType}</p>
    </div>
  );
}

function renderRuntime(client: Partial<ItemClient>, initialEntries: string[] = ["/apps/9/page-1"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <AppRuntimePage pk="9" pageId="page-1" />
          <LocationDisplay />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

// __ctx_probe__ is registered once at module scope (registerWidget just warns
// on re-registration, but this avoids the noise across the two ctx tests below).
if (!getWidget("__ctx_probe__")) {
  registerWidget({
    type: "__ctx_probe__", label: "probe", defaultProps: {}, defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: () => {
      const ctx = useAnalyticsContext();
      return <p>probe-timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}</p>;
    },
  });
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

const probeConfig: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  interactions: "auto",
  layout: emptyLayout,
  pages: [
    { id: "page-1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
      { id: "p1", widget: "__ctx_probe__", x: 0, y: 0, w: 4, h: 2, props: {} },
    ] } },
  ],
};

test("hydrates the initial analytics context from the ctx URL param", async () => {
  const encoded = encodeAnalyticsContext({ timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {} });
  renderRuntime(
    { getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(probeConfig) },
    [`/apps/9/page-1?ctx=${encoded}`],
  );
  expect(await screen.findByText("probe-timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

const dateFilterConfig: AppConfig = {
  kind: "app", theme: {}, dataSources: [], messages: [],
  interactions: "auto",
  layout: emptyLayout,
  pages: [
    { id: "page-1", name: "Accueil", layout: { type: "grid", breakpoints: {}, items: [
      { id: "d1", widget: "dateRangeFilter", x: 0, y: 0, w: 4, h: 1, props: { label: "Période" } },
    ] } },
  ],
};

test("writes the analytics context back to the ctx URL param, debounced, with replace semantics", async () => {
  renderRuntime({ getItem: vi.fn().mockResolvedValue(okItem), getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig) });
  const fromInput = await screen.findByLabelText("Date de début");
  const toInput = await screen.findByLabelText("Date de fin");
  expect(screen.getByTestId("search")).toHaveTextContent("");

  // fireEvent (not userEvent) here: userEvent's internal async wait model hangs
  // indefinitely under Vitest fake timers in this environment (see
  // AnalyticsContext.test.tsx) — fireEvent + act() is the RTL-sanctioned way to
  // combine input changes with fake-timer advances.
  vi.useFakeTimers();
  try {
    fireEvent.change(fromInput, { target: { value: "2026-01-01" } });
    fireEvent.change(toInput, { target: { value: "2026-02-01" } });
    // Not written yet — still debouncing.
    expect(screen.getByTestId("search")).toHaveTextContent("");
    act(() => { vi.advanceTimersByTime(EXTENT_DEBOUNCE_MS); });

    const search = screen.getByTestId("search").textContent ?? "";
    const ctx = new URLSearchParams(search).get("ctx");
    expect(ctx).toBeTruthy();
    expect(decodeAnalyticsContext(ctx)).toEqual({
      timeRange: { from: "2026-01-01", to: "2026-02-01" }, extent: null, crossFilter: {},
    });
    // replace semantics: the location changed, but no new history entry was pushed.
    expect(screen.getByTestId("navtype")).toHaveTextContent("REPLACE");
  } finally {
    vi.useRealTimers();
  }
});
