// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes, useParams } from "react-router-dom";
import type { ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { vi } from "vitest";
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
            <Route path="/admin/collections" element={<div>collections-probe</div>} />
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

test("GAP-29 : GeoParquet géo-référencé (fields=null) démarre le job sans étape de géométrie", async () => {
  // Correctif d'un test SP-56 dont la prémisse ("aucune inspection") est
  // invalidée par ce même chantier (GAP-29/Task 11-12) : le cœur inspecte
  // désormais TOUJOURS un .parquet (POST /uploads/inspect) pour distinguer,
  // via une sentinelle fields=null, un GeoParquet déjà géo-référencé (sniff
  // GDAL, aucune étape de géométrie à montrer) d'un Parquet tabulaire ordi-
  // naire (fields=[...], passe par le sélecteur de géométrie comme les
  // autres formats tabulaires). "Aucun appel d'inspection" n'a jamais été
  // la garantie voulue ; "aucune étape de géométrie affichée" l'est.
  let inspectCalled = false;
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-8", key: "t/vwx-villes.parquet" }),
    ),
    http.put("https://minio.test/upload-8", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () => {
      inspectCalled = true;
      return HttpResponse.json({ layers: [], fields: null });
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
  expect(inspectCalled).toBe(true);
  expect(screen.queryByLabelText("Aucune géométrie")).not.toBeInTheDocument();
});

function jsonlFile(name = "villes.jsonl") {
  return new File(['{"nom":"a","wkt_col":"POINT(1 2)"}\n'], name, {
    type: "application/jsonl",
  });
}

test("GAP-29 : selecting-geometry propose lat/lon, WKT et aucune géométrie ; mode « aucune » envoie geometryMode=none", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-10", key: "t/gap29-villes.jsonl" }),
    ),
    http.put("https://minio.test/upload-10", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({ layers: [], fields: ["nom", "wkt_col"] }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as {
        geometryMode?: string;
        latField?: string;
        lonField?: string;
        wktField?: string;
      };
      expect(body.geometryMode).toBe("none");
      expect(body.latField).toBeUndefined();
      expect(body.lonField).toBeUndefined();
      expect(body.wktField).toBeUndefined();
      return HttpResponse.json({ jobId: "job-10" });
    }),
    http.get("https://core.test/v1/uploads/job-10", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_none",
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
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), jsonlFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes JSONL");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Aucune géométrie")).toBeInTheDocument());
  expect(screen.getByLabelText("Colonnes latitude/longitude")).toBeInTheDocument();
  expect(screen.getByLabelText("Colonne WKT unique")).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Aucune géométrie"));
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  // GAP-29 : job "done" avec itemId=null (collection sans géométrie, pas de
  // Map associée) — poll() navigue vers /admin/collections, pas /maps/{id}.
  await waitFor(() => expect(screen.getByText("collections-probe")).toBeInTheDocument());
});

test("GAP-29 : selecting-geometry en mode WKT envoie geometryMode=wkt et wktField", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-14", key: "t/gap29-wkt.jsonl" }),
    ),
    http.put("https://minio.test/upload-14", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", () =>
      HttpResponse.json({ layers: [], fields: ["nom", "wkt_col"] }),
    ),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as {
        geometryMode?: string;
        wktField?: string;
        latField?: string;
      };
      expect(body.geometryMode).toBe("wkt");
      expect(body.wktField).toBe("wkt_col");
      expect(body.latField).toBeUndefined();
      return HttpResponse.json({ jobId: "job-14" });
    }),
    http.get("https://core.test/v1/uploads/job-14", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_wkt",
        itemId: "107",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), jsonlFile("wkt.jsonl"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes WKT");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Colonne WKT unique")).toBeInTheDocument());
  await userEvent.click(screen.getByLabelText("Colonne WKT unique"));
  await userEvent.selectOptions(screen.getByLabelText("Colonne WKT"), "wkt_col");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-107")).toBeInTheDocument());
});

test("GAP-29 : XLSX multi-feuilles inspecte spécifiquement la feuille choisie (2 appels distincts)", async () => {
  const inspectCalls: Array<{ layerName?: string }> = [];
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-12", key: "t/gap29-multi.xlsx" }),
    ),
    http.put("https://minio.test/upload-12", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      inspectCalls.push(body);
      if (body.layerName) {
        return HttpResponse.json({ layers: [], fields: ["lat", "lon"] });
      }
      return HttpResponse.json({
        layers: [
          { name: "Feuil1", featureCount: 3, geometryType: "Tabular" },
          { name: "Feuil2", featureCount: 5, geometryType: "Tabular" },
        ],
        fields: null,
      });
    }),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string; latField?: string };
      expect(body.layerName).toBe("Feuil1");
      expect(body.latField).toBeUndefined();
      return HttpResponse.json({ jobId: "job-12" });
    }),
    http.get("https://core.test/v1/uploads/job-12", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_multi_xlsx",
        itemId: "105",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), xlsxFile("multi.xlsx"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Multi XLSX");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "Feuil1");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-105")).toBeInTheDocument());
  expect(inspectCalls).toHaveLength(2);
  expect(inspectCalls[0]?.layerName).toBeUndefined();
  expect(inspectCalls[1]?.layerName).toBe("Feuil1");
});

test("GAP-29 : XLSX multi-feuilles sans lat/lon détectables sur la feuille choisie ouvre selecting-geometry", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-13", key: "t/gap29-multi2.xlsx" }),
    ),
    http.put("https://minio.test/upload-13", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads/inspect", async ({ request }) => {
      const body = (await request.json()) as { layerName?: string };
      if (body.layerName === "Feuil2") {
        return HttpResponse.json({ layers: [], fields: ["nom", "wkt_col"] });
      }
      return HttpResponse.json({
        layers: [
          { name: "Feuil1", featureCount: 3, geometryType: "Tabular" },
          { name: "Feuil2", featureCount: 5, geometryType: "Tabular" },
        ],
        fields: null,
      });
    }),
    http.post("https://core.test/v1/uploads", async ({ request }) => {
      const body = (await request.json()) as {
        layerName?: string;
        wktField?: string;
        geometryMode?: string;
      };
      expect(body.layerName).toBe("Feuil2");
      expect(body.wktField).toBe("wkt_col");
      expect(body.geometryMode).toBe("wkt");
      return HttpResponse.json({ jobId: "job-13" });
    }),
    http.get("https://core.test/v1/uploads/job-13", () =>
      HttpResponse.json({
        status: "done",
        errorMessage: null,
        collectionId: "ingest_multi_xlsx2",
        itemId: "106",
      }),
    ),
  );

  render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), xlsxFile("multi2.xlsx"));
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Multi XLSX 2");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByLabelText("Couche à importer")).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("Couche à importer"), "Feuil2");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByLabelText("Colonne WKT unique")).toBeInTheDocument());
  await userEvent.click(screen.getByLabelText("Colonne WKT unique"));
  await userEvent.selectOptions(screen.getByLabelText("Colonne WKT"), "wkt_col");
  await userEvent.click(screen.getByRole("button", { name: "Continuer" }));

  await waitFor(() => expect(screen.getByText("map-106")).toBeInTheDocument());
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

test("REV-087 : Échap/Annuler n'abandonnent pas un import en vol (busy)", async () => {
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({
        uploadUrl: "https://minio.test/upload-9",
        key: "t/rev87-villes.geojson",
      }),
    ),
    http.put("https://minio.test/upload-9", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-9" })),
    http.get("https://core.test/v1/uploads/job-9", () =>
      HttpResponse.json({
        status: "pending",
        errorMessage: null,
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
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes REV-087");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(screen.getByRole("button", { name: "Annuler" })).toBeDisabled());
  await userEvent.keyboard("{Escape}");
  expect(screen.getByRole("dialog")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Annuler" }));
  expect(screen.getByRole("dialog")).toBeInTheDocument();
});

test("does not poll again or update state after the drawer is unmounted mid-import", async () => {
  let pollCalls = 0;
  server.use(
    http.post("https://core.test/v1/uploads/presign", () =>
      HttpResponse.json({ uploadUrl: "https://minio.test/upload-1", key: "t/abc-villes.geojson" }),
    ),
    http.put("https://minio.test/upload-1", () => new HttpResponse(null, { status: 200 })),
    http.post("https://core.test/v1/uploads", () => HttpResponse.json({ jobId: "job-1" })),
    http.get("https://core.test/v1/uploads/job-1", () => {
      pollCalls += 1;
      return HttpResponse.json({
        status: "pending",
        errorMessage: null,
        collectionId: null,
        itemId: null,
      });
    }),
  );

  const { unmount } = render(
    <Harness>
      <ImportFileButton />
    </Harness>,
  );
  await userEvent.click(screen.getByRole("button", { name: "Importer un fichier" }));
  await userEvent.upload(screen.getByLabelText("Fichier à importer"), geojsonFile());
  await userEvent.type(screen.getByLabelText("Titre de la collection"), "Villes");
  await userEvent.click(screen.getByRole("button", { name: "Importer" }));

  await waitFor(() => expect(pollCalls).toBeGreaterThanOrEqual(1));
  const errorSpy = vi.spyOn(console, "error").mockImplementation(() => {});
  const callsAtUnmount = pollCalls;
  unmount();
  await new Promise((r) => setTimeout(r, 2000));
  expect(pollCalls).toBe(callsAtUnmount);
  expect(errorSpy).not.toHaveBeenCalled();
  errorSpy.mockRestore();
});
