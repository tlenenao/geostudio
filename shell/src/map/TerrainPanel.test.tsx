// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { useState, type ReactNode } from "react";
import { http, HttpResponse } from "msw";
import { expect, test, vi } from "vitest";
import type { MapTerrainConfig } from "../api/types";
import { server } from "../test/msw/server";
import { createItemClient } from "../api/itemClient";
import { ItemClientProvider } from "../api/ItemClientProvider";
import { TerrainPanel } from "./TerrainPanel";

const CORE_URL = "https://core.test";

function Harness({ children }: { children: ReactNode }) {
  const queryClient = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client = createItemClient({ coreUrl: CORE_URL, getToken: () => "tok" });
  return (
    <QueryClientProvider client={queryClient}>
      <ItemClientProvider client={client}>{children}</ItemClientProvider>
    </QueryClientProvider>
  );
}

function setInstance(terrain3dEnabled: boolean) {
  server.use(
    http.get(`${CORE_URL}/instance`, () => HttpResponse.json({ readOnly: false, terrain3dEnabled })),
  );
}

// TerrainPanel is a controlled component (value/onChange). Most existing
// tests below only assert the onChange call args and pass `value` directly,
// so they don't need the rendered tree to reflect a state change. Render
// them with this simple helper, wrapped only in the providers now required
// by useItemClient()/useInstanceInfo() (added by this task).
function renderPanel(
  value: MapTerrainConfig | null,
  onChange: (next: MapTerrainConfig | null) => void,
  terrain3dEnabled = false,
) {
  setInstance(terrain3dEnabled);
  return render(
    <Harness>
      <TerrainPanel value={value} onChange={onChange} />
    </Harness>,
  );
}

// The three new tests below need the panel to actually re-render with an
// enabled `value` after checking "Activer le terrain 3D" (a real parent,
// e.g. MapEditorPage, would loop the value back in) — this stateful wrapper
// does the same, while still forwarding every change to the `onChange` spy
// so assertions on call args are unaffected.
function ControlledTerrainPanel({ onChange }: { onChange: (next: MapTerrainConfig | null) => void }) {
  const [value, setValue] = useState<MapTerrainConfig | null>(null);
  return (
    <TerrainPanel
      value={value}
      onChange={(next) => {
        setValue(next);
        onChange(next);
      }}
    />
  );
}

function renderControlled(onChange: (next: MapTerrainConfig | null) => void, terrain3dEnabled = true) {
  setInstance(terrain3dEnabled);
  return render(
    <Harness>
      <ControlledTerrainPanel onChange={onChange} />
    </Harness>,
  );
}

test("renders unchecked and hides fields when value is null", () => {
  renderPanel(null, vi.fn());
  expect(screen.getByLabelText("Activer le terrain 3D")).not.toBeChecked();
  expect(screen.queryByLabelText("URL de tuiles terrain")).not.toBeInTheDocument();
});

test("checking the box emits a default terrain config", async () => {
  const onChange = vi.fn();
  renderPanel(null, onChange);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "", encoding: "terrarium", exaggeration: 1 });
});

test("shows URL and exaggeration fields when a terrain config is provided", () => {
  const value: MapTerrainConfig = { tilesUrl: "https://example.test/dem/{z}/{x}/{y}.png", encoding: "terrarium", exaggeration: 2 };
  renderPanel(value, vi.fn());
  expect(screen.getByLabelText("Activer le terrain 3D")).toBeChecked();
  expect(screen.getByLabelText("URL de tuiles terrain")).toHaveValue("https://example.test/dem/{z}/{x}/{y}.png");
  expect(screen.getByLabelText("Exaggeration du terrain")).toHaveValue(2);
});

test("editing the URL field patches tilesUrl and preserves other fields", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "", encoding: "terrarium", exaggeration: 1 };
  renderPanel(value, onChange);
  await userEvent.type(screen.getByLabelText("URL de tuiles terrain"), "u");
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 1 });
});

test("editing the exaggeration field patches exaggeration", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 1 };
  renderPanel(value, onChange);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "2.5" } });
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 2.5 });
});

test("clearing the exaggeration field keeps the previous value instead of zeroing it", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 2 };
  renderPanel(value, onChange);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "" } });
  expect(onChange).not.toHaveBeenCalled();
});

test("a still-explicit zero exaggeration is accepted", () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 2 };
  renderPanel(value, onChange);
  fireEvent.change(screen.getByLabelText("Exaggeration du terrain"), { target: { value: "0" } });
  expect(onChange).toHaveBeenCalledWith({ tilesUrl: "u", encoding: "terrarium", exaggeration: 0 });
});

test("unchecking the box emits null", async () => {
  const onChange = vi.fn();
  const value: MapTerrainConfig = { tilesUrl: "u", encoding: "terrarium", exaggeration: 1 };
  renderPanel(value, onChange);
  await userEvent.click(screen.getByLabelText("Activer le terrain 3D"));
  expect(onChange).toHaveBeenCalledWith(null);
});

test("selecting a hosted DEM sets tilesUrl to the terrain3d proxy URL", async () => {
  server.use(
    http.get(`${CORE_URL}/items`, () =>
      HttpResponse.json({ items: [{ pk: "t-1", title: "Relief du massif" }], total: 1, page: 1, pageSize: 200 }),
    ),
  );
  const onChange = vi.fn();
  renderControlled(onChange, true);

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  const select = await screen.findByLabelText(/dem hébergé/i);
  await screen.findByRole("option", { name: "Relief du massif" });
  await userEvent.selectOptions(select, "t-1");

  await waitFor(() =>
    expect(onChange).toHaveBeenCalledWith({
      tilesUrl: `${CORE_URL}/terrain3d/t-1/tiles/{z}/{x}/{y}.png`,
      encoding: "terrarium",
      exaggeration: 1,
    }),
  );
});

test("external URL field remains usable and independent of the hosted picker", async () => {
  server.use(http.get(`${CORE_URL}/items`, () => HttpResponse.json({ items: [], total: 0, page: 1, pageSize: 200 })));
  const onChange = vi.fn();
  renderControlled(onChange, true);

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  // fireEvent.change (not userEvent.type): userEvent.type interprets "{"/"}"
  // as special key syntax, which would mangle this terrain-RGB URL's
  // literal {z}/{x}/{y} placeholders — same reason the pre-existing
  // "editing the URL field" test above only ever types a brace-free char.
  fireEvent.change(screen.getByLabelText(/url de tuiles terrain/i), {
    target: { value: "https://ext.example/{z}/{x}/{y}.png" },
  });
  expect(onChange).toHaveBeenLastCalledWith(
    expect.objectContaining({ tilesUrl: "https://ext.example/{z}/{x}/{y}.png" }),
  );
});

test("hosted DEM picker and upload button stay hidden when terrain3dEnabled is false", async () => {
  const onChange = vi.fn();
  renderControlled(onChange, false);

  await userEvent.click(screen.getByLabelText(/activer le terrain 3d/i));
  // External field still there (never gated)...
  expect(screen.getByLabelText(/url de tuiles terrain/i)).toBeInTheDocument();
  // ...but the hosted section is gone, so nothing hits the disabled /terrain3d/* routes.
  expect(screen.queryByLabelText(/dem hébergé/i)).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /nouveau dem/i })).not.toBeInTheDocument();
});
