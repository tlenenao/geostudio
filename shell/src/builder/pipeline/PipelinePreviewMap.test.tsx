// SPDX-License-Identifier: Apache-2.0
import { render } from "@testing-library/react";
import { beforeEach, expect, test, vi } from "vitest";
import { mapInstances } from "../../test/MockMaplibreMap";
import { PipelinePreviewMap } from "./PipelinePreviewMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
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
