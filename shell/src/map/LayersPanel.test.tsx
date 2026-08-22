// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { LayersPanel } from "./LayersPanel";

const layers: MapLayer[] = [
  { id: "a", title: "A", visible: true, kind: "feature", url: "u1" },
  { id: "b", title: "B", visible: true, kind: "feature", url: "u2" },
];

function renderPanel(current: MapLayer[], onChange: (l: MapLayer[]) => void) {
  const client = {
    listLayerSources: vi.fn().mockResolvedValue([]),
    getCollectionSchema: vi.fn().mockResolvedValue({ fields: [] }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <LayersPanel layers={current} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("toggles a layer's visibility", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Masquer A" }));
  expect(onChange).toHaveBeenCalledWith([{ ...layers[0], visible: false }, layers[1]]);
});

test("removes a layer", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Retirer A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1]]);
});

test("moves a layer down", async () => {
  const onChange = vi.fn();
  renderPanel(layers, onChange);
  await userEvent.click(screen.getByRole("button", { name: "Descendre A" }));
  expect(onChange).toHaveBeenCalledWith([layers[1], layers[0]]);
});

test("the layers panel exposes the popup editor of each layer", async () => {
  const onChange = vi.fn();
  const vectorLayer: MapLayer = {
    id: "l1",
    title: "Communes",
    visible: true,
    kind: "vector",
    tilesUrl: "u",
    sourceLayer: "communes",
    collectionId: "communes",
  };
  renderPanel([vectorLayer], onChange);
  await userEvent.click(screen.getByRole("checkbox", { name: "Afficher les attributs au clic" }));
  expect(onChange).toHaveBeenCalledWith([expect.objectContaining({ popup: {} })]);
});

test("a raster layer has no popup editor", () => {
  const rasterLayer: MapLayer = {
    id: "r",
    title: "Fond",
    visible: true,
    kind: "raster",
    tilesUrl: "u",
  };
  renderPanel([rasterLayer], () => {});
  expect(
    screen.queryByRole("checkbox", { name: "Afficher les attributs au clic" }),
  ).not.toBeInTheDocument();
});
