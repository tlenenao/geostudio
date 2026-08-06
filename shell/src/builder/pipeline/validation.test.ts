// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
import { isPipelineValid, validatePipelineGraphLocally } from "./validation";

const CATALOG: PipelineOpsCatalog = {
  "reader.collection": { kind: "reader", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
  "transform.filter": { kind: "transform", paramsSchema: { properties: { expr: { type: "string" } }, required: ["expr"] } },
  "writer.collection": { kind: "writer", paramsSchema: { properties: { collectionId: { type: "string", format: "collection-id" } }, required: ["collectionId"] } },
};

function reader(id: string, params: Record<string, unknown> = { collectionId: "villes" }): PipelineNode {
  return { id, kind: "reader", op: "reader.collection", x: 0, y: 0, params };
}
function writer(id: string, params: Record<string, unknown> = { collectionId: "villes_propres" }): PipelineNode {
  return { id, kind: "writer", op: "writer.collection", x: 0, y: 0, params };
}

test("a valid linear reader->writer graph has no errors", () => {
  const nodes = [reader("r1"), writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toEqual([]);
  expect(result.nodeErrors).toEqual({ r1: [], w1: [] });
  expect(isPipelineValid(result)).toBe(true);
});

test("a graph with no reader node is invalid", () => {
  const result = validatePipelineGraphLocally([writer("w1")], [], CATALOG);
  expect(result.graphErrors).toContain("Le pipeline doit contenir au moins une source.");
  expect(isPipelineValid(result)).toBe(false);
});

test("a graph with no writer node is invalid", () => {
  const result = validatePipelineGraphLocally([reader("r1")], [], CATALOG);
  expect(result.graphErrors).toContain("Le pipeline doit contenir au moins une écriture.");
});

test("a cyclic graph is invalid", () => {
  const nodes = [reader("r1"), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "w1" },
    { id: "e2", from: "w1", to: "r1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toContain("Le graphe contient un cycle.");
});

test("a node with more than one incoming edge is invalid", () => {
  const nodes = [reader("r1"), reader("r2"), writer("w1")];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "w1" },
    { id: "e2", from: "r2", to: "w1" },
  ];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toContain("Un nœud ne peut avoir qu'une seule arête entrante (w1).");
});

test("a node missing a required param is flagged on that node, not as a graph error", () => {
  const nodes = [reader("r1", {}), writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.graphErrors).toEqual([]);
  expect(result.nodeErrors.r1).toEqual(["collectionId est requis."]);
  expect(isPipelineValid(result)).toBe(false);
});

test("a node whose op is not in the catalogue is flagged on that node", () => {
  const nodes = [{ ...reader("r1"), op: "reader.does-not-exist" }, writer("w1")];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const result = validatePipelineGraphLocally(nodes, edges, CATALOG);
  expect(result.nodeErrors.r1).toEqual(["Opération inconnue : reader.does-not-exist."]);
});

test("isPipelineValid is false when any node has errors even if graphErrors is empty", () => {
  const result = { graphErrors: [], nodeErrors: { r1: ["x est requis."] } };
  expect(isPipelineValid(result)).toBe(false);
});
