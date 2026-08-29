// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import type { ItemClient, MapConfig } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { mapInstances } from "../test/MockMaplibreMap";
import { overlayInstances } from "../test/MockDeckgl";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
});
vi.mock("@deck.gl/mapbox", async () => {
  const { MockMapboxOverlay } = await import("../test/MockDeckgl");
  return { MapboxOverlay: MockMapboxOverlay };
});
vi.mock("@deck.gl/aggregation-layers", async () => {
  const { HeatmapLayer, HexagonLayer } = await import("../test/MockDeckgl");
  return { HeatmapLayer, HexagonLayer };
});
vi.mock("@deck.gl/layers", async () => {
  const { ColumnLayer } = await import("../test/MockDeckgl");
  return { ColumnLayer };
});
vi.mock("@deck.gl/geo-layers", async () => {
  const { Tile3DLayer } = await import("../test/MockDeckgl");
  return { Tile3DLayer };
});
vi.mock("@loaders.gl/3d-tiles", async () => {
  const { Tiles3DLoader } = await import("../test/MockLoadersGl");
  return { Tiles3DLoader };
});

const { MapEditorPage } = await import("./MapEditorPage");

beforeEach(() => {
  mapInstances.length = 0;
  overlayInstances.length = 0;
  // La couche "feature" de `config` (ci-dessous) déclenche désormais un
  // fetch de son `url` au montage de LayersPanel (Task 2, SP-28) — MSW
  // (onUnhandledRequest: "error") ferait échouer ces tests sans ce repli.
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});

afterEach(() => {
  delete document.body.dataset.exportReady;
  vi.unstubAllGlobals();
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.4, 46.6], zoom: 5 },
  layers: [{ id: "a", title: "Couche A", visible: true, kind: "feature", url: "u" }],
};

function renderEditor(client: Partial<ItemClient>, initialEntries: string[] = ["/maps/77"]) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MemoryRouter initialEntries={initialEntries}>
          <MapEditorPage pk="77" />
        </MemoryRouter>
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("loads the config and saves edits", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Retirer Couche A" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const savedLayers = saveMapConfig.mock.calls[0][1].layers;
  expect(savedLayers).toEqual([]);
});

test("shows an error when loading fails", async () => {
  renderEditor({ getMapConfig: vi.fn().mockRejectedValue(new Error("boom")) });
  expect(await screen.findByRole("alert")).toHaveTextContent(/carte introuvable/i);
});

test("saving after only changing a layer keeps the previously loaded printLayout", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue({
      ...config,
      printLayout: { pageSize: "a3", orientation: "landscape" },
    }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await screen.findByText(/A3/i); // le panneau reflète bien le printLayout chargé
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const savedConfig = saveMapConfig.mock.calls[0][1];
  expect(savedConfig.printLayout).toEqual({ pageSize: "a3", orientation: "landscape" });
});

test("edits terrain and camera, then saves both", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");

  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  await userEvent.type(
    screen.getByLabelText("URL de tuiles terrain"),
    "https://example.test/dem/{{z}/{{x}/{{y}.png",
  );
  fireEvent.change(screen.getByLabelText("Inclinaison de la caméra"), { target: { value: "40" } });
  fireEvent.change(screen.getByLabelText("Orientation de la caméra"), { target: { value: "200" } });

  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.terrain).toEqual({
    tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png",
    encoding: "terrarium",
    exaggeration: 1,
  });
  expect(saved.view.pitch).toBe(40);
  expect(saved.view.bearing).toBe(200);
});

test("the camera reset button zeroes pitch and bearing in the saved view", async () => {
  const saveMapConfig = vi.fn().mockResolvedValue(undefined);
  renderEditor({
    getMapConfig: vi
      .fn()
      .mockResolvedValue({ ...config, view: { ...config.view, pitch: 40, bearing: 200 } }),
    saveMapConfig,
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Réinitialiser en 2D" }));
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  await waitFor(() => expect(saveMapConfig).toHaveBeenCalled());
  const saved = saveMapConfig.mock.calls[0][1];
  expect(saved.view.pitch).toBe(0);
  expect(saved.view.bearing).toBe(0);
});

test("surfaces a save failure", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    saveMapConfig: vi.fn().mockRejectedValue(new Error("nope")),
    listLayerSources: vi.fn().mockResolvedValue([]),
  });
  // Layer name appears in both LayersPanel and MapLegend; use findAllByText as sync point
  await screen.findAllByText("Couche A");
  await userEvent.click(screen.getByRole("button", { name: "Enregistrer" }));
  expect(await screen.findByText(/échec de l'enregistrement/i)).toBeInTheDocument();
});

test("exportRender=1 renders a nude chrome (no builder aside/save button) and marks the page export-ready once the map idles", async () => {
  renderEditor(
    {
      getMapConfig: vi.fn().mockResolvedValue({
        ...config,
        printLayout: {
          title: "Carte des communes",
          showLegend: true,
          cartouche: "GeoStudio © 2026",
        },
      }),
      listLayerSources: vi.fn().mockResolvedValue([]),
    },
    ["/maps/77?exportRender=1"],
  );
  // Builder chrome must be absent from the capture.
  expect(screen.queryByRole("button", { name: "Enregistrer" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Retirer Couche A" })).not.toBeInTheDocument();
  // PrintLayout overlays render from the loaded config.
  expect(await screen.findByText("Carte des communes")).toBeInTheDocument();
  expect(screen.getByText("Couche A")).toBeInTheDocument(); // showLegend
  expect(screen.getByText("GeoStudio © 2026")).toBeInTheDocument();
  // The map fires "idle" synchronously on mount in the MockMap harness — the
  // export-ready DOM signal (Task 6's contract) must follow. But mounting
  // the mocked MapLibre instance still happens inside MapView's effect, one
  // tick after this test's own render/findByText resolve — indexing
  // mapInstances[0] without waiting was a ~25% flake on this branch's merge
  // (I6 de la revue finale SP-25), not caused by SP-25 itself.
  await waitFor(() => expect(mapInstances[0]).toBeDefined());
  mapInstances[0].fire("idle");
  expect(document.body.getAttribute("data-export-ready")).toBe("true");
});

test("affiche le panneau d'historique", async () => {
  renderEditor({
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
    listConfigRevisions: vi.fn().mockResolvedValue([]),
  });
  expect(await screen.findByText("Historique")).toBeInTheDocument();
});
