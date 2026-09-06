// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import type { ItemClient, LayerSource, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayerPicker } from "./LayerPicker";

afterEach(() => {
  vi.unstubAllGlobals();
});

const sources: LayerSource[] = [
  {
    id: "communes",
    title: "Communes",
    service: "core",
    kind: "vector",
    tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "communes",
    collectionId: "communes",
    geometryKind: "polygon",
    pkColumn: "id",
  },
  {
    id: "public.parcs",
    title: "Parcs",
    service: "core",
    kind: "feature",
    url: "https://core.test/collections/public.parcs/items",
    featureCount: 128,
  },
  {
    id: "public.legacy",
    title: "Legacy",
    service: "core",
    kind: "feature",
    url: "https://core.test/collections/public.legacy/items",
    featureCount: null,
  },
  {
    id: "ext-ortho",
    title: "Orthophoto (WMS)",
    service: "external",
    kind: "raster",
    tilesUrl: "https://ows.example.com/wms?...&bbox={bbox-epsg-3857}",
  },
  {
    id: "t1",
    title: "Ville hébergée",
    service: "tileset3d",
    kind: "tiles3d",
    url: "https://core.test/tileset3d/t1/tileset.json",
  },
];

function renderPicker(onAdd: (l: MapLayer) => void) {
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("lists sources and emits a vector MapLayer on click", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "vector",
    title: "Communes",
    visible: true,
    tilesUrl: "https://core.test/collections/communes/tiles/{z}/{x}/{y}.mvt",
    sourceLayer: "communes",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("adding a collection produces a tiled layer bound to it", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({
      kind: "vector",
      collectionId: "communes",
      geometryKind: "polygon",
      pkColumn: "id",
    }),
  );
});

test("emits a feature MapLayer for a core source", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.click(await screen.findByRole("button", { name: /Parcs/ }));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Parcs",
    visible: true,
    url: "https://core.test/collections/public.parcs/items",
  });
});

test("emits a raster MapLayer for an external source", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.click(await screen.findByRole("button", { name: /Orthophoto \(WMS\)/ }));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "raster",
    title: "Orthophoto (WMS)",
    visible: true,
    tilesUrl: "https://ows.example.com/wms?...&bbox={bbox-epsg-3857}",
  });
});

test("clicking a hosted tileset3d source emits a tiles3d MapLayer with its proxy url", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Ville hébergée/ });
  await userEvent.click(btn);
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "tiles3d",
    url: "https://core.test/tileset3d/t1/tileset.json",
    visible: true,
  });
});

test("gives each added layer a distinct id", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const btn = await screen.findByRole("button", { name: /Communes/ });
  await userEvent.click(btn);
  await userEvent.click(btn);
  const id1 = (onAdd.mock.calls[0][0] as MapLayer).id;
  const id2 = (onAdd.mock.calls[1][0] as MapLayer).id;
  expect(id1).not.toBe(id2);
});

test("shows a feature-count badge for a core source with a known count", async () => {
  renderPicker(vi.fn());
  const item = (await screen.findByRole("button", { name: /Parcs/ })).closest("li")!;
  expect(item).toHaveTextContent("128 entités");
});

test("shows no feature-count badge for a tiled vector source or an unknown count", async () => {
  renderPicker(vi.fn());
  const communesItem = (await screen.findByRole("button", { name: /Communes/ })).closest("li")!;
  expect(communesItem).not.toHaveTextContent(/entités/);
  const legacyItem = (await screen.findByRole("button", { name: /Legacy/ })).closest("li")!;
  expect(legacyItem).not.toHaveTextContent(/entités/);
});

test("has a search field that calls listLayerSources with q", async () => {
  const onAdd = vi.fn();
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await screen.findByRole("button", { name: /Communes/ });
  const search = screen.getByRole("searchbox", { name: /rechercher/i });
  await userEvent.type(search, "commun");
  await waitFor(() => {
    expect(client.listLayerSources).toHaveBeenLastCalledWith({ q: "commun" });
  });
});

test("adds a tiles3d layer from the manual URL form", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  await userEvent.type(
    screen.getByLabelText("URL du tileset.json"),
    "https://example.test/tileset.json",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(onAdd).toHaveBeenCalledTimes(1);
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "tiles3d",
    title: "Bâtiments",
    visible: true,
    url: "https://example.test/tileset.json",
  });
  expect(typeof layer.id).toBe("string");
  expect(layer.id.length).toBeGreaterThan(0);
});

test("ajoute une couche deck.gl (heatmap) par URL (GAP-36)", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre de la visualisation"), "Densité");
  await userEvent.selectOptions(screen.getByLabelText("Type de visualisation"), "heatmap");
  await userEvent.type(
    screen.getByLabelText("URL des données (GeoJSON)"),
    "https://d/points.geojson",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la visualisation" }));
  expect(onAdd).toHaveBeenCalledWith(
    expect.objectContaining({
      kind: "deck",
      deckType: "heatmap",
      dataUrl: "https://d/points.geojson",
      title: "Densité",
    }),
  );
});

test("disables the deck.gl add button until title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter la visualisation" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre de la visualisation"), "Densité");
  expect(button).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText("URL des données (GeoJSON)"),
    "https://d/points.geojson",
  );
  expect(button).toBeEnabled();
});

test("disables the tiles3d add button until both title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter le tileset 3D" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre du tileset 3D"), "Bâtiments");
  expect(button).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText("URL du tileset.json"),
    "https://example.test/tileset.json",
  );
  expect(button).toBeEnabled();
});

test("clears the tiles3d form after adding", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const titleInput = screen.getByLabelText("Titre du tileset 3D") as HTMLInputElement;
  const urlInput = screen.getByLabelText("URL du tileset.json") as HTMLInputElement;
  await userEvent.type(titleInput, "Bâtiments");
  await userEvent.type(urlInput, "https://example.test/tileset.json");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le tileset 3D" }));
  expect(titleInput.value).toBe("");
  expect(urlInput.value).toBe("");
});

test("adds a feature layer from the manual GeoJSON URL form, with renderAs detected from its geometry", async () => {
  const onAdd = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
    ],
  };
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => fc }));
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Points d'intérêt");
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/poi.geojson",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Points d'intérêt",
    visible: true,
    url: "https://external.test/poi.geojson",
    renderAs: "circle",
  });
});

test("adds the layer even when the GeoJSON probe fails, without a renderAs, and shows an inline warning", async () => {
  const onAdd = vi.fn();
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("CORS")));
  renderPicker(onAdd);
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Zones");
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/zones.geojson",
  );
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  const layer = onAdd.mock.calls[0][0] as MapLayer;
  expect(layer).toMatchObject({
    kind: "feature",
    title: "Zones",
    url: "https://external.test/zones.geojson",
  });
  expect(layer).not.toHaveProperty("renderAs");
  expect(screen.getByRole("alert")).toHaveTextContent(/n'a pas pu être vérifié/);
});

test("disables the GeoJSON URL add button until both title and URL are filled", async () => {
  const onAdd = vi.fn();
  renderPicker(onAdd);
  const button = screen.getByRole("button", { name: "Ajouter la couche" });
  expect(button).toBeDisabled();
  await userEvent.type(screen.getByLabelText("Titre de la couche GeoJSON"), "Zones");
  expect(button).toBeDisabled();
  await userEvent.type(
    screen.getByLabelText("URL du GeoJSON"),
    "https://external.test/zones.geojson",
  );
  expect(button).toBeEnabled();
});

test("clears the GeoJSON URL form after adding and primes the introspection cache for that URL", async () => {
  const onAdd = vi.fn();
  const fc = {
    type: "FeatureCollection",
    features: [
      { type: "Feature", properties: {}, geometry: { type: "Point", coordinates: [1, 2] } },
    ],
  };
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => fc });
  vi.stubGlobal("fetch", fetchMock);
  const client = { listLayerSources: vi.fn().mockResolvedValue(sources) } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayerPicker onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  const titleInput = screen.getByLabelText("Titre de la couche GeoJSON") as HTMLInputElement;
  const urlInput = screen.getByLabelText("URL du GeoJSON") as HTMLInputElement;
  await userEvent.type(titleInput, "Points");
  await userEvent.type(urlInput, "https://external.test/points.geojson");
  await userEvent.click(screen.getByRole("button", { name: "Ajouter la couche" }));
  await waitFor(() => expect(onAdd).toHaveBeenCalledTimes(1));
  expect(titleInput.value).toBe("");
  expect(urlInput.value).toBe("");
  expect(fetchMock).toHaveBeenCalledTimes(1);
  expect(qc.getQueryData(["feature-geojson", "https://external.test/points.geojson"])).toEqual(fc);
});
