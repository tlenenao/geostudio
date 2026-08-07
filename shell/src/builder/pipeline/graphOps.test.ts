// SPDX-License-Identifier: Apache-2.0
import { expect, test } from "vitest";
import type { PipelineEdge, PipelineNode } from "../../api/types";
import { genEdgeId, genNodeId, hasIncomingEdge, insertNodeOnEdge, topologicalOrder, wouldCreateCycle } from "./graphOps";

test("genNodeId and genEdgeId produce distinct, non-empty ids", () => {
  const a = genNodeId();
  const b = genNodeId();
  expect(a).not.toBe(b);
  expect(a.length).toBeGreaterThan(0);
  expect(genEdgeId().length).toBeGreaterThan(0);
});

test("hasIncomingEdge is true only for a node that is some edge's 'to'", () => {
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  expect(hasIncomingEdge(edges, "w1")).toBe(true);
  expect(hasIncomingEdge(edges, "r1")).toBe(false);
});

test("wouldCreateCycle detects a direct back-edge", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "a", to: "b" }];
  expect(wouldCreateCycle(nodes, edges, { from: "b", to: "a" })).toBe(true);
});

test("wouldCreateCycle detects a longer cycle through an intermediate node", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} },
    { id: "c", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "a", to: "b" },
    { id: "e2", from: "b", to: "c" },
  ];
  expect(wouldCreateCycle(nodes, edges, { from: "c", to: "a" })).toBe(true);
});

test("wouldCreateCycle is false for a candidate that keeps the graph acyclic", () => {
  const nodes: PipelineNode[] = [
    { id: "a", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "b", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
  ];
  expect(wouldCreateCycle(nodes, [], { from: "a", to: "b" })).toBe(false);
});

test("insertNodeOnEdge splits the edge into two, wiring the new node between", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "w1", kind: "writer", op: "writer.collection", x: 200, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1" }];
  const newNode: PipelineNode = { id: "t1", kind: "transform", op: "transform.filter", x: 100, y: 0, params: {} };

  const result = insertNodeOnEdge(nodes, edges, "e1", newNode);

  expect(result.nodes).toEqual([...nodes, newNode]);
  expect(result.edges).toHaveLength(2);
  expect(result.edges.find((e) => e.from === "r1")?.to).toBe("t1");
  expect(result.edges.find((e) => e.from === "t1")?.to).toBe("w1");
  expect(result.edges.some((e) => e.id === "e1")).toBe(false);
});

test("insertNodeOnEdge is a no-op when the edge id does not exist", () => {
  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];
  const newNode: PipelineNode = { id: "t1", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} };
  const result = insertNodeOnEdge(nodes, edges, "missing", newNode);
  expect(result).toEqual({ nodes, edges });
});

test("hasIncomingEdge defaults to checking for a primary (non-secondary) edge", () => {
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "w1", role: "secondary" }];
  expect(hasIncomingEdge(edges, "w1")).toBe(false); // only a secondary edge exists, not a primary one
  expect(hasIncomingEdge(edges, "w1", "secondary")).toBe(true);
});

test("hasIncomingEdge distinguishes primary from secondary explicitly", () => {
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
  ];
  expect(hasIncomingEdge(edges, "t1", "primary")).toBe(true);
  expect(hasIncomingEdge(edges, "t1", "secondary")).toBe(true);
});

test("insertNodeOnEdge preserves the original edge's role on the downstream half", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.join", x: 200, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [{ id: "e1", from: "r1", to: "t1", role: "secondary" }];
  const newNode: PipelineNode = { id: "f1", kind: "transform", op: "transform.filter", x: 100, y: 0, params: {} };

  const result = insertNodeOnEdge(nodes, edges, "e1", newNode);

  const upstream = result.edges.find((e) => e.from === "r1");
  const downstream = result.edges.find((e) => e.from === "f1");
  expect(upstream?.role).toBeUndefined();
  expect(downstream?.role).toBe("secondary");
});

test("topologicalOrder returns nodes in a valid dependency order", () => {
  const nodes: PipelineNode[] = [
    { id: "w1", kind: "writer", op: "writer.collection", x: 0, y: 0, params: {} },
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.filter", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "t1", to: "w1" },
  ];
  expect(topologicalOrder(nodes, edges)).toEqual(["r1", "t1", "w1"]);
});

test("topologicalOrder handles fan-out and fan-in deterministically (sorted ties)", () => {
  const nodes: PipelineNode[] = [
    { id: "r1", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "r2", kind: "reader", op: "reader.collection", x: 0, y: 0, params: {} },
    { id: "t1", kind: "transform", op: "transform.merge", x: 0, y: 0, params: {} },
  ];
  const edges: PipelineEdge[] = [
    { id: "e1", from: "r1", to: "t1" },
    { id: "e2", from: "r2", to: "t1", role: "secondary" },
  ];
  expect(topologicalOrder(nodes, edges)).toEqual(["r1", "r2", "t1"]);
});
