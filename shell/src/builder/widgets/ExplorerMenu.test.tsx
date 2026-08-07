// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import { ExplorerMenu } from "./ExplorerMenu";
import { ExplorerProvider, useExplorerTarget } from "../ExplorerContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { DataSource, ItemClient } from "../../api/types";

function TargetProbe() {
  const target = useExplorerTarget();
  return <p>target:{target ? `${target.datasetId}/${target.dataSourceId}` : "none"}</p>;
}

test("renders nothing when the explorer is disabled", () => {
  render(
    <ExplorerProvider enabled={false}>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("renders nothing when there is no datasetId", () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId={undefined} dataSourceId="src1" />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Explorer")).not.toBeInTheDocument();
});

test("clicking the button then the menu item opens the explorer with the right target", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
      <TargetProbe />
    </ExplorerProvider>,
  );
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.getByText("target:ds1/src1")).toBeInTheDocument();
});

test("the menu closes again after selecting the item", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="src1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Voir les entités"));
  expect(screen.queryByLabelText("Voir les entités")).not.toBeInTheDocument();
});

test("aggregate sources only offer CSV/XLSX", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.getByLabelText("Exporter en XLSX")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});

test("items sources with geometry offer all four formats", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  for (const label of ["Exporter en CSV", "Exporter en XLSX", "Exporter en GEOJSON", "Exporter en GPKG"]) {
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  }
});

test("items sources without geometry only offer CSV/XLSX", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "parcs", query: {} };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry={false} />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.getByLabelText("Exporter en CSV")).toBeInTheDocument();
  expect(screen.queryByLabelText("Exporter en GEOJSON")).not.toBeInTheDocument();
});

test("clicking an export format calls exportDataSource and triggers a download", async () => {
  const blob = new Blob(["a,b\n1,2\n"], { type: "text/csv" });
  const exportDataSource = vi.fn().mockResolvedValue({ blob, filename: "parcs.csv" });
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: { groupBy: "region" } };
  const createObjectURL = vi.fn().mockReturnValue("blob:fake");
  const revokeObjectURL = vi.fn();
  vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry={false} />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(source, "csv");
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("a failed export surfaces an inline error message instead of failing silently", async () => {
  const exportDataSource = vi.fn().mockRejectedValue(new Error("Request failed: 413 GET /collections/parcs/export/items"));
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "statistics", service: "core", layer: "parcs", query: { groupBy: "region" } };

  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry={false} />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));

  expect(await screen.findByRole("alert")).toHaveTextContent("413");
});

test("no export entries when resolvedSource is absent (backward compatible with existing callers)", async () => {
  render(
    <ExplorerProvider enabled>
      <ExplorerMenu datasetId="ds1" dataSourceId="s1" />
    </ExplorerProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  expect(screen.queryByLabelText(/^Exporter en/)).not.toBeInTheDocument();
});
