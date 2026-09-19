// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { mapInstances } from "../../test/MockMaplibreMap";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});

beforeEach(() => {
  mapInstances.length = 0;
});

test("adds a geojson source built from the rows carrying a geometry", () => {
  render(
    <PipelinePreviewMap
      rows={[
        { id: 1, geometry: { type: "Point", coordinates: [3.0, 45.0] } },
        { id: 2, geometry: null },
      ]}
    />,
  );
  const map = mapInstances[0];
  const source = map.getSource("pipeline-preview") as { spec: { data: GeoJSON.FeatureCollection } };
  expect(source.spec.data.features).toHaveLength(1); // the null-geometry row is excluded
  expect(source.spec.data.features[0].geometry).toEqual({
    type: "Point",
    coordinates: [3.0, 45.0],
  });
});

test("fits the map to the bounds of the rendered features", () => {
  render(
    <PipelinePreviewMap
      rows={[
        { id: 1, geometry: { type: "Point", coordinates: [1.0, 10.0] } },
        { id: 2, geometry: { type: "Point", coordinates: [3.0, 20.0] } },
      ]}
    />,
  );
  const map = mapInstances[0];
  expect(map.fitBoundsArgs).toHaveLength(1);
  expect(map.fitBoundsArgs[0]).toEqual({
    bounds: [
      [1.0, 10.0],
      [3.0, 20.0],
    ],
    opts: { padding: 20, maxZoom: 16 },
  });
});

test("does not call fitBounds when there are no geometries to show", () => {
  render(<PipelinePreviewMap rows={[{ id: 1, geometry: null }]} />);
  expect(mapInstances[0].fitBoundsArgs).toHaveLength(0);
});

test("rebuilds the map when the rows prop changes (different selected node)", () => {
  const { rerender } = render(
    <PipelinePreviewMap rows={[{ id: 1, geometry: { type: "Point", coordinates: [1.0, 1.0] } }]} />,
  );
  expect(mapInstances).toHaveLength(1);
  rerender(
    <PipelinePreviewMap rows={[{ id: 2, geometry: { type: "Point", coordinates: [9.0, 9.0] } }]} />,
  );
  expect(mapInstances).toHaveLength(2); // a fresh map, not the stale one
  const latestMap = mapInstances[1];
  const source = latestMap.getSource("pipeline-preview") as {
    spec: { data: GeoJSON.FeatureCollection };
  };
  expect(source.spec.data.features[0].geometry).toEqual({ type: "Point", coordinates: [9.0, 9.0] });
});

test("uses a distinct fill color for polygons, line color for lines, and circle color for points", () => {
  render(
    <PipelinePreviewMap rows={[{ id: 1, geometry: { type: "Point", coordinates: [1, 1] } }]} />,
  );
  const map = mapInstances[0];
  const fillLayer = map.getLayer("pipeline-preview-fill") as unknown as {
    paint: { "fill-color": string };
  };
  const lineLayer = map.getLayer("pipeline-preview-line") as unknown as {
    paint: { "line-color": string };
  };
  const circleLayer = map.getLayer("pipeline-preview-circle") as unknown as {
    paint: { "circle-color": string };
  };
  expect(fillLayer.paint["fill-color"]).not.toBe(lineLayer.paint["line-color"]);
  expect(lineLayer.paint["line-color"]).not.toBe(circleLayer.paint["circle-color"]);
});

test("renders a legend swatch only for geometry kinds actually present in rows", () => {
  render(
    <PipelinePreviewMap rows={[{ id: 1, geometry: { type: "Point", coordinates: [1, 1] } }]} />,
  );
  expect(screen.getByText("Point")).toBeInTheDocument();
  expect(screen.queryByText("Polygone")).not.toBeInTheDocument();
  expect(screen.queryByText("Ligne")).not.toBeInTheDocument();
});
