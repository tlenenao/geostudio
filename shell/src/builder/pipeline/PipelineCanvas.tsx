// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";
import {
  Background,
  Controls,
  EdgeLabelRenderer,
  Handle,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  type Edge,
  type EdgeChange,
  type EdgeProps,
  type Node,
  type NodeChange,
  type NodeProps,
  type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type {
  PipelineEdge,
  PipelineNode,
  PipelineNodeStat,
  PipelineOpsCatalog,
} from "../../api/types";
import { genEdgeId, hasIncomingEdge, topologicalOrder, wouldCreateCycle } from "./graphOps";

// Les 6 op transform.* insérables sur une arête (cf. plan Task 6 — clic sur
// le "+" d'une arête, pas de drag-drop précis sur le tracé SVG). SP-15c
// ajoute les 5 op spatiales étage 1 ; SP-15g ajoute transform.merge (fusion
// ligne à ligne). writer.dataset n'y figure jamais (ce n'est pas une op
// transform, jamais candidate à cette liste, cf. design §5).
const INSERTABLE_TRANSFORMS: { op: string; label: string }[] = [
  { op: "transform.filter", label: "Filtrer" },
  { op: "transform.select", label: "Sélectionner" },
  { op: "transform.derive", label: "Dériver" },
  { op: "transform.aggregate", label: "Agréger" },
  { op: "transform.join", label: "Joindre" },
  { op: "transform.merge", label: "Fusionner" },
  { op: "transform.buffer", label: "Buffer" },
  { op: "transform.reproject", label: "Reprojeter" },
  { op: "transform.intersection", label: "Intersection" },
  { op: "transform.countWithin", label: "Compter dans" },
  { op: "transform.h3Aggregate", label: "Agréger H3" },
];

const KIND_COLOR: Record<PipelineNode["kind"], string> = {
  reader: "border-emerald-500 bg-emerald-50",
  transform: "border-amber-500 bg-amber-50",
  writer: "border-sky-500 bg-sky-50",
};

// Bagage porté par le `data` de chaque nœud React Flow (SP-15g) — étend
// PipelineNode (format fil) avec ce que seul le canvas a besoin de savoir
// pour se rendre : accepte-t-il une seconde entrée, où en est-il dans le run
// en cours (§5.1/§5.2 du design).
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
};

function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as CanvasNodeData;
  return (
    <div
      className={`relative rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-blue-500" : ""}`}
    >
      <Handle type="target" position={Position.Left} id="primary" />
      {node.acceptsSecondaryInput && (
        <Handle
          type="target"
          position={Position.Top}
          id="secondary"
          style={{ borderStyle: "dashed" }}
        />
      )}
      <div className="font-medium">{node.title ?? node.op}</div>
      <div className="text-[10px] text-slate-500">{node.op}</div>
      <Handle type="source" position={Position.Right} />
      {node.nodeStat && (
        <span
          role="status"
          className="absolute -right-2 -top-2 rounded-full bg-emerald-600 px-1.5 py-0.5 text-[10px] text-white"
        >
          {node.nodeStat.rowCount ?? "?"}
        </span>
      )}
      {node.isNext && !node.nodeStat && (
        <span
          role="status"
          aria-label="Exécution en cours"
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-blue-500 border-t-transparent"
        />
      )}
    </div>
  );
}

function InsertOnEdgeButton({
  id,
  sourceX,
  sourceY,
  targetX,
  targetY,
  data,
  onInsert,
}: EdgeProps & { onInsert: (edgeId: string, op: string) => void }) {
  const [open, setOpen] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const role = (data as { role?: string } | undefined)?.role;
  return (
    <>
      <path
        id={id}
        className="react-flow__edge-path"
        d={edgePath}
        style={role === "secondary" ? { strokeDasharray: "4 4" } : undefined}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
        >
          <button
            type="button"
            aria-label="Insérer une étape sur cette arête"
            className="h-5 w-5 rounded-full border border-slate-400 bg-white text-xs leading-none hover:bg-slate-100"
            onClick={() => setOpen((o) => !o)}
          >
            +
          </button>
          {open && (
            <ul
              role="menu"
              className="absolute z-10 mt-1 rounded border border-slate-300 bg-white text-xs shadow"
            >
              {INSERTABLE_TRANSFORMS.map((t) => (
                <li key={t.op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-slate-100"
                    onClick={() => {
                      onInsert(id, t.op);
                      setOpen(false);
                    }}
                  >
                    {t.label}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      </EdgeLabelRenderer>
    </>
  );
}

function toFlowNode(
  n: PipelineNode,
  selected: boolean,
  extra: { acceptsSecondaryInput: boolean; nodeStat?: PipelineNodeStat; isNext: boolean },
): Node {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { ...n, ...extra } as unknown as Record<string, unknown>,
    type: "pipelineNode",
    selected,
  };
}
function toFlowEdge(e: PipelineEdge): Edge {
  return {
    id: e.id,
    source: e.from,
    target: e.to,
    type: "insertable",
    targetHandle: e.role === "secondary" ? "secondary" : "primary",
    data: { role: e.role },
  };
}

function PipelineCanvasInner({
  nodes,
  edges,
  selectedNodeId,
  onSelectNode,
  onNodesChange,
  onEdgesChange,
  onInsertOnEdge,
  opsCatalog,
  nodeStats,
  runStatus,
}: {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onNodesChange: (nodes: PipelineNode[]) => void;
  onEdgesChange: (edges: PipelineEdge[]) => void;
  onInsertOnEdge: (edgeId: string, op: string) => void;
  opsCatalog: PipelineOpsCatalog;
  nodeStats?: Record<string, PipelineNodeStat>;
  runStatus?: "queued" | "running" | "succeeded" | "failed";
}) {
  const nodeTypes = { pipelineNode: PipelineNodeBox };
  const edgeTypes = {
    insertable: (props: EdgeProps) => <InsertOnEdgeButton {...props} onInsert={onInsertOnEdge} />,
  };

  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (!connection.source || !connection.target) return;
      const role: "primary" | "secondary" =
        connection.targetHandle === "secondary" ? "secondary" : "primary";
      if (hasIncomingEdge(edges, connection.target, role)) return; // garde §3.4/§4.3 : ≤ 1 arête entrante par rôle
      if (wouldCreateCycle(nodes, edges, { from: connection.source, to: connection.target }))
        return;
      const newEdge: PipelineEdge = {
        id: genEdgeId(),
        from: connection.source,
        to: connection.target,
      };
      if (role === "secondary") newEdge.role = "secondary";
      onEdgesChange([...edges, newEdge]);
    },
    [nodes, edges, onEdgesChange],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      let next = nodes;
      for (const change of changes) {
        if (change.type === "position" && change.position) {
          next = next.map((n) =>
            n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n,
          );
        }
        if (change.type === "remove") {
          next = next.filter((n) => n.id !== change.id);
        }
        // Ne réagit qu'à l'événement "sélectionné" (jamais "déselectionné") :
        // un clic sur un nouveau nœud émet deux changements dans un ordre non
        // garanti (ancien nœud selected:false, nouveau selected:true) — ne
        // traiter que selected:true rend la sélection robuste à cet ordre.
        // La désélection (clic sur le fond) passe par onPaneClick ci-dessous.
        if (change.type === "select" && change.selected) {
          onSelectNode(change.id);
        }
      }
      if (next !== nodes) onNodesChange(next);
    },
    [nodes, onNodesChange, onSelectNode],
  );

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      const removedIds = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
      if (removedIds.size) onEdgesChange(edges.filter((e) => !removedIds.has(e.id)));
    },
    [edges, onEdgesChange],
  );

  const order = topologicalOrder(nodes, edges);
  const nextNodeId = runStatus === "running" ? order.find((id) => !nodeStats?.[id]) : undefined;

  return (
    <div style={{ height: 480 }}>
      <ReactFlow
        nodes={nodes.map((n) =>
          toFlowNode(n, n.id === selectedNodeId, {
            acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
            nodeStat: nodeStats?.[n.id],
            isNext: n.id === nextNodeId,
          }),
        )}
        edges={edges.map(toFlowEdge)}
        nodeTypes={nodeTypes}
        edgeTypes={edgeTypes}
        onConnect={onConnect}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onPaneClick={() => onSelectNode(null)}
        deleteKeyCode={["Backspace", "Delete"]}
      >
        <Background />
        <Controls />
      </ReactFlow>
    </div>
  );
}

export function PipelineCanvas(props: React.ComponentProps<typeof PipelineCanvasInner>) {
  return (
    <ReactFlowProvider>
      <PipelineCanvasInner {...props} />
    </ReactFlowProvider>
  );
}
