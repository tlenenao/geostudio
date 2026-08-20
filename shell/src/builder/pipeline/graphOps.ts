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

export function hasIncomingEdge(
  edges: PipelineEdge[],
  nodeId: string,
  role: "primary" | "secondary" = "primary",
): boolean {
  return edges.some((e) => {
    if (e.to !== nodeId) return false;
    return role === "secondary" ? e.role === "secondary" : e.role !== "secondary";
  });
}

// Détection de cycle interne (DFS trois couleurs) — factorisée pour être
// réutilisée par wouldCreateCycle (candidat hypothétique, Task 3) et
// validatePipelineGraphLocally (graphe déjà construit, validation.ts),
// qui dupliquaient auparavant le même DFS.
export function hasCycle(nodes: PipelineNode[], edges: { from: string; to: string }[]): boolean {
  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) adjacency.get(e.from)?.push(e.to);

  const WHITE = 0,
    GRAY = 1,
    BLACK = 2;
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

// Miroir client de app/configs/pipeline_validation.py::_check_acyclic
// (SP-15a) — mêmes couleurs DFS, mais posée la question "ce candidat
// créerait-il un cycle ?" avant de l'ajouter, pour la garde de connexion
// interactive du canvas (Task 6).
export function wouldCreateCycle(
  nodes: PipelineNode[],
  edges: PipelineEdge[],
  candidate: { from: string; to: string },
): boolean {
  return hasCycle(nodes, [...edges, candidate]);
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
  const downstream: PipelineEdge = { id: genEdgeId(), from: newNode.id, to: edge.to };
  if (edge.role) downstream.role = edge.role;
  return {
    nodes: [...nodes, newNode],
    edges: [...rest, { id: genEdgeId(), from: edge.from, to: newNode.id }, downstream],
  };
}

// Miroir client de app/pipelines/compiler.py::topological_order (SP-15a) —
// même algorithme de Kahn, tri déterministe des ids à chaque étape pour que
// le "prochain nœud" affiché pendant une exécution (PipelineCanvas, SP-15g
// §5.2) corresponde à l'ordre réel du runtime. Ne lève jamais sur un cycle
// (contrairement à la version serveur) : un pipeline sauvegardé est déjà
// garanti acyclique (validation serveur) au moment où ce calcul sert
// uniquement d'heuristique d'affichage.
export function topologicalOrder(nodes: PipelineNode[], edges: PipelineEdge[]): string[] {
  const indegree = new Map<string, number>(nodes.map((n) => [n.id, 0]));
  const adjacency = new Map<string, string[]>(nodes.map((n) => [n.id, []]));
  for (const e of edges) {
    adjacency.get(e.from)?.push(e.to);
    indegree.set(e.to, (indegree.get(e.to) ?? 0) + 1);
  }
  let queue = nodes
    .filter((n) => indegree.get(n.id) === 0)
    .map((n) => n.id)
    .sort();
  const ordered: string[] = [];
  while (queue.length > 0) {
    const current = queue.shift()!;
    ordered.push(current);
    const newlyReady: string[] = [];
    for (const neighbor of adjacency.get(current) ?? []) {
      indegree.set(neighbor, (indegree.get(neighbor) ?? 0) - 1);
      if (indegree.get(neighbor) === 0) newlyReady.push(neighbor);
    }
    queue = [...queue, ...newlyReady].sort();
  }
  return ordered;
}
