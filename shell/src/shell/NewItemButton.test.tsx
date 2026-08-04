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

test("auto-generates the slug from the title when the type is Site", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "site");
  await userEvent.type(screen.getByLabelText("Titre"), "Mon Portail");
  expect(screen.getByLabelText("Slug")).toHaveValue("mon-portail");
});

test("disables the Créer button when the edited slug is invalid", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "site");
  await userEvent.type(screen.getByLabelText("Titre"), "Mon Portail");
  await userEvent.clear(screen.getByLabelText("Slug"));
  await userEvent.type(screen.getByLabelText("Slug"), "Pas Valide");
  expect(screen.getByRole("button", { name: "Créer" })).toBeDisabled();
});

test("submits a Site with its slug in the POST body", async () => {
  let body: any = null;
  server.use(
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json(
        { id: "cfg-1", kind: "site", itemId: "site-9", version: 1, config: body.config },
        { status: 201 },
      );
    }),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "site");
  await userEvent.type(screen.getByLabelText("Titre"), "Mon Portail");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  await waitFor(() => expect(body).not.toBeNull());
  expect(body.slug).toBe("mon-portail");
  expect(body.config.kind).toBe("site");
  expect(await screen.findByText("app-builder-site-9")).toBeInTheDocument();
});

test("creating a dataset posts collectionId and navigates to the dataset editor", async () => {
  let body: any;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({
        collections: [
          {
            id: "parcs",
            title: "Parcs",
            description: "",
            tableName: "parcs",
            isPublic: true,
            editable: true,
            geometryType: "Point",
            srid: 4326,
            pkColumn: "id",
            canWrite: true,
            featureCount: 3,
            owner: "alice",
          },
        ],
      }),
    ),
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds", kind: "dataset", itemId: "ds-9" }, { status: 201 });
    }),
  );
  function DatasetProbe() {
    const { pk } = useParams();
    return <div>dataset-{pk}</div>;
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
            <Route path="/datasets/:pk/edit" element={<DatasetProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await userEvent.selectOptions(await screen.findByLabelText("Collection source"), "parcs");
  await userEvent.type(screen.getByLabelText("Titre"), "Parcs partagés");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));

  await waitFor(() => expect(body?.config?.dataset?.collectionId).toBe("parcs"));
  expect(await screen.findByText("dataset-ds-9")).toBeInTheDocument();
});

test("creates an arcgis-sourced dataset from a feature-layer picker", async () => {
  let body: any;
  server.use(
    http.get("https://core.test/collections", () =>
      HttpResponse.json({ collections: [] }),
    ),
    http.get("https://core.test/harvest/feature-layers", () =>
      HttpResponse.json({ layers: [{ id: "layer-1", title: "Bâtiments" }] }),
    ),
    http.post("https://core.test/configs", async ({ request }) => {
      body = await request.json();
      return HttpResponse.json({ id: "cfg-ds", kind: "dataset", itemId: "ds-1" }, { status: 201 });
    }),
  );
  function DatasetProbe() {
    const { pk } = useParams();
    return <div>dataset-{pk}</div>;
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
            <Route path="/datasets/:pk/edit" element={<DatasetProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(screen.getByLabelText("Type"), "dataset");
  await userEvent.selectOptions(screen.getByLabelText("Type de source"), "arcgis");
  await userEvent.selectOptions(await screen.findByLabelText("Couche ArcGIS"), "layer-1");
  await userEvent.type(screen.getByLabelText("Titre"), "Bâtiments (live)");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));

  await waitFor(() => expect(body?.config?.dataset?.source).toBe("arcgis"));
  await waitFor(() => expect(body?.config?.dataset?.arcgisItemId).toBe("layer-1"));
  expect(await screen.findByText("dataset-ds-1")).toBeInTheDocument();
});
