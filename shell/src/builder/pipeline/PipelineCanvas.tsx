// SPDX-License-Identifier: Apache-2.0
import { useCallback, useState } from "react";
import {
  Background, Controls, EdgeLabelRenderer, Handle, Position, ReactFlow, ReactFlowProvider,
  getBezierPath,
  type Edge, type EdgeChange, type EdgeProps, type Node, type NodeChange, type NodeProps, type OnConnect,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PipelineEdge, PipelineNode } from "../../api/types";
import { genEdgeId, hasIncomingEdge, wouldCreateCycle } from "./graphOps";

// Les 5 op transform.* insérables sur une arête (cf. plan Task 6 — clic sur
// le "+" d'une arête, pas de drag-drop précis sur le tracé SVG). SP-15c
// ajoute les 5 op spatiales étage 1 ; writer.dataset n'y figure jamais (ce
// n'est pas une op transform, jamais candidate à cette liste, cf. design §5).
const INSERTABLE_TRANSFORMS: { op: string; label: string }[] = [
  { op: "transform.filter", label: "Filtrer" },
  { op: "transform.select", label: "Sélectionner" },
  { op: "transform.derive", label: "Dériver" },
  { op: "transform.aggregate", label: "Agréger" },
  { op: "transform.join", label: "Joindre" },
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

function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as PipelineNode;
  return (
    <div className={`rounded-md border-2 px-3 py-2 text-xs ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-blue-500" : ""}`}>
      <Handle type="target" position={Position.Left} />
      <div className="font-medium">{node.title ?? node.op}</div>
      <div className="text-[10px] text-slate-500">{node.op}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

function InsertOnEdgeButton({ id, sourceX, sourceY, targetX, targetY, onInsert }: EdgeProps & { onInsert: (edgeId: string, op: string) => void }) {
  const [open, setOpen] = useState(false);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  return (
    <>
      <path id={id} className="react-flow__edge-path" d={edgePath} />
      <EdgeLabelRenderer>
        <div style={{ position: "absolute", transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`, pointerEvents: "all" }}>
          <button
            type="button"
            aria-label="Insérer une étape sur cette arête"
            className="h-5 w-5 rounded-full border border-slate-400 bg-white text-xs leading-none hover:bg-slate-100"
            onClick={() => setOpen((o) => !o)}
          >
            +
          </button>
          {open && (
            <ul role="menu" className="absolute z-10 mt-1 rounded border border-slate-300 bg-white text-xs shadow">
              {INSERTABLE_TRANSFORMS.map((t) => (
                <li key={t.op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-slate-100"
                    onClick={() => { onInsert(id, t.op); setOpen(false); }}
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

function toFlowNode(n: PipelineNode, selected: boolean): Node {
  return { id: n.id, position: { x: n.x, y: n.y }, data: n as unknown as Record<string, unknown>, type: "pipelineNode", selected };
}
function toFlowEdge(e: PipelineEdge): Edge {
  return { id: e.id, source: e.from, target: e.to, type: "insertable" };
}

function PipelineCanvasInner({
  nodes, edges, selectedNodeId, onSelectNode, onNodesChange, onEdgesChange, onInsertOnEdge,
}: {
  nodes: PipelineNode[];
  edges: PipelineEdge[];
  selectedNodeId: string | null;
  onSelectNode: (id: string | null) => void;
  onNodesChange: (nodes: PipelineNode[]) => void;
  onEdgesChange: (edges: PipelineEdge[]) => void;
  onInsertOnEdge: (edgeId: string, op: string) => void;
}) {
  const nodeTypes = { pipelineNode: PipelineNodeBox };
  const edgeTypes = { insertable: (props: EdgeProps) => <InsertOnEdgeButton {...props} onInsert={onInsertOnEdge} /> };

  const onConnect: OnConnect = useCallback((connection) => {
    if (!connection.source || !connection.target) return;
    if (hasIncomingEdge(edges, connection.target)) return; // garde §3.4 : ≤ 1 arête entrante
    if (wouldCreateCycle(nodes, edges, { from: connection.source, to: connection.target })) return;
    onEdgesChange([...edges, { id: genEdgeId(), from: connection.source, to: connection.target }]);
  }, [nodes, edges, onEdgesChange]);

  const handleNodesChange = useCallback((changes: NodeChange[]) => {
    let next = nodes;
    for (const change of changes) {
      if (change.type === "position" && change.position) {
        next = next.map((n) => (n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n));
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
  }, [nodes, onNodesChange, onSelectNode]);

  const handleEdgesChange = useCallback((changes: EdgeChange[]) => {
    const removedIds = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
    if (removedIds.size) onEdgesChange(edges.filter((e) => !removedIds.has(e.id)));
  }, [edges, onEdgesChange]);

  return (
    <div style={{ height: 480 }}>
      <ReactFlow
        nodes={nodes.map((n) => toFlowNode(n, n.id === selectedNodeId))}
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
