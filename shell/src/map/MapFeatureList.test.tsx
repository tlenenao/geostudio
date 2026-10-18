// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import type { Map as MapLibreMap } from "maplibre-gl";
import { expect, test, vi } from "vitest";
import { MapFeatureList } from "./MapFeatureList";

function fakeMap(features: unknown[]): MapLibreMap {
  return {
    getCenter: () => ({ lng: 2, lat: 46 }),
    queryRenderedFeatures: () => features,
  } as unknown as MapLibreMap;
}

const feat = (id: number, name: string, layer = "villes") => ({
  id,
  layer: { id: layer },
  properties: { nom: name },
  geometry: { type: "Point", coordinates: [3, 47] },
});

test("AUD-114 : liste des entités de la vue, ouverture du popup au clavier", async () => {
  const onSelect = vi.fn();
  const map = fakeMap([
    feat(1, "Tulle"),
    feat(1, "Tulle", "villes__outline"), // sous-couche : dédoublonnée
    feat(2, "Brive"),
    feat(3, "Ailleurs", "autre"), // couche sans popup : ignorée
    { id: 9, layer: { id: "villes" }, properties: { point_count: 4 }, geometry: null },
  ]);
  render(<MapFeatureList map={map} popupLayerIds={["villes"]} onSelect={onSelect} />);
  const toggle = screen.getByRole("button", { name: "Entités de la vue" });
  expect(toggle).toHaveAttribute("aria-expanded", "false");
  toggle.focus();
  await userEvent.keyboard("{Enter}");
  expect(screen.getAllByRole("listitem")).toHaveLength(2);
  await userEvent.click(screen.getByRole("button", { name: "Brive" }));
  expect(onSelect).toHaveBeenCalledWith(
    expect.objectContaining({ layerId: "villes", id: 2, lngLat: { lng: 3, lat: 47 } }),
  );
});

test("vue sans entité : message explicite", async () => {
  render(<MapFeatureList map={fakeMap([])} popupLayerIds={["villes"]} onSelect={vi.fn()} />);
  await userEvent.click(screen.getByRole("button", { name: "Entités de la vue" }));
  expect(screen.getByText("Aucune entité visible dans la vue.")).toBeInTheDocument();
});
