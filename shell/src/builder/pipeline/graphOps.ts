// SPDX-License-Identifier: Apache-2.0
import type { PipelineEdge, PipelineNode } from "../../api/types";

// Pas crypto.randomUUID() : évite toute dépendance à sa disponibilité dans
// l'environnement de test (jsdom) ou un navigateur ancien — un id
// suffisamment unique pour un graphe édité par un seul utilisateur en local.
function genId(prefix: string): string {
  return `${prefix}-${Math.random().toString(36).slice(2, 10)}`;
}

export function genNodeId(): string {
  return genId("n");
}

export function genEdgeId(): string {
  return genId("e");
}

export function hasIncomingEdge(edges: PipelineEdge[], nodeId: string): boolean {
  return edges.some((e) => e.to === nodeId);
}

// Miroir client de app/configs/pipeline_validation.py::_check_acyclic
// (SP-15a) — mêmes couleurs DFS, mais posée la question "ce candidat
// créerait-il un cycle ?" avant de l'ajouter, pour la garde de connexion
// interactive du canvas (Task 6).
export function wouldCreateCycle(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  candidate: { from: string; to: string },
): boolean {
  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) adjacency.get(e.from)?.push(e.to);
  adjacency.get(candidate.from)?.push(candidate.to);

  const WHITE = 0, GRAY = 1, BLACK = 2;
  const color = new Map<string, number>(nodes.map((n) => [n.id, WHITE]));

  function visit(nodeId: string): boolean {
    color.set(nodeId, GRAY);
    for (const next of adjacency.get(nodeId) ?? []) {
      if (color.get(next) === GRAY) return true;
      if (color.get(next) === WHITE && visit(next)) return true;
    }
    color.set(nodeId, BLACK);
    return false;
  }

  return nodes.some((n) => color.get(n.id) === WHITE && visit(n.id));
}

// Insertion d'un nœud "sur" une arête existante (SP-15b, clic sur le bouton
// "+" d'une arête, cf. plan Global Constraints — pas un drag-drop précis sur
// le tracé SVG) : retire l'arête from->to, ajoute le nœud, reconnecte
// from->nouveau->to.
export function insertNodeOnEdge(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  edgeId: string,
  newNode: PipelineNode,
): { nodes: PipelineNode[]; edges: PipelineEdge[] } {
  const edge = edges.find((e) => e.id === edgeId);
  if (!edge) return { nodes, edges };
  const rest = edges.filter((e) => e.id !== edgeId);
  return {
    nodes: [...nodes, newNode],
    edges: [...rest, { id: genEdgeId(), from: edge.from, to: newNode.id }, { id: genEdgeId(), from: newNode.id, to: edge.to }],
  };
}
