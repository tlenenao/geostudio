// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { NewItemButton } from "./NewItemButton";

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

function AppBuilderProbe() {
  const { pk } = useParams();
  return <div>app-builder-{pk}</div>;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          {children}
          <Routes>
            <Route path="/apps/:pk/edit" element={<AppBuilderProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("creates an App and navigates to the app builder", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.getByRole("dialog", { name: /nouvel/i })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Titre"), "My App");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("app-builder-99")).toBeInTheDocument();
});

test("does not submit an empty title", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(screen.queryByText(/^app-builder-/)).not.toBeInTheDocument();
});

test("creates a Map and navigates to the editor route", async () => {
  server.use(
    http.post("https://core.test/configs", () =>
      HttpResponse.json({ id: "cfg-77", kind: "map", itemId: "77", version: 1, config: {} }),
    ),
  );
  function MapProbe() {
    const { pk } = useParams();
    return <div>map-{pk}</div>;
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    coreUrl: "https://core.test",
    getToken: () => "t",
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/apps/:pk/edit" element={<AppBuilderProbe />} />
            <Route path="/maps/:pk" element={<MapProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  await userEvent.type(screen.getByLabelText("Titre"), "Ma Carte");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("map-77")).toBeInTheDocument();
});

test("shows an alert and stays on the page when creation fails", async () => {
  server.use(
    http.post("https://core.test/configs", () => new HttpResponse(null, { status: 500 })),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.type(screen.getByLabelText("Titre"), "Boom");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByRole("alert")).toBeInTheDocument();
  expect(screen.queryByText(/^app-builder-/)).not.toBeInTheDocument();
});

test("shows a Modèle select for app/dashboard, filtered by the current type", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.getByRole("option", { name: "Vide" })).toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Deux colonnes" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Tableau de bord basique" })).not.toBeInTheDocument();
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dashboard");
  expect(screen.getByRole("option", { name: "Tableau de bord basique" })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Deux colonnes" })).not.toBeInTheDocument();
});

test("creating from a template posts its layout", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-9", kind: "app", itemId: "9", version: 1, config: body.config });
    }),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Modèle"), "two-column");
  await userEvent.type(screen.getByLabelText("Titre"), "Mon app");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  await waitFor(() => expect(body).not.toBeNull());
  expect(body.config.layout.items).toHaveLength(2);
  expect(body.config.layout.items[0].widget).toBe("text");
});

test("does not show a Modèle select for the map type", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "map");
  expect(screen.queryByLabelText("Modèle")).not.toBeInTheDocument();
});
