// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode, PipelineOpsCatalog } from "../../api/types";
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
      errors.push(`${field} est requis.`);
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
  for (const [nodeId, count] of primaryCount) {
    if (count > 1)
      graphErrors.push(`Un nœud ne peut avoir qu'une seule arête entrante (${nodeId}).`);
  }
  for (const [nodeId, count] of secondaryCount) {
    if (count > 1)
      graphErrors.push(`Un nœud ne peut avoir qu'une seule arête secondaire entrante (${nodeId}).`);
  }

  if (hasCycle(nodes, edges)) {
    graphErrors.push("Le graphe contient un cycle.");
  }

  if (!nodes.some((n) => n.kind === "reader"))
    graphErrors.push("Le pipeline doit contenir au moins une source.");
  if (!nodes.some((n) => n.kind === "writer"))
    graphErrors.push("Le pipeline doit contenir au moins une écriture.");

  for (const node of nodes) {
    const entry = opsCatalog[node.op];
    const errors = entry
      ? validateNodeParamsShape(entry, node.params)
      : [`Opération inconnue : ${node.op}.`];
    const hasSecondaryEdge = edges.some((e) => e.to === node.id && e.role === "secondary");
    const hasPrimaryEdge = edges.some((e) => e.to === node.id && e.role !== "secondary");
    if (entry) {
      if (entry.acceptsSecondaryInput) {
        const withCollectionId = node.params.withCollectionId;
        const hasParam =
          withCollectionId !== undefined && withCollectionId !== null && withCollectionId !== "";
        if (!hasPrimaryEdge) {
          errors.push(`${node.op} : requiert une arête primaire entrante.`);
        }
        if (hasSecondaryEdge && hasParam) {
          errors.push(
            `${node.op} : withCollectionId et une arête secondaire ne peuvent pas être renseignés en même temps.`,
          );
        } else if (!hasSecondaryEdge && !hasParam) {
          errors.push(`${node.op} : requiert soit withCollectionId, soit une arête secondaire.`);
        }
      } else if (hasSecondaryEdge) {
        errors.push(`${node.op} n'accepte pas d'arête secondaire.`);
      }
    }
    nodeErrors[node.id] = errors;
  }

  return { graphErrors, nodeErrors };
}
