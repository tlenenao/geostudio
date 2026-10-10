// SPDX-License-Identifier: Apache-2.0
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Background,
  BaseEdge,
  Controls,
  EdgeLabelRenderer,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  ReactFlowProvider,
  getBezierPath,
  type AriaLabelConfig,
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
  PipelineCanvasNote,
  PipelineEdge,
  PipelineNode,
  PipelineNodeStat,
  PipelineOpsCatalog,
  PipelineRunStatus,
} from "../../api/types";
import { genEdgeId, hasIncomingEdge, topologicalOrder, wouldCreateCycle } from "./graphOps";
import { usePanelTrigger } from "../../ui/kit/usePanelTrigger";
import { plural, t } from "../../i18n";
import { jobStatusLabel } from "../../lib/jobStatusLabel";

// SP-B12c : pas de token catégoriel à 3 valeurs dans tokens.css — ok/warn/
// accent réutilisés ici pour leur distinction visuelle (vert/ambre/teal),
// pas pour leur sens sémantique de statut.
// `!` : React Flow pose `.react-flow__node.selectable:focus-visible { outline: none }` (plus
// spécifique, chargé après) — sans lui l'anneau n'apparaît jamais (t01b-002, vu au rejeu réel).
const FOCUS_RING =
  "focus-visible:outline-2! focus-visible:outline-offset-2! focus-visible:outline-accent!";

const KIND_COLOR: Record<PipelineNode["kind"], string> = {
  reader: "border-ok bg-ok-soft",
  transform: "border-warn bg-warn-soft",
  writer: "border-accent bg-accent-soft",
};

// Bagage porté par le `data` de chaque nœud React Flow (SP-15g) — étend
// PipelineNode (format fil) avec ce que seul le canvas a besoin de savoir
// pour se rendre : accepte-t-il une seconde entrée, où en est-il dans le run
// en cours (§5.1/§5.2 du design).
type CanvasNodeData = PipelineNode & {
  acceptsSecondaryInput: boolean;
  nodeStat?: PipelineNodeStat;
  isNext: boolean;
  errorCount: number;
  onDelete: (nodeId: string) => void;
  onStartConnect: (nodeId: string) => void;
  isConnectingSource: boolean;
};

function PipelineNodeBox({ data, selected }: NodeProps) {
  const node = data as unknown as CanvasNodeData;
  return (
    <div
      className={`relative rounded-md border-2 px-3 py-2 text-xs text-ink ${KIND_COLOR[node.kind]} ${selected ? "ring-2 ring-accent" : ""} ${node.errorCount > 0 ? "border-danger" : ""} ${node.isConnectingSource ? "ring-2 ring-accent" : ""}`}
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
      <div className="text-xs text-ink-2">{node.op}</div>
      <Handle type="source" position={Position.Right} />
      {node.errorCount > 0 && (
        <span
          role="status"
          aria-label={t(
            plural(
              node.errorCount,
              "pipelineCanvas.nodeErrorAriaOne",
              "pipelineCanvas.nodeErrorAriaMany",
            ),
            { count: node.errorCount },
          )}
          className="absolute -left-2 -top-2 flex h-4 w-4 items-center justify-center rounded-full bg-danger text-2xs text-surface"
        >
          !
        </span>
      )}
      {node.nodeStat && (
        <span
          role="status"
          className="absolute -right-2 -top-2 rounded-full bg-ok px-1.5 py-0.5 text-2xs text-surface"
        >
          {node.nodeStat.rowCount ?? "?"}
        </span>
      )}
      {node.isNext && !node.nodeStat && (
        <span
          role="status"
          aria-label={t("pipelineCanvas.runningAria")}
          className="absolute -right-2 -top-2 h-3 w-3 animate-spin rounded-full border-2 border-accent border-t-transparent"
        />
      )}
      <button
        type="button"
        aria-label={t("pipelineCanvas.deleteNodeAria", { title: node.title ?? node.op })}
        className="absolute -bottom-3 -right-3 flex h-6 w-6 items-center justify-center rounded-full border border-rule bg-surface text-2xs leading-none text-ink-2 hover:bg-sunken hover:text-danger"
        onClick={(e) => {
          e.stopPropagation();
          node.onDelete(node.id);
        }}
      >
        ×
      </button>
      <button
        type="button"
        aria-label={t("pipelineCanvas.startConnectAria", { title: node.title ?? node.op })}
        aria-pressed={node.isConnectingSource}
        className="absolute -bottom-3 -left-3 flex h-6 w-6 items-center justify-center rounded-full border border-rule bg-surface text-2xs leading-none text-ink-2 hover:bg-sunken"
        onClick={(e) => {
          e.stopPropagation();
          node.onStartConnect(node.id);
        }}
      >
        ↝
      </button>
    </div>
  );
}

type CanvasNoteData = PipelineCanvasNote & {
  onLabelChange: (id: string, label: string) => void;
  readOnly?: boolean;
};

function CanvasNoteBox({ data }: NodeProps) {
  const note = data as unknown as CanvasNoteData;
  return (
    <div
      style={{ width: note.width, height: note.height }}
      className="rounded-md border-2 border-dashed border-rule bg-sunken/40 p-2"
    >
      <input
        aria-label={t("pipelineCanvas.noteLabelAria")}
        className="h-6 w-full bg-transparent text-xs font-medium text-ink-2 outline-none"
        value={note.label}
        onChange={(e) => note.onLabelChange(note.id, e.target.value)}
        disabled={note.readOnly}
      />
    </div>
  );
}

function toFlowNoteNode(
  n: PipelineCanvasNote,
  onLabelChange: (id: string, label: string) => void,
  readOnly?: boolean,
): Node {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { ...n, onLabelChange, readOnly } as unknown as Record<string, unknown>,
    type: "canvasNote",
    zIndex: -1,
  };
}

type InsertEdgeData = {
  role?: string;
  onInsert: (edgeId: string, op: string) => void;
  opsCatalog: PipelineOpsCatalog;
  readOnly?: boolean;
};

// Les types d'arête/nœud doivent être stables (module scope) : un composant
// recréé à chaque rendu remonte à chaque changement de sélection et perd son
// état (menu « + » ouvert, focus).
function InsertOnEdgeButton({ id, sourceX, sourceY, targetX, targetY, data }: EdgeProps) {
  const { role, onInsert, opsCatalog, readOnly } = data as unknown as InsertEdgeData;
  const [open, setOpen] = useState(false);
  const insertMenu = usePanelTrigger(open);
  const [edgePath, labelX, labelY] = getBezierPath({ sourceX, sourceY, targetX, targetY });
  const insertableTransforms = Object.entries(opsCatalog)
    .filter(([, entry]) => entry.kind === "transform")
    .map(([op]) => op)
    .sort();
  return (
    <>
      <BaseEdge
        id={id}
        path={edgePath}
        style={role === "secondary" ? { strokeDasharray: "4 4" } : undefined}
      />
      <EdgeLabelRenderer>
        <div
          style={{
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px,${labelY}px)`,
            pointerEvents: "all",
          }}
          // Un clic sur « + » n'est pas une sélection de l'arête (le portail
          // fait remonter l'événement React jusqu'au wrapper de l'arête).
          role="presentation"
          onClick={(e) => e.stopPropagation()}
        >
          <button
            type="button"
            aria-label={t("pipelineCanvas.insertStepAria")}
            aria-expanded={insertMenu.triggerProps["aria-expanded"]}
            aria-controls={insertMenu.triggerProps["aria-controls"]}
            className="h-6 w-6 rounded-full border border-rule bg-surface text-xs leading-none text-ink hover:bg-sunken"
            onClick={() => setOpen((o) => !o)}
            disabled={readOnly}
          >
            +
          </button>
          {open && !readOnly && (
            // role="menu" conservé (plus spécifique que role="region" du
            // hook générique) — seul l'id du panneau est câblé ici, cf.
            // consigne explicite du brief pour ce site.
            <ul
              id={insertMenu.panelId}
              role="menu"
              className="absolute z-10 mt-1 rounded border border-rule bg-surface text-xs shadow"
            >
              {insertableTransforms.map((op) => (
                <li key={op}>
                  <button
                    type="button"
                    role="menuitem"
                    className="block w-full whitespace-nowrap px-2 py-1 text-left hover:bg-sunken"
                    onClick={() => {
                      onInsert(id, op);
                      setOpen(false);
                    }}
                  >
                    {op}
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
  extra: {
    acceptsSecondaryInput: boolean;
    nodeStat?: PipelineNodeStat;
    isNext: boolean;
    errorCount: number;
    onDelete: (nodeId: string) => void;
    onStartConnect: (nodeId: string) => void;
    isConnectingSource: boolean;
  },
): Node {
  return {
    id: n.id,
    position: { x: n.x, y: n.y },
    data: { ...n, ...extra } as unknown as Record<string, unknown>,
    type: "pipelineNode",
    selected,
    // P32.04 : le wrapper React Flow porte le focus clavier, pas notre boîte.
    className: FOCUS_RING,
  };
}
// Référence stable : React Flow ré-abonne ses écouteurs clavier à chaque nouveau tableau.
const DELETE_KEYS = ["Backspace", "Delete"];
const NODE_TYPES = { pipelineNode: PipelineNodeBox, canvasNote: CanvasNoteBox };
const EDGE_TYPES = { insertable: InsertOnEdgeButton };

function toFlowEdge(
  e: PipelineEdge,
  selected: boolean,
  label: string,
  extra: Omit<InsertEdgeData, "role">,
): Edge {
  return {
    id: e.id,
    source: e.from,
    target: e.to,
    type: "insertable",
    selected,
    ariaLabel: label,
    className: "focus-visible:outline-none [&:focus-visible_.react-flow__edge-path]:stroke-accent",
    targetHandle: e.role === "secondary" ? "secondary" : "primary",
    data: { role: e.role, ...extra },
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
  nodeErrors,
  notes,
  onNotesChange,
  readOnly,
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
  runStatus?: PipelineRunStatus;
  nodeErrors?: Record<string, string[]>;
  notes: PipelineCanvasNote[];
  onNotesChange: (notes: PipelineCanvasNote[]) => void;
  readOnly?: boolean;
}) {
  const onConnect: OnConnect = useCallback(
    (connection) => {
      if (readOnly) return;
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
    [nodes, edges, onEdgesChange, readOnly],
  );

  const handleNodesChange = useCallback(
    (changes: NodeChange[]) => {
      // D55 : en lecture seule, `nodesDraggable={false}` (cf. <ReactFlow>
      // plus bas) empêche déjà React Flow d'émettre des changements
      // "position" par drag natif, et `deleteKeyCode={null}` l'empêche
      // d'émettre des changements "remove" au clavier. Ce filtre est une
      // seconde ligne de défense (déjà écartée dans le pire des cas testé :
      // la suppression au clic sur le bouton × passe par `deleteNode`,
      // jamais par ici — gardée séparément ci-dessous).
      const effectiveChanges = readOnly
        ? changes.filter((c) => c.type !== "remove" && c.type !== "add")
        : changes;
      let nextNodes = nodes;
      let nextNotes = notes;
      for (const change of effectiveChanges) {
        if (change.type === "position" && change.position) {
          const isNote = change.id.startsWith("note-");
          if (isNote) {
            nextNotes = nextNotes.map((n) =>
              n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n,
            );
          } else {
            nextNodes = nextNodes.map((n) =>
              n.id === change.id ? { ...n, x: change.position!.x, y: change.position!.y } : n,
            );
          }
        }
        if (change.type === "remove") {
          if (change.id.startsWith("note-"))
            nextNotes = nextNotes.filter((n) => n.id !== change.id);
          else nextNodes = nextNodes.filter((n) => n.id !== change.id);
        }
        // Ne réagit qu'à l'événement "sélectionné" (jamais "déselectionné") :
        // un clic sur un nouveau nœud émet deux changements dans un ordre non
        // garanti (ancien nœud selected:false, nouveau selected:true) — ne
        // traiter que selected:true rend la sélection robuste à cet ordre.
        // La désélection (clic sur le fond) passe par onPaneClick ci-dessous.
        // Une zone annotée (préfixe "note-") ne devient jamais le nœud actif.
        if (change.type === "select" && change.selected && !change.id.startsWith("note-")) {
          onSelectNode(change.id);
        }
      }
      if (nextNodes !== nodes) onNodesChange(nextNodes);
      if (nextNotes !== notes) onNotesChange(nextNotes);
    },
    [nodes, notes, onNodesChange, onNotesChange, onSelectNode, readOnly],
  );

  // P32.02 : les arêtes sont reconstruites à chaque rendu ; sans cet état,
  // React Flow n'en voit jamais une « selected » et Suppr ne la retire pas.
  const [selectedEdgeId, setSelectedEdgeId] = useState<string | null>(null);

  const handleEdgesChange = useCallback(
    (changes: EdgeChange[]) => {
      for (const c of changes) {
        if (c.type === "select")
          setSelectedEdgeId((cur) => (c.selected ? c.id : cur === c.id ? null : cur));
      }
      // D55 : même raisonnement que handleNodesChange — deleteKeyCode={null}
      // empêche déjà l'émission d'un changement "remove" au clavier en
      // lecture seule ; ce garde explicite est la seconde ligne de défense.
      if (readOnly) return;
      const removedIds = new Set(changes.filter((c) => c.type === "remove").map((c) => c.id));
      if (removedIds.size) onEdgesChange(edges.filter((e) => !removedIds.has(e.id)));
    },
    [edges, onEdgesChange, readOnly],
  );

  const deleteNode = useCallback(
    (nodeId: string) => {
      // D55 : seul chemin réel de suppression d'un nœud (le bouton ×
      // appelle `onDelete` = cette fonction directement — jamais via
      // `handleNodesChange`, qui ne voit un changement "remove" que pour la
      // suppression clavier). Sans ce garde, le filtre ci-dessus sur
      // `handleNodesChange` ne suffit pas à couvrir D55.
      if (readOnly) return;
      onNodesChange(nodes.filter((n) => n.id !== nodeId));
      onEdgesChange(edges.filter((e) => e.from !== nodeId && e.to !== nodeId));
    },
    [nodes, edges, onNodesChange, onEdgesChange, readOnly],
  );

  const [connectingFromId, setConnectingFromId] = useState<string | null>(null);

  const completeConnection = useCallback(
    (targetId: string) => {
      // D55 : chemin de connexion réellement exercé par le clic accessible
      // (bouton ↝ puis clic sur le nœud cible) — c'est celui-là, pas
      // `onConnect` (réservé au drag natif), que les tests de ce fichier
      // exercent. Sans ce garde, `onConnect` seul ne suffit pas à fermer
      // D55.
      if (readOnly) return;
      if (!connectingFromId) return;
      setConnectingFromId(null);
      if (hasIncomingEdge(edges, targetId)) return;
      if (wouldCreateCycle(nodes, edges, { from: connectingFromId, to: targetId })) return;
      onEdgesChange([...edges, { id: genEdgeId(), from: connectingFromId, to: targetId }]);
    },
    [readOnly, connectingFromId, nodes, edges, onEdgesChange],
  );

  useEffect(() => {
    if (!connectingFromId) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") setConnectingFromId(null);
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [connectingFromId]);

  // P32.01 : Entrée/Espace sur le nœud cible achève la connexion amorcée par ↝
  // (le clic passe par onNodeClick, le clavier par ce gestionnaire).
  function onCanvasKeyDown(e: React.KeyboardEvent) {
    if (!connectingFromId || (e.key !== "Enter" && e.key !== " ")) return;
    const el = (e.target as HTMLElement).closest<HTMLElement>(".react-flow__node");
    if (!el || e.target !== el) return;
    const id = el.dataset.id;
    if (!id || id === connectingFromId || id.startsWith("note-")) return;
    e.preventDefault();
    completeConnection(id);
  }

  const titleOf = useMemo(() => new Map(nodes.map((n) => [n.id, n.title ?? n.op])), [nodes]);
  const ariaLabelConfig = useMemo<Partial<AriaLabelConfig>>(
    () => ({
      "node.a11yDescription.default": t("pipelineCanvas.nodeA11yDescription"),
      "node.a11yDescription.keyboardDisabled": t("pipelineCanvas.nodeA11yDescription"),
      "node.a11yDescription.ariaLiveMessage": ({ direction, x, y }) =>
        t("pipelineCanvas.nodeMovedLive", { direction, x: Math.round(x), y: Math.round(y) }),
      "edge.a11yDescription.default": t("pipelineCanvas.edgeA11yDescription"),
      "controls.ariaLabel": t("pipelineCanvas.controlsAria"),
      "controls.zoomIn.ariaLabel": t("pipelineCanvas.zoomIn"),
      "controls.zoomOut.ariaLabel": t("pipelineCanvas.zoomOut"),
      "controls.fitView.ariaLabel": t("pipelineCanvas.fitView"),
      "controls.interactive.ariaLabel": t("pipelineCanvas.toggleInteractivity"),
      "minimap.ariaLabel": t("pipelineCanvas.minimapAria"),
      "handle.ariaLabel": t("pipelineCanvas.handleAria"),
    }),
    [],
  );

  const order = topologicalOrder(nodes, edges);
  const nextNodeId = runStatus === "running" ? order.find((id) => !nodeStats?.[id]) : undefined;

  return (
    <div className="h-full" role="presentation" onKeyDown={onCanvasKeyDown}>
      {/* Région live permanente : une région insérée avec son contenu n'est pas annoncée de façon fiable. */}
      <p
        role="status"
        aria-label={
          runStatus
            ? t("pipelineCanvas.runStatusAria", { status: jobStatusLabel(runStatus) })
            : undefined
        }
        className="sr-only"
      >
        {runStatus ? jobStatusLabel(runStatus) : ""}
      </p>
      <ReactFlow
        nodes={[
          ...nodes.map((n) =>
            toFlowNode(n, n.id === selectedNodeId, {
              acceptsSecondaryInput: opsCatalog[n.op]?.acceptsSecondaryInput ?? false,
              nodeStat: nodeStats?.[n.id],
              isNext: n.id === nextNodeId,
              errorCount: nodeErrors?.[n.id]?.length ?? 0,
              onDelete: deleteNode,
              onStartConnect: (id) => setConnectingFromId(id),
              isConnectingSource: n.id === connectingFromId,
            }),
          ),
          ...notes.map((n) =>
            toFlowNoteNode(
              n,
              (id, label) => {
                // D55, revue finale Vague C (point 2) : chemin direct
                // (l'input de la zone annotée n'émet aucun NodeChange géré
                // par handleNodesChange plus haut) — sans ce garde,
                // `disabled` sur l'input seul ne suffirait pas à couvrir un
                // événement forcé (ex. testing-library, extension tierce).
                if (readOnly) return;
                onNotesChange(notes.map((x) => (x.id === id ? { ...x, label } : x)));
              },
              readOnly,
            ),
          ),
        ]}
        edges={edges.map((e) =>
          toFlowEdge(
            e,
            e.id === selectedEdgeId,
            t("pipelineCanvas.edgeAria", {
              source: titleOf.get(e.from) ?? e.from,
              target: titleOf.get(e.to) ?? e.to,
            }),
            { onInsert: onInsertOnEdge, opsCatalog, readOnly },
          ),
        )}
        ariaLabelConfig={ariaLabelConfig}
        nodeTypes={NODE_TYPES}
        edgeTypes={EDGE_TYPES}
        onConnect={onConnect}
        onNodesChange={handleNodesChange}
        onEdgesChange={handleEdgesChange}
        onNodeClick={(_, flowNode) => {
          if (
            connectingFromId &&
            flowNode.id !== connectingFromId &&
            !flowNode.id.startsWith("note-")
          )
            completeConnection(flowNode.id);
        }}
        onPaneClick={() => onSelectNode(null)}
        deleteKeyCode={readOnly ? null : DELETE_KEYS}
        nodesDraggable={!readOnly}
        nodesConnectable={!readOnly}
      >
        <Background />
        <Controls />
        <MiniMap pannable zoomable />
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
