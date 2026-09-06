// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { ImportFileButton } from "./ImportFileButton";
import { expectAriaWired } from "../test/expectAriaWired";

function MapProbe() {
  const { pk } = useParams();
  return <div>map-{pk}</div>;
}

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          {children}
          <Routes>
            <Route path="/maps/:pk" element={<MapProbe />} />
          </Routes>
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>
  );
}

function geojsonFile() {
  return new File(['{"type":"FeatureCollection","features":[]}'], "villes.geojson", {
    type: "application/geo+json",
  });
}

test("uploads a file and navigates to the created map once the job is done", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" }),
    ),
    http.put("https://minio.test/upload-1", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-1" })),
    http.get("https://core.test/v1/uploads/job-1", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_abc",
        itemId: "42",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  const importButton = screen.getByRole("button", { name: "Importer un fichier" });
  expectAriaWired(importButton, importButton.getAttribute("aria-controls")!, false);
  await userEvent.click(importButton);
  expectAriaWired(importButton, importButton.getAttribute("aria-controls")!, true);
  expect(screen.getByRole("dialog")).toHaveAttribute(
    "id",
    importButton.getAttribute("aria-controls"),
  );
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-42")).toBeInTheDocument());
});

test("shows the job's error message and lets the user retry", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-2", key: "t/def-broken.geojson" }),
    ),
    http.put("https://minio.test/upload-2", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-2" })),
    http.get("https://core.test/v1/uploads/job-2", () =>
      HttpResponse.json({
        status: "error",
        errorMessage: "JSON invalide",
        collectionId: null,
        itemId: null,
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Casse");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("JSON invalide"));
  expect(screen.getByRole("button", { name: "Importer" })).toBeEnabled();
});

test("shows manual lat/lon selectors when a CSV's columns cannot be auto-detected", async () => {
  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  const csv = new File(["nom,valeur\nA,1\n"], "data.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), csv);

  await waitFor(() => expect(screen.getByLabelText("Colonne latitude")).toBeInTheDocument());
  expect(screen.getByLabelText("Colonne longitude")).toBeInTheDocument();
});

test("does not show manual lat/lon selectors when a CSV's columns are auto-detectable", async () => {
  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  const csv = new File(["nom,lat,lon\nParis,48.85,2.35\n"], "villes.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), csv);

  await waitFor(() => expect(screen.getByLabelText("Titre de la collection")).toBeInTheDocument());
  expect(screen.queryByLabelText("Colonne latitude")).not.toBeInTheDocument();
});

function gpkgFile(name = "villes.gpkg") {
  return new File(["fake-gpkg-bytes"], name, { type: "application/geopackage+sqlite3" });
}

test("auto-selects the only layer of a GeoPackage without showing a picker", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-3", key: "t/ghi-villes.gpkg" }),
    ),
    http.put("https://minio.test/upload-3", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({ layers: [{ name: "villes", featureCount: 2, geometryType: "Point" }] }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("villes");
      return HttpResponse.json({ jobId: "job-3" });
    }),
    http.get("https://core.test/v1/uploads/job-3", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_x",
        itemId: "99",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-99")).toBeInTheDocument());
});

test("shows a layer picker for a multi-layer GeoPackage and imports the chosen layer", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-4", key: "t/jkl-multi.gpkg" }),
    ),
    http.put("https://minio.test/upload-4", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({
        layers: [
          { name: "villes", featureCount: 2, geometryType: "Point" },
          { name: "routes", featureCount: 5, geometryType: "LineString" },
        ],
      }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("routes");
      return HttpResponse.json({ jobId: "job-4" });
    }),
    http.get("https://core.test/v1/uploads/job-4", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_y",
        itemId: "100",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile("multi.gpkg"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Multi");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "routes");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-100")).toBeInTheDocument());
});

function xlsxFile(name = "villes.xlsx") {
  return new File(["fake-xlsx-bytes"], name, {
    type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
  });
}

test("SP-56 : XLSX avec colonnes lat/lon détectées saute la sélection manuelle", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-5", key: "t/mno-villes.xlsx" }),
    ),
    http.put("https://minio.test/upload-5", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({ layers: [], fields: ["nom", "lat", "lon"] }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { latField?: string };
      expect(body.latField).toBeUndefined();
      return HttpResponse.json({ jobId: "job-5" });
    }),
    http.get("https://core.test/v1/uploads/job-5", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_z",
        itemId: "101",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), xlsxFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes XLSX");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-101")).toBeInTheDocument());
});

test("SP-56 : XLSX sans colonnes lat/lon détectables affiche le formulaire manuel", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-6", key: "t/pqr-villes.xlsx" }),
    ),
    http.put("https://minio.test/upload-6", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({ layers: [], fields: ["nom", "y_coord", "x_coord"] }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { latField?: string; lonField?: string };
      expect(body.latField).toBe("y_coord");
      expect(body.lonField).toBe("x_coord");
      return HttpResponse.json({ jobId: "job-6" });
    }),
    http.get("https://core.test/v1/uploads/job-6", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_w",
        itemId: "102",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), xlsxFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes XLSX 2");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Colonne latitude")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Colonne latitude"), "y_coord");
  await userEvent.selectOptions(screen.getByLabelText("Colonne longitude"), "x_coord");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-102")).toBeInTheDocument());
});

function kmlFile(name = "paris.kml") {
  return new File(["<kml/>"], name, { type: "application/vnd.google-earth.kml+xml" });
}

test("SP-56 : KML multi-couches passe par la sélection de couche (même flux que GPKG)", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-7", key: "t/stu-villes.kml" }),
    ),
    http.put("https://minio.test/upload-7", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({
        layers: [
          { name: "a", featureCount: 1, geometryType: "Point" },
          { name: "b", featureCount: 1, geometryType: "Point" },
        ],
      }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("b");
      return HttpResponse.json({ jobId: "job-7" });
    }),
    http.get("https://core.test/v1/uploads/job-7", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_kml",
        itemId: "103",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), kmlFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes KML");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "b");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-103")).toBeInTheDocument());
});

function parquetFile(name = "villes.parquet") {
  return new File(["fake-parquet-bytes"], name, { type: "application/octet-stream" });
}

test("SP-56 : GeoParquet ne passe par aucune étape d'inspection, job créé directement", async () => {
  let inspectCalled = false;
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-8", key: "t/vwx-villes.parquet" }),
    ),
    http.put("https://minio.test/upload-8", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () => {
      inspectCalled = true;
      return HttpResponse.json({ layers: [] });
    }),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-8" })),
    http.get("https://core.test/v1/uploads/job-8", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_parquet",
        itemId: "104",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), parquetFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes Parquet");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-104")).toBeInTheDocument());
  expect(inspectCalled).toBe(false);
});

test("SP-42/F-shell-pages-01 (fusion F-shell-pages-02) : masque le bouton pour un profil sans data.manage", async () => {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  queryClient.setQueryDefaults(["me"], { staleTime: Infinity });
  queryClient.setQueryData(["me"], {
    id: "u1",
    username: "alice",
    firstName: "Alice",
    lastName: "Martin",
    email: "alice@example.com",
    tenantId: "t1",
    role: { id: "role-reader", name: "Lecteur", slug: "reader" },
    privileges: [],
    version: "0.1.0",
    tenantSlug: "demo",
  });
  const client = createItemClient({ coreUrl: "https://core.test", getToken: () => "t" });
  render(
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>
        <MemoryRouter initialEntries={["/"]}>
          <ImportFileButton />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() =>
    expect(screen.queryByRole("button", { name: "Importer un fichier" })).not.toBeInTheDocument(),
  );
});
