// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams, useLocation } from "react-router-dom";
import { vi } from "vitest";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { NewItemButton } from "./NewItemButton";
import { expectAriaWired } from "../test/expectAriaWired";

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

// SP-42/F-shell-pages-01 : NewItemButton lit désormais useMe() pour gater ses
// options par privilège. Le profil par défaut servi par GET /me
// (test/msw/handlers.ts) n'inclut pas apps.manage — historiquement sans
// conséquence, seulement parce que rien ne le consultait avant ce correctif.
// Seeder directement le cache React Query (au lieu de laisser la requête MSW
// réelle résoudre de façon asynchrone) rend le profil disponible dès le
// premier rendu, sans dépendance de timing sur les tests existants qui
// n'affirment pas sur les privilèges eux-mêmes ; `staleTime: Infinity` évite
// qu'un refetch d'arrière-plan écrase ce seed par la réponse MSW incomplète.
const CREATOR_ME = {
  id: "u1",
  username: "alice",
  firstName: "Alice",
  lastName: "Martin",
  email: "alice@example.com",
  tenantId: "t1",
  role: { id: "role-creator", name: "Créateur", slug: "creator" },
  privileges: ["catalog.manage", "maps.manage", "data.view", "data.manage", "apps.manage"],
  version: "0.1.0",
  tenantSlug: "demo",
};

function makeQueryClient(privileges: string[] = CREATOR_ME.privileges) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryDefaults(["me"], { staleTime: Infinity });
  queryClient.setQueryData(["me"], { ...CREATOR_ME, privileges });
  return queryClient;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = makeQueryClient();
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
  const newButton = screen.getByRole("button", { name: "Nouveau" });
  expectAriaWired(newButton, newButton.getAttribute("aria-controls")!, false);
  await userEvent.click(newButton);
  expect(screen.getByRole("dialog", { name: /nouvel/i })).toBeInTheDocument();
  expectAriaWired(newButton, newButton.getAttribute("aria-controls")!, true);
  expect(screen.getByRole("dialog", { name: /nouvel/i })).toHaveAttribute(
    "id",
    newButton.getAttribute("aria-controls"),
  );
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
  const queryClient = makeQueryClient();
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
  server.use(http.post("https://core.test/configs", () => new HttpResponse(null, { status: 500 })));
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
      return HttpResponse.json({
        id: "cfg-9",
        kind: "app",
        itemId: "9",
        version: 1,
        config: body.config,
      });
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
  const queryClient = makeQueryClient();
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
    http.get("https://core.test/collections", () => HttpResponse.json({ collections: [] })),
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
  const queryClient = makeQueryClient();
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

test("the Pipeline option is absent from the Type select when etlEnabled is false (the MSW default)", async () => {
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(screen.queryByRole("option", { name: "Pipeline" })).not.toBeInTheDocument();
});

test("the Pipeline option is present when etlEnabled is true", async () => {
  server.use(
    http.get("https://core.test/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: true }),
    ),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  expect(await screen.findByRole("option", { name: "Pipeline" })).toBeInTheDocument();
});

test("selecting Pipeline only asks for a title, and navigates to /pipelines/new with the title in route state, without calling the create API", async () => {
  server.use(
    http.get("https://core.test/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: true }),
    ),
  );
  let configPosted = false;
  server.use(
    http.post("https://core.test/configs", () => {
      configPosted = true;
      return HttpResponse.json({ id: "cfg-x", kind: "app", itemId: "x" });
    }),
  );
  function PipelineNewProbe() {
    const location = useLocation();
    const state = location.state as { title?: string } | null;
    return <div>pipeline-new-{state?.title ?? ""}</div>;
  }
  const queryClient = makeQueryClient();
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/apps/:pk/edit" element={<AppBuilderProbe />} />
            <Route path="/pipelines/new" element={<PipelineNewProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "pipeline");
  await userEvent.type(screen.getByLabelText("Titre"), "Nettoyer villes");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("pipeline-new-Nettoyer villes")).toBeInTheDocument();
  expect(configPosted).toBe(false);
});

test("selecting « Dataset par requête visuelle » only asks for a title, and navigates to /datasets/visual-query/new with the title in route state, without calling the create API", async () => {
  server.use(
    http.get("https://core.test/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: true }),
    ),
  );
  let configPosted = false;
  server.use(
    http.post("https://core.test/configs", () => {
      configPosted = true;
      return HttpResponse.json({ id: "cfg-x", kind: "app", itemId: "x" });
    }),
  );
  function VisualQueryNewProbe() {
    const location = useLocation();
    const state = location.state as { title?: string } | null;
    return <div>visual-query-new-{state?.title ?? ""}</div>;
  }
  const queryClient = makeQueryClient();
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
          <Routes>
            <Route path="/datasets/visual-query/new" element={<VisualQueryNewProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await userEvent.selectOptions(await screen.findByLabelText("Type"), "visual-query");
  await userEvent.type(screen.getByLabelText("Titre"), "Ma requête");
  await userEvent.click(screen.getByRole("button", { name: "Créer" }));
  expect(await screen.findByText("visual-query-new-Ma requête")).toBeInTheDocument();
  expect(configPosted).toBe(false);
});

test("the visual-query option is hidden when etlEnabled is false", async () => {
  server.use(
    http.get("https://core.test/instance", () =>
      HttpResponse.json({ readOnly: false, etlEnabled: false }),
    ),
  );
  render(
    <Harness>
      <NewItemButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Nouveau" }));
  await waitFor(() =>
    expect(
      screen.queryByRole("option", { name: "Dataset par requête visuelle" }),
    ).not.toBeInTheDocument(),
  );
});

test("SP-42/F-shell-pages-01 : masque tout le bouton pour un Lecteur (0 privilège, etlEnabled=false)", async () => {
  const queryClient = makeQueryClient([]);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Nouveau" })).not.toBeInTheDocument(),
  );
});

test("SP-42/F-shell-pages-01 : un profil ne portant que maps.manage ne voit que Map dans le sélecteur Type", async () => {
  const queryClient = makeQueryClient(["maps.manage"]);
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <NewItemButton />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await userEvent.click(await screen.findByRole("button", { name: "Nouveau" }));
  await waitFor(() => expect(screen.getByLabelText("Type")).toHaveValue("map"));
  expect(screen.queryByRole("option", { name: "App" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Dashboard" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Site" })).not.toBeInTheDocument();
  expect(screen.queryByRole("option", { name: "Dataset partagé" })).not.toBeInTheDocument();
  expect(screen.getByRole("option", { name: "Map" })).toBeInTheDocument();
});
