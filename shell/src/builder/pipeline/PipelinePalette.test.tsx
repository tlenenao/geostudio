// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { expect, test, vi } from "vitest";
import type { ItemClient, PipelineOpsCatalog } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelinePalette } from "./PipelinePalette";

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: {}, required: [] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: {}, required: [] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: {}, required: [] } },
};

function renderPalette(onAdd?: (op: string) => void) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { getPipelineOps: () => Promise.resolve(CATALOG) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePalette onAdd={onAdd} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
}

test("groups ops into three sections by kind", async () => {
  renderPalette();
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  expect(screen.getByRole("heading", { name: "Sources" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Transforms" })).toBeInTheDocument();
  expect(screen.getByRole("heading", { name: "Écritures" })).toBeInTheDocument();
});

test("each entry is draggable and sets the op id on dragstart", async () => {
  renderPalette();
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  const entry = screen.getByText("reader.collection").closest("[draggable]") as HTMLElement;
  expect(entry).toHaveAttribute("draggable", "true");
  const dataTransfer = {
    setData: (type: string, value: string) => {
      (dataTransfer as any)[type] = value;
    },
    effectAllowed: "",
  };
  fireEvent.dragStart(entry, { dataTransfer });
  expect((dataTransfer as any)["application/x-geostudio-pipeline-op"]).toBe("reader.collection");
});

// REV-060 : le drag-and-drop ne doit plus être l'unique voie d'ajout d'une
// étape (piège d'accessibilité clavier). Un clic sur l'entrée doit appeler
// `onAdd` avec l'id de l'op, sans jamais empêcher le drag existant.
test("clicking an entry calls onAdd with the op id (keyboard-accessible fallback)", async () => {
  const onAdd = vi.fn();
  renderPalette(onAdd);
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  fireEvent.click(screen.getByRole("button", { name: "reader.collection" }));
  expect(onAdd).toHaveBeenCalledWith("reader.collection");
});

test("entries render as native buttons (focusable, no onAdd required)", async () => {
  renderPalette();
  await waitFor(() => expect(screen.getByText("reader.collection")).toBeInTheDocument());
  const button = screen.getByRole("button", { name: "reader.collection" });
  expect(() => fireEvent.click(button)).not.toThrow();
});

test("op entries with a paramsSchema.description get it as a hover title", async () => {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const catalogWithDescription: PipelineOpsCatalog = {
    ...CATALOG,
    "reader.connector.postgres": {
      kind: "reader",
      paramsSchema: {
        properties: {},
        required: [],
        description: "Fonctionne également contre un cluster Amazon Redshift.",
      },
    },
  };
  const client: Partial<ItemClient> = {
    getPipelineOps: () => Promise.resolve(catalogWithDescription),
  };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelinePalette />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  await waitFor(() => expect(screen.getByText("reader.connector.postgres")).toBeInTheDocument());
  const entryWithDescription = screen
    .getByText("reader.connector.postgres")
    .closest("[draggable]") as HTMLElement;
  expect(entryWithDescription).toHaveAttribute(
    "title",
    "Fonctionne également contre un cluster Amazon Redshift.",
  );

  // Entry with no description (e.g. "reader.collection" from CATALOG) gets
  // no title attribute at all — never an empty string, which some screen
  // readers/tools would still surface as an (empty) tooltip.
  const entryWithoutDescription = screen
    .getByText("reader.collection")
    .closest("[draggable]") as HTMLElement;
  expect(entryWithoutDescription).not.toHaveAttribute("title");
});
