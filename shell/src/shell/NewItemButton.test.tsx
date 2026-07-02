import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
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

function DetailProbe() {
  const { pk } = useParams();
  return <div>detail-{pk}</div>;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          {children}
          <Routes>
            <Route path="/items/:pk" element={<DetailProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

test("creates an item and navigates to its detail", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.getByRole("dialog", { name: /nouvel/i })).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText("Titre"), "My App");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("detail-99")).toBeInTheDocument();
});

test("does not submit an empty title", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(screen.queryByText(/^detail-/)).not.toBeInTheDocument();
});

test("creates a Map and navigates to the editor route", async () => {
  server.use(
    http.post("https://builder.test/configs", () =>
      HttpResponse.json({ id: "cfg-77", kind: "map", itemId: "77", version: 1, config: {} }),
    ),
  );
  function MapProbe() {
    const { pk } = useParams();
    return <div>map-{pk}</div>;
  }
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({
    geonodeUrl: "https://geonode.test",
    builderUrl: "https://builder.test",
    getToken: () => "t",
  });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/items/:pk" element={<DetailProbe />} />
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
    http.post("https://builder.test/configs", () => new HttpResponse(null, { status: 500 })),
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
  expect(screen.queryByText(/^detail-/)).not.toBeInTheDocument();
});
