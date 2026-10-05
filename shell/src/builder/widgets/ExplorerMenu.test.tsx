// SPDX-License-Identifier: Apache-2.0
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, expect, test, vi } from "vitest";
import { ExplorerMenu } from "./ExplorerMenu";
import { ExplorerProvider, useExplorerTarget } from "../ExplorerContext";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import type { DataSource, ItemClient } from "../../api/types";
import { ApiError } from "../../api/ApiError";
import { expectTokenizedClasses } from "../../ui/kit/testUtils";

// REV-079 : `vi.spyOn` (au lieu de `vi.stubGlobal("URL", { ...URL, ... })`)
// laisse le constructeur `URL` intact — un `{ ...URL }` produit un objet
// simple, non constructible via `new`, qui restait installé pour tous les
// tests suivants du fichier faute de nettoyage.
afterEach(() => {
  vi.restoreAllMocks();
});

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
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "parcs",
    query: {},
  };
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
  const source: DataSource = {
    id: "s1",
    type: "features",
    service: "core",
    layer: "parcs",
    query: {},
  };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  for (const label of [
    "Exporter en CSV",
    "Exporter en XLSX",
    "Exporter en GEOJSON",
    "Exporter en GPKG",
  ]) {
    expect(screen.getByLabelText(label)).toBeInTheDocument();
  }
});

test("items sources without geometry only offer CSV/XLSX", async () => {
  const client = { exportDataSource: vi.fn() } as unknown as ItemClient;
  const source: DataSource = {
    id: "s1",
    type: "features",
    service: "core",
    layer: "parcs",
    query: {},
  };
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu
          datasetId="ds1"
          dataSourceId="s1"
          resolvedSource={source}
          hasGeometry={false}
        />
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
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "parcs",
    query: { groupBy: "region" },
  };
  const createObjectURL = vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:fake");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});

  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu
          datasetId="ds1"
          dataSourceId="s1"
          resolvedSource={source}
          hasGeometry={false}
        />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(exportDataSource).toHaveBeenCalledWith(source, "csv", expect.any(AbortSignal));
  expect(createObjectURL).toHaveBeenCalledWith(blob);
});

test("un export asynchrone (URL présignée) se télécharge par ancre, sans Blob", async () => {
  const exportDataSource = vi
    .fn()
    .mockResolvedValue({ url: "https://s3.test/f.csv", filename: "parcs.csv" });
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = {
    id: "s1",
    type: "features",
    service: "core",
    layer: "parcs",
    query: {},
  };
  const createObjectURL = vi.spyOn(URL, "createObjectURL");
  const click = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (
    this: HTMLAnchorElement,
  ) {
    expect(this.href).toBe("https://s3.test/f.csv");
    expect(this.download).toBe("parcs.csv");
  });
  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu
          datasetId="ds1"
          dataSourceId="s1"
          resolvedSource={source}
          hasGeometry={false}
        />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  await vi.waitFor(() => expect(click).toHaveBeenCalledTimes(1));
  expect(createObjectURL).not.toHaveBeenCalled();
});

test("a failed export surfaces an inline error message instead of failing silently", async () => {
  const exportDataSource = vi
    .fn()
    .mockRejectedValue(new Error("Request failed: 413 GET /collections/parcs/export/items"));
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "parcs",
    query: { groupBy: "region" },
  };

  const { container } = render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu
          datasetId="ds1"
          dataSourceId="s1"
          resolvedSource={source}
          hasGeometry={false}
        />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));

  expect(await screen.findByRole("alert")).toHaveTextContent(
    "Trop d'entités : affinez vos filtres.",
  );
  // SP-B12c : pas de couleur Tailwind de palette codée en dur — un token
  // --gs-* à la place.
  expectTokenizedClasses(container);
});

test("SP-B5 : une ApiError (status réel, requestBlob) mappe aussi le message d'accès refusé", async () => {
  const exportDataSource = vi.fn().mockRejectedValue(new ApiError(403, { detail: "forbidden" }));
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = {
    id: "s1",
    type: "statistics",
    service: "core",
    layer: "parcs",
    query: { groupBy: "region" },
  };

  render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu
          datasetId="ds1"
          dataSourceId="s1"
          resolvedSource={source}
          hasGeometry={false}
        />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));

  expect(await screen.findByRole("alert")).toHaveTextContent("Accès refusé.");
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

test("le démontage abandonne le sondage d'export sans afficher d'erreur", async () => {
  let signal: AbortSignal | undefined;
  const exportDataSource = vi.fn().mockImplementation(
    (_s: DataSource, _f: string, sig: AbortSignal) =>
      new Promise((_resolve, reject) => {
        signal = sig;
        sig.addEventListener("abort", () => reject(new DOMException("x", "AbortError")));
      }),
  );
  const client = { exportDataSource } as unknown as ItemClient;
  const source: DataSource = { id: "s1", type: "features", service: "core", layer: "p", query: {} };
  const { unmount } = render(
    <ItemClientProvider client={client}>
      <ExplorerProvider enabled>
        <ExplorerMenu datasetId="ds1" dataSourceId="s1" resolvedSource={source} hasGeometry />
      </ExplorerProvider>
    </ItemClientProvider>,
  );
  await userEvent.click(screen.getByLabelText("Explorer"));
  await userEvent.click(screen.getByLabelText("Exporter en CSV"));
  expect(signal?.aborted).toBe(false);
  unmount();
  expect(signal?.aborted).toBe(true);
});
