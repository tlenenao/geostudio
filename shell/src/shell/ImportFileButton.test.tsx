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
  return new File(
    ['{"type":"FeatureCollection","features":[]}'],
    "villes.geojson",
    { type: "application/geo+json" },
  );
}

test("uploads a file and navigates to the created map once the job is done", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" })),
    http.put("https://minio.test/upload-1", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads", () => HttpResponse.json({ jobId: "job-1" })),
    http.get("https://core.test/uploads/job-1", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_abc", itemId: "42" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-42")).toBeInTheDocument());
});

test("shows the job's error message and lets the user retry", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-2", key: "t/def-broken.geojson" })),
    http.put("https://minio.test/upload-2", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads", () => HttpResponse.json({ jobId: "job-2" })),
    http.get("https://core.test/uploads/job-2", () =>
      HttpResponse.json({ status: "error", errorMessage: "JSON invalide", collectionId: null, itemId: null })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Casse");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByRole("alert")).toHaveTextContent("JSON invalide"));
  expect(screen.getByRole("button", { name: "Importer" })).toBeEnabled();
});

test("shows manual lat/lon selectors when a CSV's columns cannot be auto-detected", async () => {
  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  const csv = new File(["nom,valeur\nA,1\n"], "data.csv", { type: "text/csv" });
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), csv);

  await waitFor(() => expect(screen.getByLabelText("Colonne latitude")).toBeInTheDocument());
  expect(screen.getByLabelText("Colonne longitude")).toBeInTheDocument();
});

test("does not show manual lat/lon selectors when a CSV's columns are auto-detectable", async () => {
  render(<Harness><ImportFileButton /></Harness>);
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
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-3", key: "t/ghi-villes.gpkg" })),
    http.put("https://minio.test/upload-3", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads/inspect", () =>
      HttpResponse.json({ layers: [{ name: "villes", featureCount: 2, geometryType: "Point" }] })),
    http.post("https://core.test/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("villes");
      return HttpResponse.json({ jobId: "job-3" });
    }),
    http.get("https://core.test/uploads/job-3", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_x", itemId: "99" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByText("map-99")).toBeInTheDocument());
});

test("shows a layer picker for a multi-layer GeoPackage and imports the chosen layer", async () => {
  server.use(
    http.post("https://core.test/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-4", key: "t/jkl-multi.gpkg" })),
    http.put("https://minio.test/upload-4", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/uploads/inspect", () =>
      HttpResponse.json({
        layers: [
          { name: "villes", featureCount: 2, geometryType: "Point" },
          { name: "routes", featureCount: 5, geometryType: "LineString" },
        ],
      })),
    http.post("https://core.test/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      expect(body.layerName).toBe("routes");
      return HttpResponse.json({ jobId: "job-4" });
    }),
    http.get("https://core.test/uploads/job-4", () =>
      HttpResponse.json({ status: "done", errorMessage: null, collectionId: "ingest_y", itemId: "100" })),
  );

  render(<Harness><ImportFileButton /></Harness>);
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), gpkgFile("multi.gpkg"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Multi");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "routes");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-100")).toBeInTheDocument());
});
