// SPDX-License-Identifier: Apache-2.0
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { expect, test, vi } from "vitest";
import type { CollectionAdmin, ItemClient, PipelineNode, PipelineOpEntry } from "../../api/types";
import { ItemClientProvider } from "../../api/ItemClientProvider";
import { PipelineNodeInspector } from "./PipelineNodeInspector";

const COLLECTIONS: CollectionAdmin[] = [
  {
    id: "villes",
    title: "Villes",
    description: "",
    tableName: "villes",
    isPublic: true,
    editable: true,
    geometryType: null,
    srid: null,
    pkColumn: "id",
    permissions: { read: true, write: true, delete: true, share: true },
    featureCount: 10,
    owner: "alice",
    attachmentFields: [],
  },
];

function renderInspector(node: PipelineNode, opEntry: PipelineOpEntry, onChange = vi.fn()) {
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve(COLLECTIONS) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineNodeInspector node={node} opEntry={opEntry} errors={[]} onChange={onChange} />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  return { onChange };
}

test("a collection-id format field renders a CollectionParamSelect", async () => {
  const node: PipelineNode = {
    id: "r1",
    kind: "reader",
    op: "reader.collection",
    x: 0,
    y: 0,
    params: { collectionId: "" },
  };
  const opEntry: PipelineOpEntry = {
    kind: "reader",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  };
  const { onChange } = renderInspector(node, opEntry);
  await waitFor(() => expect(screen.getByRole("option", { name: /Villes/ })).toBeInTheDocument());
  await userEvent.selectOptions(screen.getByLabelText("collectionId"), "villes");
  expect(onChange).toHaveBeenCalledWith({ collectionId: "villes" });
});

test("an enum field renders a plain select with its options", () => {
  const node: PipelineNode = {
    id: "j1",
    kind: "transform",
    op: "transform.join",
    x: 0,
    y: 0,
    params: { withCollectionId: "villes", on: "code", how: "inner" },
  };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: {
      properties: {
        withCollectionId: { type: "string", format: "collection-id" },
        on: { type: "string" },
        how: { type: "string", enum: ["inner", "left"] },
      },
      required: ["withCollectionId", "on"],
    },
  };
  renderInspector(node, opEntry);
  const select = screen.getByLabelText("how") as HTMLSelectElement;
  expect(Array.from(select.options).map((o) => o.value)).toEqual(["inner", "left"]);
});

test("a string field renders a text input", async () => {
  const node: PipelineNode = {
    id: "f1",
    kind: "transform",
    op: "transform.filter",
    x: 0,
    y: 0,
    params: { expr: "" },
  };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] },
  };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.type(screen.getByLabelText("expr"), "pop > 1000");
  expect(onChange).toHaveBeenLastCalledWith({ expr: "pop > 1000" });
});

test("an array-of-string field renders a comma-separated input parsed to a string array", async () => {
  const node: PipelineNode = {
    id: "a1",
    kind: "transform",
    op: "transform.aggregate",
    x: 0,
    y: 0,
    params: { groupBy: [], metrics: {} },
  };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: {
      properties: {
        groupBy: { type: "array", items: { type: "string" } },
        metrics: { type: "object" },
      },
      required: [],
    },
  };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.type(screen.getByLabelText("groupBy"), "region, departement");
  expect(onChange).toHaveBeenLastCalledWith({ groupBy: ["region", "departement"], metrics: {} });
});

test("an object field renders a key-value editor; adding a row updates the dict", async () => {
  const node: PipelineNode = {
    id: "a1",
    kind: "transform",
    op: "transform.aggregate",
    x: 0,
    y: 0,
    params: { groupBy: [], metrics: {} },
  };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: {
      properties: {
        groupBy: { type: "array", items: { type: "string" } },
        metrics: { type: "object" },
      },
      required: [],
    },
  };
  const { onChange } = renderInspector(node, opEntry);
  await userEvent.click(screen.getByRole("button", { name: "Ajouter metrics" }));
  await userEvent.type(screen.getByLabelText("metrics clé 1"), "total_pop");
  await userEvent.type(screen.getByLabelText("metrics valeur 1"), "sum(pop)");
  expect(onChange).toHaveBeenLastCalledWith({ groupBy: [], metrics: { total_pop: "sum(pop)" } });
});

test("a field with a description renders it as helper text under the control", () => {
  const node: PipelineNode = {
    id: "w1",
    kind: "writer",
    op: "writer.collection",
    x: 0,
    y: 0,
    params: { collectionId: "villes", mode: "append" },
  };
  const opEntry: PipelineOpEntry = {
    kind: "writer",
    paramsSchema: {
      properties: {
        collectionId: { type: "string", format: "collection-id" },
        mode: {
          type: "string",
          enum: ["append", "replace"],
          description:
            '"replace" supprime TOUTES les données existantes de la collection cible avant d\'écrire.',
        },
      },
      required: ["collectionId"],
    },
  };
  renderInspector(node, opEntry);
  expect(
    screen.getByText(
      '"replace" supprime TOUTES les données existantes de la collection cible avant d\'écrire.',
    ),
  ).toBeInTheDocument();
});

test("a field without a description renders no helper text", () => {
  const node: PipelineNode = {
    id: "f1",
    kind: "transform",
    op: "transform.filter",
    x: 0,
    y: 0,
    params: { expr: "" },
  };
  const opEntry: PipelineOpEntry = {
    kind: "transform",
    paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] },
  };
  renderInspector(node, opEntry);
  // Aucun <p> superflu (pas de texte d'aide vide) quand le champ ne porte
  // pas de description — seuls les <p role="alert"> d'erreurs en portent,
  // absents ici (errors=[]).
  expect(document.body.querySelectorAll("p")).toHaveLength(0);
});

test("passed-in errors render as alerts", () => {
  const node: PipelineNode = {
    id: "r1",
    kind: "reader",
    op: "reader.collection",
    x: 0,
    y: 0,
    params: {},
  };
  const opEntry: PipelineOpEntry = {
    kind: "reader",
    paramsSchema: {
      properties: { collectionId: { type: "string", format: "collection-id" } },
      required: ["collectionId"],
    },
  };
  const qc = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  const client: Partial<ItemClient> = { listCollections: () => Promise.resolve([]) };
  render(
    <QueryClientProvider client={qc}>
      <ItemClientProvider client={client as ItemClient}>
        <PipelineNodeInspector
          node={node}
          opEntry={opEntry}
          errors={["collectionId est requis."]}
          onChange={vi.fn()}
        />
      </ItemClientProvider>
    </QueryClientProvider>,
  );
  expect(screen.getByRole("alert")).toHaveTextContent("collectionId est requis.");
});
