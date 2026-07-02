import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
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

const { MapEditorPage } = await import("./MapEditorPage");

beforeEach(() => {
  mapInstances.length = 0;
  overlayInstances.length = 0;
});

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.4, 46.6], zoom: 5 },
  layers: [{ id: "a", title: "Couche A", visible: true, kind: "feature", url: "u" }],
};

function renderEditor(client: Partial<ItemClient>) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <MapEditorPage pk="77" />
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
