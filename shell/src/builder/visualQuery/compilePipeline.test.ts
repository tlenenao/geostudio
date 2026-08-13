// SPDX-License-Identifier: Apache-2.0
import { describe, expect, test } from "vitest";
import type { CollectionSchema } from "../../api/types";
import { compileVisualQueryToPipeline, decompilePipelineToWizardState, VisualQueryState } from "./compilePipeline";

const BASE: CollectionSchema = {
  collection: "incidents", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "gravite", type: "integer", required: false }],
};
const JOINED: CollectionSchema = {
  collection: "communes", pk: "id", geometry: null,
  fields: [{ name: "commune", type: "string", required: true }, { name: "population", type: "integer", required: false }],
};

function baseState(overrides: Partial<VisualQueryState> = {}): VisualQueryState {
  return {
    title: "Ma requête", baseCollectionId: "incidents",
    filters: [], join: null, summary: null, refreshPolicy: null,
    ...overrides,
  };
}

describe("compileVisualQueryToPipeline", () => {
  test("filtre seul : reader -> filter -> writer.dataset", () => {
    const state = baseState({ filters: [{ column: "gravite", operator: "gt", value: "3" }] });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "transform.filter", "writer.dataset"]);
    const writer = pipeline.nodes.find((n) => n.op === "writer.dataset")!;
    expect(writer.params).toEqual({ collectionId: "query_out", datasetId: "dataset-1" });
    expect(pipeline.edges).toHaveLength(2);
    expect(pipeline.edges.every((e) => e.role == null)).toBe(true);
  });

  test("aucune étape optionnelle : reader -> writer.dataset directement", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "writer.dataset"]);
  });

  test("jointure : deux readers, un select implicite sur la branche jointe, arête secondaire", () => {
    const state = baseState({ join: { collectionId: "communes", on: "commune", how: "inner" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, JOINED, "query_out", "dataset-1");
    const ops = pipeline.nodes.map((n) => n.op);
    expect(ops).toEqual(["reader.collection", "reader.collection", "transform.select", "transform.join", "writer.dataset"]);
    const joinNode = pipeline.nodes.find((n) => n.op === "transform.join")!;
    expect(joinNode.params).toEqual({ on: "commune", how: "inner" });
    const secondaryEdge = pipeline.edges.find((e) => e.role === "secondary")!;
    const selectNode = pipeline.nodes.find((n) => n.op === "transform.select")!;
    expect(secondaryEdge.from).toBe(selectNode.id);
    expect(secondaryEdge.to).toBe(joinNode.id);
    // La colonne de jointure est gardée telle quelle (null = pas de renommage) ;
    // "population" ne collide pas avec BASE, gardée telle quelle aussi.
    expect(selectNode.params).toEqual({ columns: { commune: null, population: null } });
  });

  test("jointure avec collision de nom hors colonne de jointure : renommage joined_<nom>", () => {
    const joinedWithCollision: CollectionSchema = {
      ...JOINED,
      fields: [...JOINED.fields, { name: "gravite", type: "string", required: false }],
    };
    const state = baseState({ join: { collectionId: "communes", on: "commune", how: "left" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, joinedWithCollision, "query_out", "dataset-1");
    const selectNode = pipeline.nodes.find((n) => n.op === "transform.select")!;
    expect(selectNode.params).toEqual({
      columns: { commune: null, population: null, gravite: "joined_gravite" },
    });
  });

  test("résumé : aggregate avec count(*) et sum(colonne quotée)", () => {
    const state = baseState({
      summary: {
        groupBy: ["commune"],
        metrics: [
          { alias: "nb", function: "count", sourceColumn: null },
          { alias: "total", function: "sum", sourceColumn: "gravite" },
        ],
      },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    const aggNode = pipeline.nodes.find((n) => n.op === "transform.aggregate")!;
    expect(aggNode.params).toEqual({
      groupBy: ["commune"], metrics: { nb: "count(*)", total: 'sum("gravite")' },
    });
  });

  test("propage refreshPolicy quand fournie", () => {
    const state = baseState({ refreshPolicy: { enabled: true, cron: "0 6 * * *" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    expect(pipeline.refreshPolicy).toEqual({ enabled: true, cron: "0 6 * * *" });
  });
});

describe("decompilePipelineToWizardState", () => {
  test("round-trip sur filtre + jointure + résumé", () => {
    const state = baseState({
      filters: [{ column: "gravite", operator: "gt", value: "3" }],
      join: { collectionId: "communes", on: "commune", how: "inner" },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, JOINED, "query_out", "dataset-1");
    const decompiled = decompilePipelineToWizardState(pipeline);
    expect(decompiled).toEqual({
      baseCollectionId: "incidents",
      filters: [{ column: "gravite", operator: "gt", value: "3" }],
      join: { collectionId: "communes", on: "commune", how: "inner" },
      summary: null,
    });
  });

  test("forme non reconnue (nœud supplémentaire ajouté à la main) -> null", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    pipeline.nodes.push({ id: "extra", kind: "transform", op: "transform.derive", x: 0, y: 0, params: { column: "x", expr: "1" } });
    pipeline.edges.push({ id: "e-extra", from: pipeline.nodes[0].id, to: "extra" });
    expect(decompilePipelineToWizardState(pipeline)).toBeNull();
  });

  test("plusieurs writers -> null", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    pipeline.nodes.push({ id: "w2", kind: "writer", op: "writer.export", x: 0, y: 0, params: { format: "csv", key: "x" } });
    expect(decompilePipelineToWizardState(pipeline)).toBeNull();
  });

  test("round-trip sur résumé seul (aggregate) — count et sum", () => {
    const state = baseState({
      summary: {
        groupBy: ["commune"],
        metrics: [
          { alias: "nb", function: "count", sourceColumn: null },
          { alias: "total", function: "sum", sourceColumn: "gravite" },
        ],
      },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    const decompiled = decompilePipelineToWizardState(pipeline);
    expect(decompiled).toEqual({
      baseCollectionId: "incidents",
      filters: [],
      join: null,
      summary: {
        groupBy: ["commune"],
        metrics: [
          { alias: "nb", function: "count", sourceColumn: null },
          { alias: "total", function: "sum", sourceColumn: "gravite" },
        ],
      },
    });
  });
});
