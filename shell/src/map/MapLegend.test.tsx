// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import type { MapConfig } from "../api/types";
import { MapLegend } from "./MapLegend";

test("lists visible non-deck layer titles", () => {
  const layers: MapConfig["layers"] = [
    { id: "a", title: "Communes", visible: true, kind: "vector", tilesUrl: "u", sourceLayer: "c" },
    { id: "b", title: "Cachée", visible: false, kind: "raster", tilesUrl: "u" },
  ];
  render(<MapLegend layers={layers} />);
  expect(screen.getByText("Communes")).toBeInTheDocument();
  expect(screen.queryByText("Cachée")).not.toBeInTheDocument();
});

test("lists visible deck layers in the legend", () => {
  const layers: MapConfig["layers"] = [
    { id: "heat", title: "Chaleur", visible: true, kind: "deck", deckType: "heatmap", dataUrl: "d" },
    { id: "off", title: "Cachée", visible: false, kind: "deck", deckType: "heatmap", dataUrl: "d" },
  ];
  render(<MapLegend layers={layers} />);
  expect(screen.getByText("Chaleur")).toBeInTheDocument();
  expect(screen.queryByText("Cachée")).not.toBeInTheDocument();
});
