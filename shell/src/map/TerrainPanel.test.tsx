// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { MapTerrainConfig } from "../api/types";
import { TerrainPanel } from "./TerrainPanel";

test("renders unchecked and hides fields when value is null", () => {
  render(<TerrainPanel value={null} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Activer le terrain 3D")).not.toBeChecked();
  expect(screen.queryByLabelText("URL de tuiles terrain")).not.toBeInTheDocument();
});

test("checking the box emits a default terrain config", async () => {
  const onChange = vi.fn();
  render(<TerrainPanel value={null} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "", encoding: "terrarium", exaggeration: 1 });
});

test("shows URL and exaggeration fields when a terrain config is provided", () => {
  const value: MapTerrainConfig = { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 2 };
  render(<TerrainPanel value={value} onChange={vi.fn()} />);
  expect(screen.getByLabelText("Activer le terrain 3D")).toBeChecked();
  expect(screen.getByLabelText("URL de tuiles terrain")).toHaveValue("https://example.test/dem/{z}/{x}/{y}.png");
  expect(screen.getByLabelText("Exaggeration du terrain")).toHaveValue(2);
});

test("editing the URL field patches tilesUrl and preserves other fields", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "", encoding: "terrarium", exaggeration: 1 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("URL de tuiles terrain"), "u");
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 1 });
});

test("editing the exaggeration field patches exaggeration", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 1 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "2.5" } });
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 2.5 });
});

test("clearing the exaggeration field keeps the previous value instead of zeroing it", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 2 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "" } });
  expect(onChange).not.toHaveBeenCalled();
});

test("a still-explicit zero exaggeration is accepted", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 2 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "0" } });
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 0 });
});

test("unchecking the box emits null", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 1 };
  render(<TerrainPanel value={value} onChange={onChange} />);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith(null);
});
