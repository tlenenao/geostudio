// SPDX-License-Identifier: Apache-2.0
// REV-250 : l'auto-cadrage D18 doit fonctionner quand le chunk `lazy()` de
// MapView est FROID (ref encore null quand les données arrivent). Dans
// MapEditorPage.test.tsx le chunk est déjà résolu par un test antérieur et le
// défaut (indicateur « déjà ajusté » posé avant que le ref existe) ne se
// manifeste jamais, corrigé ou non. Ce fichier-ci a son propre graphe de
// modules, et la factory du mock de MapView est bloquée sur une barrière :
// le chunk reste froid tant que le test ne la lève pas, quel que soit l'ordre
// d'exécution ou la charge machine.
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { act, render, screen, waitFor } from "@testing-library/react";
import * as ToastPrimitive from "@radix-ui/react-toast";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { beforeEach, expect, test, vi } from "vitest";
import type { Item, ItemClient, MapConfig } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { OWNER_PERMISSIONS } from "../auth/permissions";
import { ToastProvider } from "../ui/kit/ToastProvider";
import { mapInstances } from "../test/MockMaplibreMap";

const gate = vi.hoisted(() => {
  let release!: () => void;
  const promise = new Promise<void>((resolve) => {
    release = resolve;
  });
  return { promise, release };
});

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
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
// Barrière : l'import dynamique de MapView (le chunk lazy) ne se résout
// qu'après `gate.release()`.
vi.mock("../map/MapView", async (importOriginal) => {
  await gate.promise;
  return importOriginal();
});

const { MapEditorPage } = await import("./MapEditorPage");

const config: MapConfig = {
  basemap: { style: "https://demotiles.maplibre.org/style.json" },
  view: { center: [2.4, 46.6], zoom: 5 },
  layers: [{ id: "a", title: "Couche A", visible: true, kind: "feature", url: "u" }],
};

const ITEM: Item = {
  pk: "77",
  resourceType: "map",
  title: "Carte",
  abstract: "",
  owner: "alice",
  thumbnailUrl: null,
  date: "2026-01-01",
  configId: "cfg-77",
  isPublished: false,
  keywords: [],
  permissions: OWNER_PERMISSIONS,
  license: "",
  language: "fr",
  bbox: [1, 10, 3, 20],
};

beforeEach(() => {
  mapInstances.length = 0;
  // jsdom n'implémente pas matchMedia (piège n°10) : stub local au fichier.
  vi.stubGlobal(
    "matchMedia",
    vi.fn().mockReturnValue({
      matches: false,
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  );
  vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("not mocked in this test")));
});

test("auto-cadrage D18 : fonctionne quand le chunk lazy de MapView charge APRÈS les données (REV-250)", async () => {
  const getItem = vi.fn().mockResolvedValue(ITEM);
  const client: Partial<ItemClient> = {
    getItem,
    getMapConfig: vi.fn().mockResolvedValue(config),
    listLayerSources: vi.fn().mockResolvedValue([]),
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const router = createMemoryRouter([{ path: "/maps/:pk", element: <MapEditorPage pk="77" /> }], {
    initialEntries: ["/maps/77"],
  });
  render(
    <ToastPrimitive.Provider>
      <QueryClientProvider client={qc}>
        <ItemClientProvider client={client as ItemClient}>
          <ToastProvider>
            <RouterProvider router={router} />
          </ToastProvider>
        </ItemClientProvider>
      </QueryClientProvider>
      <ToastPrimitive.Viewport />
    </ToastPrimitive.Provider>,
  );

  // Données chargées (brouillon + item avec bbox) alors que le chunk MapView
  // est toujours bloqué sur la barrière : aucune carte n'existe encore.
  await screen.findAllByText("Couche A");
  await waitFor(() => expect(getItem).toHaveBeenCalled());
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 50));
  });
  expect(mapInstances).toHaveLength(0);

  await act(async () => gate.release());
  await waitFor(() => expect(mapInstances[0]).toBeDefined());
  mapInstances[0].fire("idle");
  await waitFor(() => expect(mapInstances[0]?.fitBoundsArgs).toHaveLength(1));
  expect(mapInstances[0].fitBoundsArgs[0]).toMatchObject({
    bounds: [
      [1, 10],
      [3, 20],
    ],
  });
});
