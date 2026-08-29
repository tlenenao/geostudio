// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, useLocation, useNavigationType } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import type { AppConfig, Item, ItemClient } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRuntimePage } from "./AppRuntimePage";
import type { AuthState } from "../auth/useAuth";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { EXTENT_DEBOUNCE_MS, useAnalyticsContext } from "../builder/AnalyticsContext";
import { decodeAnalyticsContext, encodeAnalyticsContext } from "../lib/analyticsContextUrl";
import { getWidget, registerWidget } from "../builder/registry";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "tanguy",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

afterEach(() => {
  delete document.body.dataset.exportReady;
});

const emptyLayout = { type: "grid" as const, breakpoints: {}, items: [] };
const config: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: {
    type: "grid",
    breakpoints: {},
    items: [{ id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} }],
  },
  pages: [
    {
      id: "page-1",
      name: "Accueil",
      layout: {
        type: "grid",
        breakpoints: {},
        items: [{ id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} }],
      },
    },
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
    type: "__ctx_probe__",
    label: "probe",
    defaultProps: {},
    defaultSize: { w: 1, h: 1 },
    PropsPanel: () => null,
    Component: () => {
      const ctx = useAnalyticsContext();
      return (
        <p>
          probe-timeRange:{ctx.timeRange ? `${ctx.timeRange.from}..${ctx.timeRange.to}` : "none"}
        </p>
      );
    },
  });
}

const okItem: Item = {
  pk: "9",
  resourceType: "app",
  title: "App",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "",
  configId: null,
  isPublished: true,
  permissions: OWNER_PERMISSIONS,
};

test("navigate() percent-encodes pk and the target pageId", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(config),
  });
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
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(config),
  });
  expect(await screen.findByRole("button", { name: "Accueil" })).toBeInTheDocument();
});

const probeConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  interactions: "auto",
  layout: emptyLayout,
  pages: [
    {
      id: "page-1",
      name: "Accueil",
      layout: {
        type: "grid",
        breakpoints: {},
        items: [{ id: "p1", widget: "__ctx_probe__", x: 0, y: 0, w: 4, h: 2, props: {} }],
      },
    },
  ],
};

test("hydrates the initial analytics context from the ctx URL param", async () => {
  const encoded = encodeAnalyticsContext({
    timeRange: { from: "2026-01-01", to: "2026-02-01" },
    extent: null,
    crossFilter: {},
  });
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(probeConfig),
    },
    [`/apps/9/page-1?ctx=${encoded}`],
  );
  expect(await screen.findByText("probe-timeRange:2026-01-01..2026-02-01")).toBeInTheDocument();
});

const dateFilterConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  interactions: "auto",
  layout: emptyLayout,
  pages: [
    {
      id: "page-1",
      name: "Accueil",
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          {
            id: "d1",
            widget: "dateRangeFilter",
            x: 0,
            y: 0,
            w: 4,
            h: 1,
            props: { label: "Période" },
          },
        ],
      },
    },
  ],
};

const manualDateFilterConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  // interactions absent (comportement des apps existantes / "manual" explicite)
  layout: emptyLayout,
  pages: [
    {
      id: "page-1",
      name: "Accueil",
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          {
            id: "d1",
            widget: "dateRangeFilter",
            x: 0,
            y: 0,
            w: 4,
            h: 1,
            props: { label: "Période" },
          },
        ],
      },
    },
  ],
};

test("never adds a ctx URL param when interactions is absent (manual mode) — additivité", async () => {
  // Fake timers are enabled BEFORE render (with shouldAdvanceTime so
  // findByLabelText's internal polling still progresses in real time): this
  // is what makes the test a genuine regression guard. AnalyticsContextProvider
  // emits its mount-time onStateChange (the empty context) as soon as the
  // widget mounts — if that emission were still able to schedule a debounced
  // write (i.e. if the guard in handleAnalyticsContextChange were removed),
  // the resulting setTimeout would be captured by the fake clock here and
  // fire when we advance it below. Enabling fake timers only after mount (as
  // a naive version of this test would) lets that mount-time setTimeout slip
  // through as a REAL timer that never fires within the test, making the
  // "no ctx" assertion pass regardless of whether the guard exists.
  vi.useFakeTimers({ shouldAdvanceTime: true });
  try {
    renderRuntime({
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(manualDateFilterConfig),
    });
    const fromInput = await screen.findByLabelText("Date de début");
    const toInput = await screen.findByLabelText("Date de fin");
    expect(screen.getByTestId("search")).toHaveTextContent("");

    fireEvent.change(fromInput, { target: { value: "2026-01-01" } });
    fireEvent.change(toInput, { target: { value: "2026-02-01" } });
    act(() => {
      vi.advanceTimersByTime(EXTENT_DEBOUNCE_MS);
    });

    // Even past the debounce window (and past the empty-state effect fired at
    // mount by AnalyticsContextProvider), no ?ctx= must appear: a manual-mode
    // app must stay byte-identical to today's URL behaviour.
    const search = screen.getByTestId("search").textContent ?? "";
    expect(new URLSearchParams(search).has("ctx")).toBe(false);
  } finally {
    vi.useRealTimers();
  }
});

const navAutoConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  interactions: "auto",
  layout: emptyLayout,
  pages: [
    {
      id: "page-1",
      name: "Accueil",
      layout: {
        type: "grid",
        breakpoints: {},
        items: [
          { id: "n1", widget: "nav", x: 0, y: 0, w: 4, h: 1, props: {} },
          {
            id: "d1",
            widget: "dateRangeFilter",
            x: 0,
            y: 1,
            w: 4,
            h: 1,
            props: { label: "Période" },
          },
        ],
      },
    },
    { id: "page-2", name: "Détails", layout: emptyLayout },
  ],
};

test("resolves the debounced ctx write against the pathname active when the timer fires, not the one active when it was scheduled (Task 18 stale-closure fix)", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(navAutoConfig),
  });
  const fromInput = await screen.findByLabelText("Date de début");
  const toInput = await screen.findByLabelText("Date de fin");

  vi.useFakeTimers();
  try {
    fireEvent.change(fromInput, { target: { value: "2026-01-01" } });
    fireEvent.change(toInput, { target: { value: "2026-02-01" } });
    // Not written yet — still debouncing.
    expect(screen.getByTestId("search")).toHaveTextContent("");

    // Navigate to a different page WHILE the write is still debouncing (as a
    // story chapter change would).
    fireEvent.click(screen.getByRole("button", { name: "Détails" }));
    expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/page-2");

    act(() => {
      vi.advanceTimersByTime(EXTENT_DEBOUNCE_MS);
    });

    // The write must resolve against the NEW pathname — not yank the user
    // back to the pathname active when the debounce was scheduled (the
    // stale-closure bug fixed in Task 18).
    expect(screen.getByTestId("loc")).toHaveTextContent("/apps/9/page-2");
    const search = screen.getByTestId("search").textContent ?? "";
    expect(new URLSearchParams(search).get("ctx")).toBeTruthy();
  } finally {
    vi.useRealTimers();
  }
});

test("writes the analytics context back to the ctx URL param, debounced, with replace semantics", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
  });
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
    act(() => {
      vi.advanceTimersByTime(EXTENT_DEBOUNCE_MS);
    });

    const search = screen.getByTestId("search").textContent ?? "";
    const ctx = new URLSearchParams(search).get("ctx");
    expect(ctx).toBeTruthy();
    expect(decodeAnalyticsContext(ctx)).toEqual({
      timeRange: { from: "2026-01-01", to: "2026-02-01" },
      extent: null,
      crossFilter: {},
    });
    // replace semantics: the location changed, but no new history entry was pushed.
    expect(screen.getByTestId("navtype")).toHaveTextContent("REPLACE");
  } finally {
    vi.useRealTimers();
  }
});

test("the save-view button is absent when interactions is manual", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(manualDateFilterConfig),
  });
  await screen.findByLabelText("Date de début");
  expect(screen.queryByRole("button", { name: "Enregistrer la vue" })).not.toBeInTheDocument();
});

test("the save-view button is present when interactions is auto", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
  });
  expect(await screen.findByRole("button", { name: "Enregistrer la vue" })).toBeInTheDocument();
});

test("exportRender=1 hides the save-view action bar and marks the page export-ready once the config loads", async () => {
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
    },
    ["/apps/9/page-1?exportRender=1"],
  );
  await screen.findByLabelText("Date de début");
  expect(screen.queryByRole("button", { name: "Enregistrer la vue" })).not.toBeInTheDocument();
  await waitFor(() => expect(document.body.getAttribute("data-export-ready")).toBe("true"));
});

// Fix round (finding I1) : le bouton/panneau Exporter doit apparaître dès
// que exportEnabled est vrai, indépendamment de interactions === "auto" —
// avant ce correctif, ExportPanel vivait entièrement à l'intérieur de la
// barre gated sur interactions === "auto", ce qui le cachait sur la plupart
// des apps/dashboards (interactions absent/"manual" par défaut).
test("the export button shows when exportEnabled is true, even with interactions absent/manual (finding I1)", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(manualDateFilterConfig),
    getInstanceInfo: vi
      .fn()
      .mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled: true }),
  });
  expect(await screen.findByRole("button", { name: "Exporter" })).toBeInTheDocument();
  // The interactions-gated "Enregistrer la vue" button keeps its own,
  // independent gate — manual mode still hides it.
  expect(screen.queryByRole("button", { name: "Enregistrer la vue" })).not.toBeInTheDocument();
});

test("the export button is absent when exportEnabled is false, even with interactions auto", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
    getInstanceInfo: vi
      .fn()
      .mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled: false }),
  });
  expect(await screen.findByRole("button", { name: "Enregistrer la vue" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Exporter" })).not.toBeInTheDocument();
});

test("the export button never renders during ?exportRender=1 capture itself, even when exportEnabled is true", async () => {
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
      getInstanceInfo: vi
        .fn()
        .mockResolvedValue({ readOnly: false, etlEnabled: false, exportEnabled: true }),
    },
    ["/apps/9/page-1?exportRender=1"],
  );
  await screen.findByLabelText("Date de début");
  expect(screen.queryByRole("button", { name: "Exporter" })).not.toBeInTheDocument();
});

// Fix round (finding I4) : PrintLayout title/cartouche must render as an
// overlay in the app/dashboard export capture, mirroring MapEditorPage's
// existing overlay pattern — previously silently dropped for apps.
const printLayoutConfig: AppConfig = {
  kind: "app",
  theme: {},
  dataSources: [],
  messages: [],
  layout: emptyLayout,
  pages: [{ id: "page-1", name: "Accueil", layout: emptyLayout }],
  printLayout: {
    pageSize: "a4",
    orientation: "portrait",
    title: "Rapport trimestriel",
    cartouche: "GeoStudio — confidentiel",
  },
};

test("exportRender=1 renders the printLayout title/cartouche overlay (finding I4)", async () => {
  renderRuntime(
    {
      getItem: vi.fn().mockResolvedValue(okItem),
      getAppConfig: vi.fn().mockResolvedValue(printLayoutConfig),
    },
    ["/apps/9/page-1?exportRender=1"],
  );
  expect(await screen.findByText("Rapport trimestriel")).toBeInTheDocument();
  expect(screen.getByText("GeoStudio — confidentiel")).toBeInTheDocument();
});

test("the printLayout overlay does not render outside of exportRender", async () => {
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(printLayoutConfig),
  });
  await waitFor(() => expect(screen.queryByRole("status")).not.toBeInTheDocument());
  expect(screen.queryByText("Rapport trimestriel")).not.toBeInTheDocument();
  expect(screen.queryByText("GeoStudio — confidentiel")).not.toBeInTheDocument();
});

test("saving a view captures the current analytics context and posts a bookmark", async () => {
  const createBookmarkItem = vi.fn().mockResolvedValue({
    pk: "bm-1",
    resourceType: "bookmark",
    title: "Ma vue",
    abstract: "",
    owner: "tanguy",
    thumbnailUrl: null,
    date: "",
    configId: "cfg-bm-1",
    isPublished: false,
  });
  renderRuntime({
    getItem: vi.fn().mockResolvedValue(okItem),
    getAppConfig: vi.fn().mockResolvedValue(dateFilterConfig),
    createBookmarkItem,
  });
  const fromInput = await screen.findByLabelText("Date de début");
  const toInput = await screen.findByLabelText("Date de fin");
  await userEvent.type(fromInput, "2026-01-01");
  await userEvent.type(toInput, "2026-02-01");

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer la vue" }));
  await userEvent.type(screen.getByLabelText("Nom de la vue"), "Ma vue");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));

  await waitFor(() =>
    expect(createBookmarkItem).toHaveBeenCalledWith({
      title: "Ma vue",
      owner: "tanguy",
      appId: "9",
      pageId: "page-1",
      timeRange: { from: "2026-01-01", to: "2026-02-01" },
      extent: null,
      crossFilter: {},
    }),
  );
});
