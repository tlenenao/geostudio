// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { ItemClient, MapLayer } from "../api/types";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { isHostedRasterUrl } from "./hostedCoreUrl";
import { RasterLayerForm } from "./RasterLayerForm";

const CORE = "https://core.test/v1";

function setup(onAdd: (l: MapLayer) => void) {
  const client = {
    getCoreUrl: () => CORE,
    listHostedRasterSources: vi.fn().mockResolvedValue([{ id: "r1", title: "Ortho" }]),
    getRasterInfo: vi.fn().mockResolvedValue({
      itemId: "r1",
      bands: [{ index: 1, min: 64, max: 4095, mean: 2000, std: 1 }],
    }),
  } as unknown as ItemClient;
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client}>
        <RasterLayerForm onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("ajoute une couche raster dont l'URL porte la rampe et l'étendue des stats", async () => {
  const onAdd = vi.fn();
  setup(onAdd);
  await screen.findByRole("option", { name: "Ortho" });
  await userEvent.selectOptions(screen.getByLabelText("Raster hébergé"), "r1");
  await userEvent.selectOptions(screen.getByLabelText("Rampe de couleurs"), "magma");
  // étendue préremplie depuis les stats de la bande 1
  await vi.waitFor(() => expect(screen.getByLabelText("Valeur maximale")).toHaveValue(4095));
  await userEvent.click(screen.getByRole("button", { name: "Ajouter le raster" }));
  const layer = onAdd.mock.calls[0][0] as Extract<MapLayer, { kind: "raster" }>;
  expect(layer.kind).toBe("raster");
  expect(layer.title).toBe("Ortho");
  expect(layer.tilesUrl).toBe(
    `${CORE}/raster/r1/tiles/{z}/{x}/{y}?rescale=64%2C4095&colormap_name=magma`,
  );
  expect(isHostedRasterUrl(layer.tilesUrl, CORE)).toBe(true);
});

test("le jeton n'est jamais attaché à une URL /raster/ d'une autre origine", () => {
  expect(isHostedRasterUrl("https://evil.test/v1/raster/r1/tiles/0/0/0", CORE)).toBe(false);
  expect(isHostedRasterUrl("https://core.test/v1/collections/x", CORE)).toBe(false);
});
