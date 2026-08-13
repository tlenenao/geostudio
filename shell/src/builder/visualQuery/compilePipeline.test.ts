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
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "transform.filter", "transform.select", "writer.dataset"]);
    const writer = pipeline.nodes.find((n) => n.op === "writer.dataset")!;
    expect(writer.params).toEqual({ collectionId: "query_out", datasetId: "dataset-1", mode: "replace" });
    expect(pipeline.edges).toHaveLength(3);
    expect(pipeline.edges.every((e) => e.role == null)).toBe(true);
  });

  test("aucune étape optionnelle : reader -> select -> writer.dataset", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "transform.select", "writer.dataset"]);
  });

  test("jointure : deux readers, un select implicite sur la branche jointe, arête secondaire", () => {
    const state = baseState({ join: { collectionId: "communes", on: "commune", how: "inner" } });
    const pipeline = compileVisualQueryToPipeline(state, BASE, JOINED, "query_out", "dataset-1");
    const ops = pipeline.nodes.map((n) => n.op);
    expect(ops).toEqual(["reader.collection", "reader.collection", "transform.select", "transform.join", "transform.select", "writer.dataset"]);
    const joinNode = pipeline.nodes.find((n) => n.op === "transform.join")!;
    expect(joinNode.params).toEqual({ on: "commune", how: "inner" });
    const secondaryEdge = pipeline.edges.find((e) => e.role === "secondary")!;
    // Il y a maintenant deux nœuds transform.select (jointe + sortie finale) :
    // le premier trouvé dans l'ordre d'insertion est celui de la branche jointe.
    const joinedSelectNode = pipeline.nodes.filter((n) => n.op === "transform.select")[0];
    expect(secondaryEdge.from).toBe(joinedSelectNode.id);
    expect(secondaryEdge.to).toBe(joinNode.id);
    expect(joinedSelectNode.params).toEqual({ columns: { commune: null, population: null } });
    const outputSelectNode = pipeline.nodes.filter((n) => n.op === "transform.select")[1];
    expect(outputSelectNode.params).toEqual({ columns: { commune: null, gravite: null, population: null } });
  });

  test("étape de sortie finale : exclut une colonne de type unsupported, inclut la géométrie", () => {
    const baseWithUnsupported: CollectionSchema = {
      collection: "incidents", pk: "id", geometry: { column: "geom", type: "Point", srid: 4326 },
      fields: [
        { name: "commune", type: "string", required: true },
        { name: "brut", type: "unsupported", required: false },
      ],
    };
    const pipeline = compileVisualQueryToPipeline(baseState(), baseWithUnsupported, null, "query_out", "dataset-1");
    const ops = pipeline.nodes.map((n) => n.op);
    expect(ops).toEqual(["reader.collection", "transform.select", "writer.dataset"]);
    const outputSelect = pipeline.nodes.find((n) => n.op === "transform.select")!;
    expect(outputSelect.params).toEqual({ columns: { commune: null, geometry: null } });
  });

  test("étape de sortie finale : absente pour un résumé (transform.aggregate projette déjà exactement)", () => {
    const state = baseState({
      summary: { groupBy: ["commune"], metrics: [{ alias: "nb", function: "count", sourceColumn: null }] },
    });
    const pipeline = compileVisualQueryToPipeline(state, BASE, null, "query_out", "dataset-1");
    expect(pipeline.nodes.map((n) => n.op)).toEqual(["reader.collection", "transform.aggregate", "writer.dataset"]);
  });

  test("étape de sortie finale : présente mais sans clé geometry quand la collection de base n'en a pas", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    const outputSelect = pipeline.nodes.find((n) => n.op === "transform.select");
    expect(outputSelect!.params).toEqual({ columns: { commune: null, gravite: null } });
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

  test("transform.select non reconnu s'il n'est pas immédiatement avant le writer -> null", () => {
    const pipeline = compileVisualQueryToPipeline(baseState(), BASE, null, "query_out", "dataset-1");
    // baseState() compile en: [reader, select(output), writer]
    // avec edges: reader->select, select->writer

    const outputSelect = pipeline.nodes.find((n) => n.op === "transform.select")!;
    const reader = pipeline.nodes.find((n) => n.op === "reader.collection")!;

    // Crée un nœud transform.select intermédiaire
    const customSelect = {
      id: "custom-select",
      kind: "transform" as const,
      op: "transform.select",
      x: 0,
      y: 0,
      params: { columns: { commune: null } },
    };

    // Ajoute le nœud
    pipeline.nodes.push(customSelect);

    // Récupère l'arête reader->select
    const readerToSelectEdge = pipeline.edges.find((e) => e.from === reader.id && e.to === outputSelect.id)!;

    // Crée la chaîne: reader -> customSelect -> outputSelect -> writer
    readerToSelectEdge.to = customSelect.id;

    pipeline.edges.push({
      id: "e-custom-to-output",
      from: customSelect.id,
      to: outputSelect.id,
      role: null,
    });

    // Le customSelect n'est pas immédiatement avant le writer
    expect(decompilePipelineToWizardState(pipeline)).toBeNull();
  });
});
