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
