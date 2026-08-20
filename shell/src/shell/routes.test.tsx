// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import type { ReactNode } from "react";
import { vi } from "vitest";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { AppRoutes } from "./routes";
import type { AuthState } from "../auth/useAuth";

const authState: AuthState = {
  isLoading: false,
  isAuthenticated: true,
  username: "alice",
  error: null,
  getAccessToken: () => "t",
  signIn: vi.fn(),
  signOut: vi.fn(),
};
vi.mock("../auth/useAuth", () => ({ useAuth: () => authState }));

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});

vi.mock("../pages/MapEditorPage", () => ({
  MapEditorPage: ({ pk }: { pk: string }) => <div>map-editor-{pk}</div>,
}));

vi.mock("../pages/AppBuilderPage", () => ({
  AppBuilderPage: ({ pk }: { pk: string }) => <div>app-builder-{pk}</div>,
}));

vi.mock("../pages/AppRuntimePage", () => ({
  AppRuntimePage: ({ pk, pageId }: { pk: string; pageId?: string }) => (
    <div>
      app-runtime-{pk}-{pageId ?? "none"}
    </div>
  ),
}));

vi.mock("../pages/AdminExtensionsPage", () => ({
  AdminExtensionsPage: () => <div>admin-extensions</div>,
}));

function wrap(children: ReactNode, initial = "/") {
  const queryClient = new QueryClient({
    defaultOptions: { queries: { retry: false } },
  });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  return render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={[initial]}>{children}</MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("navigates from catalog to app builder on open (app item)", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "1",
            resourceType: "app",
            title: "Alpha",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
  );
  wrap(<AppRoutes />);
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText("app-builder-1")).toBeInTheDocument();
});

test("renders the app builder route at /apps/:pk/edit", () => {
  wrap(<AppRoutes />, "/apps/42/edit");
  expect(screen.getByText("app-builder-42")).toBeInTheDocument();
});

test("renders the app runtime route at /apps/:pk", () => {
  wrap(<AppRoutes />, "/apps/42");
  expect(screen.getByText("app-runtime-42-none")).toBeInTheDocument();
});

test("renders the app runtime route with a pageId at /apps/:pk/:pageId", () => {
  wrap(<AppRoutes />, "/apps/42/xyz");
  expect(screen.getByText("app-runtime-42-xyz")).toBeInTheDocument();
});

test("the runtime route renders without going through the auth gate", () => {
  authState.isAuthenticated = false;
  wrap(<AppRoutes />, "/apps/42");
  expect(screen.getByText("app-runtime-42-none")).toBeInTheDocument();
  authState.isAuthenticated = true;
});

test("renders the admin extensions route at /admin/extensions", () => {
  wrap(<AppRoutes />, "/admin/extensions");
  expect(screen.getByText("admin-extensions")).toBeInTheDocument();
});

test("protected routes still require authentication", () => {
  authState.isAuthenticated = false;
  wrap(<AppRoutes />, "/");
  expect(authState.signIn).toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: /ouvrir/i })).not.toBeInTheDocument();
  authState.isAuthenticated = true;
});

test("renders the bookmarks catalog at /bookmarks, filtered to type=bookmark", async () => {
  let lastUrl = "";
  server.use(
    http.get("https://core.test/items", ({ request }) => {
      lastUrl = request.url;
      return HttpResponse.json({
        items: [
          {
            pk: "bm-1",
            resourceType: "bookmark",
            title: "Ma vue",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      });
    }),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await screen.findByText("Ma vue");
  expect(new URL(lastUrl).searchParams.get("type")).toBe("bookmark");
});

test("opening a bookmark navigates to its app+page+ctx URL, not an editor", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "bm-1",
            resourceType: "bookmark",
            title: "Ma vue",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
    http.get("https://core.test/configs/by-item/bm-1", () =>
      HttpResponse.json({
        id: "cfg-bm-1",
        itemId: "bm-1",
        kind: "bookmark",
        config: {
          version: 1,
          kind: "bookmark",
          bookmark: {
            appId: "42",
            pageId: "page-1",
            timeRange: null,
            extent: null,
            crossFilter: {},
          },
        },
      }),
    ),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByText(/^app-runtime-42-page-1$/)).toBeInTheDocument();
});

test("exportRender=1 on a protected map route hides AppLayout's header/nav chrome (Task 10 fix round 1)", () => {
  // Regression for the Critical review finding: MapEditorPage's own nude-chrome
  // guard only controls what MapEditorPage renders, not AppLayout sitting above
  // it in ProtectedLayout. Render through the REAL AppRoutes -> ProtectedLayout
  // -> AppLayout tree (MapEditorPage itself is mocked to a plain div — the
  // point here is AppLayout's chrome, not MapEditorPage's own content) so this
  // actually exercises the integration gap the unit tests missed.
  wrap(<AppRoutes />, "/maps/77?exportRender=1");
  expect(screen.getByText("map-editor-77")).toBeInTheDocument();
  expect(screen.queryByText("GeoStudio")).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /déconnexion/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("link", { name: "Catalogue" })).not.toBeInTheDocument();
});

test("without exportRender, the same map route still renders AppLayout's header/nav chrome normally", () => {
  wrap(<AppRoutes />, "/maps/77");
  expect(screen.getByText("map-editor-77")).toBeInTheDocument();
  expect(screen.getByText("GeoStudio")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: /déconnexion/i })).toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Catalogue" })).toBeInTheDocument();
});

test("a failed bookmark config fetch surfaces an error instead of silently doing nothing", async () => {
  server.use(
    http.get("https://core.test/items", () =>
      HttpResponse.json({
        items: [
          {
            pk: "bm-1",
            resourceType: "bookmark",
            title: "Ma vue",
            abstract: "",
            owner: "alice",
            thumbnailUrl: null,
            date: "",
            configId: null,
            isPublished: false,
          },
        ],
        total: 1,
        page: 1,
        pageSize: 12,
      }),
    ),
    http.get(
      "https://core.test/configs/by-item/bm-1",
      () => new HttpResponse(null, { status: 500 }),
    ),
  );
  wrap(<AppRoutes />, "/bookmarks");
  await userEvent.click((await screen.findAllByRole("button", { name: /ouvrir/i }))[0]);
  expect(await screen.findByRole("alert")).toHaveTextContent(/échec de l.ouverture/i);
  // No navigation happened: we're still on the bookmarks catalog, not the app runtime.
  expect(screen.getByText("Ma vue")).toBeInTheDocument();
  expect(screen.queryByText(/^app-runtime-/)).not.toBeInTheDocument();
});
