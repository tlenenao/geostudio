import { render, screen } from "@testing-library/react";
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
  const sources: DataSource[] = [{ id: "d1", type: "features", service: "featureserv", layer: "parcs", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.click(screen.getByRole("button", { name: "Retirer parcs" }));
  expect(onChange).toHaveBeenCalledWith([]);
});

test("edits a source layer", async () => {
  const sources: DataSource[] = [{ id: "d1", type: "features", service: "featureserv", layer: "", query: {} }];
  const onChange = vi.fn();
  render(<DataSourcePanel sources={sources} onChange={onChange} />);
  await userEvent.type(screen.getByLabelText("Collection de la source d1"), "parcs");
  const last = onChange.mock.calls.at(-1)![0] as DataSource[];
  expect(last[0].layer.endsWith("s")).toBe(true);
});
