// SPDX-License-Identifier: Apache-2.0
import { act, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, expect, test, vi } from "vitest";
import { mapInstances } from "../test/MockMaplibreMap";

vi.mock("maplibre-gl", async () => {
  const { MockMap } = await import("../test/MockMaplibreMap");
  return { default: { Map: MockMap } };
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
