// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { mapInstances } from "../test/MockMaplibreMap";
import { ItemClientProvider } from "../api/ItemClientProvider";
import type { ItemClient } from "../api/types";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { Map: MockMap, setWorkerUrl: () => {} };
});

const { CatalogSpatialFilter } = await import("./CatalogSpatialFilter");

beforeEach(() => {
  mapInstances.length = 0;
});

test("dessine un rectangle et remonte [minLon, minLat, maxLon, maxLat] à onChange", () => {
  const onChange = vi.fn();
  render(<CatalogSpatialFilter onChange={onChange} />);
  const map = mapInstances[0];

  act(() => {
    map.fire("mousedown", { lngLat: { lng: 1.0, lat: 45.0 } });
    map.fire("mousemove", { lngLat: { lng: 2.0, lat: 46.0 } });
    map.fire("mouseup", { lngLat: { lng: 2.0, lat: 46.0 } });
  });

  expect(onChange).toHaveBeenCalledWith([1.0, 45.0, 2.0, 46.0]);
});

test("normalise le rectangle quel que soit le sens du glisser (coin bas-droit vers haut-gauche)", () => {
  const onChange = vi.fn();
  render(<CatalogSpatialFilter onChange={onChange} />);
  const map = mapInstances[0];

  act(() => {
    map.fire("mousedown", { lngLat: { lng: 5.0, lat: 50.0 } });
    map.fire("mouseup", { lngLat: { lng: 1.0, lat: 45.0 } });
  });

  expect(onChange).toHaveBeenCalledWith([1.0, 45.0, 5.0, 50.0]);
});

test("le bouton Effacer réinitialise le rectangle et appelle onChange(null)", async () => {
  const onChange = vi.fn();
  render(<CatalogSpatialFilter onChange={onChange} />);
  const map = mapInstances[0];

  act(() => {
    map.fire("mousedown", { lngLat: { lng: 1.0, lat: 45.0 } });
    map.fire("mouseup", { lngLat: { lng: 2.0, lat: 46.0 } });
  });
  expect(onChange).toHaveBeenLastCalledWith([1.0, 45.0, 2.0, 46.0]);

  const clearButton = screen.getByRole("button", { name: "Effacer" });
  expect(clearButton).toBeEnabled();
  await userEvent.click(clearButton);

  expect(onChange).toHaveBeenLastCalledWith(null);
  expect(clearButton).toBeDisabled();
});

test("le bouton Effacer est désactivé tant qu'aucun rectangle n'est dessiné", () => {
  render(<CatalogSpatialFilter onChange={() => {}} />);
  expect(screen.getByRole("button", { name: "Effacer" })).toBeDisabled();
});

test("mousemove sans mousedown préalable n'appelle pas onChange", () => {
  const onChange = vi.fn();
  render(<CatalogSpatialFilter onChange={onChange} />);
  const map = mapInstances[0];

  act(() => {
    map.fire("mousemove", { lngLat: { lng: 2.0, lat: 46.0 } });
    map.fire("mouseup", { lngLat: { lng: 2.0, lat: 46.0 } });
  });

  expect(onChange).not.toHaveBeenCalled();
});

test("le rectangle suit la bascule d'ambiance (REV-285 e)", async () => {
  render(<CatalogSpatialFilter onChange={vi.fn()} />);
  const map = mapInstances[0];
  document.documentElement.style.setProperty("--gs-accent", "#010203");
  document.documentElement.dataset.theme = "dark";
  await new Promise((r) => setTimeout(r, 0));
  try {
    const fill = map.getLayer("catalog-spatial-filter-rect-fill") as unknown as {
      paint: { "fill-color": string };
    };
    expect(fill.paint["fill-color"]).toBe("#010203");
  } finally {
    document.documentElement.style.removeProperty("--gs-accent");
    delete document.documentElement.dataset.theme;
  }
});

test("AUD-122 : instance sans fond externe -> fond vierge, rectangle dessine conserve", async () => {
  const client = {
    getInstanceInfo: () => Promise.resolve({ externalBasemapsEnabled: false }),
  } as unknown as ItemClient;
  const setStyle = vi.fn();
  render(
    <ItemClientProvider client={client}>
      <CatalogSpatialFilter onChange={() => {}} />
    </ItemClientProvider>,
  );
  const map = mapInstances[0] as unknown as { opts: { style: string }; setStyle: typeof setStyle };
  map.setStyle = setStyle;
  expect(map.opts.style).toBe("https://demotiles.maplibre.org/style.json");
  await vi.waitFor(() => expect(setStyle).toHaveBeenCalledTimes(1));
  const [style, { transformStyle }] = setStyle.mock.calls[0];
  expect(style).toBe("/basemaps/blank.json");
  const rect = { type: "geojson", data: {} };
  const prev = {
    sources: { "catalog-spatial-filter-rect": rect, other: {} },
    layers: [
      { id: "bg" },
      { id: "catalog-spatial-filter-rect-fill" },
      { id: "catalog-spatial-filter-rect-outline" },
    ],
  };
  const next = transformStyle(prev, { version: 8, sources: {}, layers: [{ id: "background" }] });
  expect(next.sources).toEqual({ "catalog-spatial-filter-rect": rect });
  expect(next.layers.map((l: { id: string }) => l.id)).toEqual([
    "background",
    "catalog-spatial-filter-rect-fill",
    "catalog-spatial-filter-rect-outline",
  ]);
});
