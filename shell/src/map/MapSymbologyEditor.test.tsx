// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { MapSymbologyEditor } from "./MapSymbologyEditor";

test("no color field selected: shows the field picker only", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={["population", "region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByLabelText("Champ couleur")).toBeInTheDocument();
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();
});

test("theme-primary palette option is absent without a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(false);
});

test("theme-primary palette option is present with a theme", () => {
  render(
    <MapSymbologyEditor
      value={undefined}
      availableFields={[]}
      themeColors={{ primary: "#2563eb" }}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  const select = screen.getByLabelText("Palette") as HTMLSelectElement;
  expect(Array.from(select.options).some((o) => o.value === "theme-primary")).toBe(true);
});

test("classification method selector is hidden in categorical mode and shown in numeric mode", async () => {
  const onChange = vi.fn();
  const { rerender } = render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "region",
          mode: "categorical",
          palette: "categorical-a",
          domain: { kind: "categorical", values: [] },
          computedAt: "",
        },
      }}
      availableFields={["region"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.queryByLabelText("Méthode de classification")).not.toBeInTheDocument();

  rerender(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 1 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );
  expect(screen.getByLabelText("Méthode de classification")).toBeInTheDocument();
});

test("class count selector is hidden when the method is continuous", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 1 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.queryByLabelText("Nombre de classes")).not.toBeInTheDocument();
});

test("recompute button calls runStatistics and writes domain + computedAt via onChange", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 0, max: 100 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));

  expect(runStatistics).toHaveBeenCalled();
  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      color: expect.objectContaining({
        domain: { kind: "numeric", min: 0, max: 100 },
        computedAt: expect.any(String),
      }),
    }),
  );
});

test("recompute button for the size field calls runStatistics and writes size domain", async () => {
  const runStatistics = vi.fn().mockResolvedValue([{ id: "", properties: { min: 1, max: 9 } }]);
  const onChange = vi.fn();
  render(
    <MapSymbologyEditor
      value={{ size: { field: "montant", domain: { min: 0, max: 0 }, computedAt: "" } }}
      availableFields={["montant"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={onChange}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Recalculer la taille" }));

  expect(onChange).toHaveBeenCalledWith(
    expect.objectContaining({
      size: expect.objectContaining({ domain: { min: 1, max: 9 }, computedAt: expect.any(String) }),
    }),
  );
});

test("a failing recompute surfaces an error instead of hanging silently", async () => {
  const runStatistics = vi.fn().mockRejectedValue(new Error("boom"));
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          palette: "sequential-blue",
          domain: { kind: "numeric", min: 0, max: 0 },
          computedAt: "",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={runStatistics}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  await userEvent.click(screen.getByRole("button", { name: "Recalculer les classes" }));
  expect(await screen.findByRole("alert")).toHaveTextContent("boom");
});

test("computed breaks are shown as text", () => {
  render(
    <MapSymbologyEditor
      value={{
        color: {
          field: "pop",
          mode: "numeric",
          classification: { method: "quantile", classes: 2 },
          palette: "sequential-blue",
          domain: { kind: "numeric-classed", breaks: [0, 50, 100] },
          computedAt: "2026-08-23T10:00:00Z",
        },
      }}
      availableFields={["pop"]}
      themeColors={undefined}
      runStatistics={vi.fn()}
      sampleField={vi.fn()}
      onChange={vi.fn()}
    />,
  );
  expect(screen.getByText(/0.*50.*100/)).toBeInTheDocument();
});
