// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
import { t } from "../../i18n";
import { hasCycle } from "./graphOps";

export type PipelineValidationResult = {
  graphErrors: string[];
  nodeErrors: Record<string, string[]>;
};

export function isPipelineValid(result: PipelineValidationResult): boolean {
  return (
    result.graphErrors.length === 0 &&
    Object.values(result.nodeErrors).every((errs) => errs.length === 0)
  );
}

// Matches validateNodeParamsShape's message format ("${field} est requis.")
// by prefix — a pure convenience matcher, not a change to
// PipelineValidationResult's shape. An error that doesn't start with any
// known field name (a structural op-level error, e.g. "requiert une arête
// primaire entrante") never matches any field and keeps rendering in the
// node-level fallback list.
export function fieldErrorsFor(field: string, errors: string[]): string[] {
  return errors.filter((e) => e.startsWith(`${field} `));
}

// Vérification de forme uniquement (présence des champs requis) — jamais la
// sémantique d'une expression SQL bornée, cf. plan Global Constraints et
// design SP-15a §5.1 (frontière déjà actée, non rouverte ici).
function validateNodeParamsShape(
  entry: PipelineOpsCatalog[string],
  params: Record<string, unknown>,
): string[] {
  const errors: string[] = [];
  for (const field of entry.paramsSchema.required ?? []) {
    const value = params[field];
    if (value === undefined || value === null || value === "") {
      errors.push(t("pipelineValidation.fieldRequired", { field }));
    }
  }
  return errors;
}

// Miroir client des quatre vérifications structurelles de
// app/configs/pipeline_validation.py (SP-15a) + la forme des params de
// chaque nœud — retour rapide pour l'éditeur (§4.3 du design). Le serveur
// reste la garde définitive à chaque POST/PUT /configs, inchangé.
export function validatePipelineGraphLocally(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  opsCatalog: PipelineOpsCatalog,
): PipelineValidationResult {
  const graphErrors: string[] = [];
  const nodeErrors: Record<string, string[]> = {};

  const primaryCount = new Map<string, number>();
  const secondaryCount = new Map<string, number>();
  for (const e of edges) {
    const bucket = e.role === "secondary" ? secondaryCount : primaryCount;
    bucket.set(e.to, (bucket.get(e.to) ?? 0) + 1);
  }
  // Nom affiché d'un nœud (titre, sinon opération) — jamais son identifiant technique.
  const nameById = new Map(nodes.map((n) => [n.id, n.title ?? n.op]));
  const nameOf = (id: string) => nameById.get(id) ?? id;
  for (const [nodeId, count] of primaryCount) {
    if (count > 1)
      graphErrors.push(t("pipelineValidation.multiplePrimary", { node: nameOf(nodeId) }));
  }
  for (const [nodeId, count] of secondaryCount) {
    if (count > 1)
      graphErrors.push(t("pipelineValidation.multipleSecondary", { node: nameOf(nodeId) }));
  }

  // j06-002 : miroir de _check_topology (cœur) — formes que l'exécution ne sait pas traiter.
  const kindById = new Map(nodes.map((n) => [n.id, n.kind]));
  for (const e of edges) {
    if (kindById.get(e.to) === "reader")
      graphErrors.push(t("pipelineValidation.readerIncoming", { node: nameOf(e.to) }));
    if (kindById.get(e.from) === "writer")
      graphErrors.push(t("pipelineValidation.writerOutgoing", { node: nameOf(e.from) }));
    if (e.role === "secondary" && kindById.get(e.to) === "writer")
      graphErrors.push(t("pipelineValidation.writerSecondary", { node: nameOf(e.to) }));
  }
  if (hasCycle(nodes, edges)) {
    graphErrors.push(t("pipelineValidation.cycle"));
  }

  if (!nodes.some((n) => n.kind === "reader")) graphErrors.push(t("pipelineValidation.noReader"));
  if (!nodes.some((n) => n.kind === "writer")) graphErrors.push(t("pipelineValidation.noWriter"));

  for (const node of nodes) {
    const entry = opsCatalog[node.op];
    const errors = entry
      ? validateNodeParamsShape(entry, node.params)
      : [t("pipelineValidation.unknownOp", { op: node.op })];
    const hasSecondaryEdge = edges.some((e) => e.to === node.id && e.role === "secondary");
    const hasPrimaryEdge = edges.some((e) => e.to === node.id && e.role !== "secondary");
    // j06-002 : erreur portée par le nœud (badge + inspecteur), pas une bannière de graphe.
    if (node.kind !== "reader" && !edges.some((e) => e.to === node.id)) {
      errors.push(t("pipelineValidation.noInput"));
    }
    if (entry) {
      if (entry.acceptsSecondaryInput) {
        const withCollectionId = node.params.withCollectionId;
        const hasParam =
          withCollectionId !== undefined && withCollectionId !== null && withCollectionId !== "";
        if (!hasPrimaryEdge) {
          errors.push(t("pipelineValidation.needsPrimary", { node: nameOf(node.id) }));
        }
        if (hasSecondaryEdge && hasParam) {
          errors.push(t("pipelineValidation.secondaryConflict", { node: nameOf(node.id) }));
        } else if (!hasSecondaryEdge && !hasParam) {
          errors.push(t("pipelineValidation.needsSecondary", { node: nameOf(node.id) }));
        }
      } else if (hasSecondaryEdge) {
        errors.push(t("pipelineValidation.noSecondaryAllowed", { node: nameOf(node.id) }));
      }
    }
    nodeErrors[node.id] = errors;
  }

  return { graphErrors, nodeErrors };
}
