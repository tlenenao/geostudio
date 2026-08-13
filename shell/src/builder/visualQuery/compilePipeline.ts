// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode, PipelinePayload, PipelineRefreshPolicy, CollectionSchema } from "../../api/types";
import { genEdgeId, genNodeId } from "../pipeline/graphOps";
import { FilterRow, compileFilterRowsToSql, decompileSqlToFilterRows, quoteIdent } from "./compileFilter";
import { JoinConfig, MetricConfig, SummaryConfig } from "./inferSchema";

export type VisualQueryState = {
  title: string;
  baseCollectionId: string;
  filters: FilterRow[];
  join: JoinConfig | null;
  summary: SummaryConfig | null;
  refreshPolicy: PipelineRefreshPolicy | null;
};

function metricExpr(metric: MetricConfig): string {
  if (metric.function === "count") return "count(*)";
  return `${metric.function}(${quoteIdent(metric.sourceColumn!)})`;
}

export function compileVisualQueryToPipeline(
  state: VisualQueryState, baseSchema: CollectionSchema, joinedSchema: CollectionSchema | null,
  outputCollectionId: string, datasetItemId: string,
): PipelinePayload {
  const nodes: PipelineNode[] = [];
  const edges: PipelineEdge[] = [];
  let x = 0;

  function addNode(kind: PipelineNode["kind"], op: string, params: Record<string, unknown>): PipelineNode {
    const n: PipelineNode = { id: genNodeId(), kind, op, x: (x += 200), y: 0, params };
    nodes.push(n);
    return n;
  }
  function addEdge(from: PipelineNode, to: PipelineNode, role?: "secondary") {
    edges.push({ id: genEdgeId(), from: from.id, to: to.id, role: role ?? null });
  }

  const baseReader = addNode("reader", "reader.collection", { collectionId: state.baseCollectionId });
  let mainTail = baseReader;

  if (state.filters.length > 0) {
    const filterNode = addNode("transform", "transform.filter", {
      expr: compileFilterRowsToSql(state.filters, baseSchema),
    });
    addEdge(mainTail, filterNode);
    mainTail = filterNode;
  }

  if (state.join && joinedSchema) {
    const joinedReader = addNode("reader", "reader.collection", { collectionId: state.join.collectionId });
    const baseNames = new Set(baseSchema.fields.map((f) => f.name));
    const joinedColumns: Record<string, string | null> = {};
    for (const f of joinedSchema.fields) {
      if (f.name === state.join.on) { joinedColumns[f.name] = null; continue; }
      joinedColumns[f.name] = baseNames.has(f.name) ? `joined_${f.name}` : null;
    }
    const joinedSelect = addNode("transform", "transform.select", { columns: joinedColumns });
    addEdge(joinedReader, joinedSelect);

    const joinNode = addNode("transform", "transform.join", { on: state.join.on, how: state.join.how });
    addEdge(mainTail, joinNode);
    addEdge(joinedSelect, joinNode, "secondary");
    mainTail = joinNode;
  }

  if (state.summary) {
    const metrics: Record<string, string> = {};
    for (const metric of state.summary.metrics) metrics[metric.alias] = metricExpr(metric);
    const aggregateNode = addNode("transform", "transform.aggregate", {
      groupBy: state.summary.groupBy, metrics,
    });
    addEdge(mainTail, aggregateNode);
    mainTail = aggregateNode;
  }

  const writerNode = addNode("writer", "writer.dataset", {
    collectionId: outputCollectionId, datasetId: datasetItemId,
  });
  addEdge(mainTail, writerNode);

  return { nodes, edges, refreshPolicy: state.refreshPolicy };
}

function decompileMetrics(metrics: Record<string, string>): MetricConfig[] | null {
  const result: MetricConfig[] = [];
  for (const [alias, expr] of Object.entries(metrics)) {
    if (expr === "count(*)") { result.push({ alias, function: "count", sourceColumn: null }); continue; }
    const match = expr.match(/^(sum|avg|min|max)\("((?:[^"]|"")+)"\)$/);
    if (!match) return null;
    result.push({
      alias, function: match[1] as MetricConfig["function"], sourceColumn: match[2].replace(/""/g, '"'),
    });
  }
  return result;
}

// Best-effort, reconnaît uniquement la forme exacte produite par
// compileVisualQueryToPipeline ci-dessus : un seul writer.dataset, au plus
// deux readers, une chaîne primaire sans branchement non reconnu. Toute
// autre forme (pipeline retouché à la main dans le canvas complet) renvoie
// null — le point d'appel (Task 13) traite ça comme un repli attendu vers
// PipelineBuilderPage, pas une erreur.
export function decompilePipelineToWizardState(pipeline: PipelinePayload): {
  baseCollectionId: string; filters: FilterRow[]; join: JoinConfig | null; summary: SummaryConfig | null;
} | null {
  const byId = new Map(pipeline.nodes.map((n) => [n.id, n]));
  const readerNodes = pipeline.nodes.filter((n) => n.kind === "reader");
  const writerNodes = pipeline.nodes.filter((n) => n.kind === "writer");
  if (writerNodes.length !== 1 || writerNodes[0].op !== "writer.dataset") return null;
  if (readerNodes.length < 1 || readerNodes.length > 2) return null;
  if (readerNodes.some((n) => n.op !== "reader.collection")) return null;

  const primaryReader = readerNodes.find(
    (r) => !pipeline.edges.some((e) => e.from === r.id && e.role === "secondary"),
  );
  if (!primaryReader) return null;

  let currentId = primaryReader.id;
  const visited = new Set<string>([currentId]);
  let filters: FilterRow[] = [];
  let join: JoinConfig | null = null;
  let summary: SummaryConfig | null = null;

  while (true) {
    const outgoing = pipeline.edges.filter((e) => e.from === currentId && e.role !== "secondary");
    if (outgoing.length !== 1) return null;
    const next = byId.get(outgoing[0].to);
    if (!next) return null;
    if (next.id === writerNodes[0].id) break;
    if (visited.has(next.id)) return null;
    visited.add(next.id);

    if (next.op === "transform.filter" && filters.length === 0 && !join && !summary) {
      const decompiled = decompileSqlToFilterRows(String(next.params.expr ?? ""));
      if (decompiled === null) return null;
      filters = decompiled;
      currentId = next.id;
      continue;
    }
    if (next.op === "transform.join" && !join && !summary) {
      const secondaryEdge = pipeline.edges.find((e) => e.to === next.id && e.role === "secondary");
      const joinedReader = readerNodes.find((r) => r.id !== primaryReader.id);
      if (!secondaryEdge || !joinedReader) return null;
      const selectEdge = pipeline.edges.find((e) => e.from === joinedReader.id);
      const selectNode = selectEdge ? byId.get(selectEdge.to) : undefined;
      if (!selectNode || selectNode.op !== "transform.select" || selectEdge!.to !== secondaryEdge.from) return null;
      join = {
        collectionId: String(joinedReader.params.collectionId),
        on: String(next.params.on),
        how: next.params.how === "left" ? "left" : "inner",
      };
      currentId = next.id;
      continue;
    }
    if (next.op === "transform.aggregate" && !summary) {
      const params = next.params as { groupBy?: string[]; metrics?: Record<string, string> };
      const metrics = decompileMetrics(params.metrics ?? {});
      if (metrics === null) return null;
      summary = { groupBy: params.groupBy ?? [], metrics };
      currentId = next.id;
      continue;
    }
    return null;
  }

  return { baseCollectionId: String(primaryReader.params.collectionId), filters, join, summary };
}
