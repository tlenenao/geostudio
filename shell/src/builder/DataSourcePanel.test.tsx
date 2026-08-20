// SPDX-License-Identifier: Apache-2.0
import { fireEvent, render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { DataSource } from "../api/types";
import { DataSourcePanel } from "./DataSourcePanel";

test("adds a data source", async () => {
  const onChange = vi.fn();
  render(<DataSourcePanel sources={[]} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une source" }));
  const next = onChange.mock.calls[0][0] as DataSource[];
  expect(next).toHaveLength(1);
  expect(next[0].type).toBe("features");
  expect(typeof next[0].id).toBe("string");
});

test("removes a data source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "parcs", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer parcs" }));
  expect(onChange).toHaveBeenCalledWith([]);
});

test("edits a source layer", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Collection de la source d1"), "parcs");
  const last = onChange.mock.calls.at(-1)![0] as DataSource[];
  expect(last[0].layer.endsWith("s")).toBe(true);
});

test("offers a statistics type option", () => {
  const sources: DataSource[] = [
    { id: "d1", type: "features", service: "featureserv", layer: "", query: {} },
  ];
  render(<DataSourcePanel sources={sources} onChange={vi.fn()} />);
  const typeSelect = screen.getByLabelText("Type de la source d1");
  expect(within(typeSelect).getByRole("option", { name: "Statistiques" })).toBeInTheDocument();
});

test("edits a statistics source's group-by and split", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  // onChange is a spy, so the controlled inputs stay frozen at "" — each
  // keystroke emits the single typed char (as with "edits a source layer").
  await userEvent.type(screen.getByLabelText("Grouper par (source d1)"), "r");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toBe("r");
  await userEvent.type(screen.getByLabelText("Séparer par (source d1)"), "a");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.split).toBe("a");
});

test("adds and configures a measure on a statistics source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter une mesure à d1" }));
  const afterAdd = (onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.measures as unknown[];
  expect(afterAdd).toHaveLength(1);
});

test("edits the default aggregation of a statistics source", async () => {
  const sources: DataSource[] = [
    {
      id: "d1",
      type: "statistics",
      service: "featureserv",
      layer: "villes",
      query: { groupBy: "region" },
    },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.selectOptions(screen.getByLabelText("Agrégation (source d1)"), "sum");
  const last = (onChange.mock.calls.at(-1)![0] as DataSource[])[0];
  expect(last.query.agg).toBe("sum");
  expect(last.query.groupBy).toBe("region");
});

test("promoting a features source calls onPromote and then shows it as shared", async () => {
  const onChange = vi.fn();
  const onPromote = vi.fn();
  const sources: DataSource[] = [
    { id: "s1", type: "features", service: "core", layer: "parcs", query: {} },
  ];
  const { rerender } = render(
    <DataSourcePanel
      sources={sources}
      onChange={onChange}
      onPromote={onPromote}
      promotingId={null}
    />,
  );

  await userEvent.click(screen.getByRole("button", { name: "Promouvoir en dataset partagé s1" }));
  expect(onPromote).toHaveBeenCalledWith("s1");

  rerender(
    <DataSourcePanel
      sources={[{ ...sources[0], datasetId: "ds-1" }]}
      onChange={onChange}
      onPromote={onPromote}
      promotingId={null}
    />,
  );
  expect(screen.getByText("Dataset partagé actif")).toBeInTheDocument();
  expect(
    screen.queryByRole("button", { name: "Promouvoir en dataset partagé s1" }),
  ).not.toBeInTheDocument();
});

test("a comma-separated group-by becomes a string array; a single field stays a string", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  const { rerender } = render(<DataSourcePanel sources={sources} onChange={onChange} />);
  fireEvent.change(screen.getByLabelText("Grouper par (source d1)"), {
    target: { value: "origin,destination" },
  });
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.groupBy).toEqual([
    "origin",
    "destination",
  ]);

  const withArray: DataSource[] = [
    { ...sources[0], query: { groupBy: ["origin", "destination"] } },
  ];
  rerender(<DataSourcePanel sources={withArray} onChange={onChange} />);
  expect(screen.getByLabelText("Grouper par (source d1)")).toHaveValue("origin,destination");
});

test("edits the histogram bin count on a statistics source", async () => {
  const sources: DataSource[] = [
    { id: "d1", type: "statistics", service: "featureserv", layer: "villes", query: {} },
  ];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Nombre de classes (source d1)"), "8");
  expect((onChange.mock.calls.at(-1)![0] as DataSource[])[0].query.bins).toBe(8);
});
