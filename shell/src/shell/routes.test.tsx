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

vi.mock("../pages/MapEditorPage", () => ({
  MapEditorPage: ({ pk }: { pk: string }) => <div>map-editor-{pk}</div>,
}));

vi.mock("../pages/AppBuilderPage", () => ({
  AppBuilderPage: ({ pk }: { pk: string }) => <div>app-builder-{pk}</div>,
}));

vi.mock("../pages/AppRuntimePage", () => ({
  AppRuntimePage: ({ pk, pageId }: { pk: string; pageId?: string }) => <div>app-runtime-{pk}-{pageId ?? "none"}</div>,
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
          { pk: "1", resourceType: "app", title: "Alpha", abstract: "", owner: "alice", thumbnailUrl: null, date: "", configId: null, isPublished: false },
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
