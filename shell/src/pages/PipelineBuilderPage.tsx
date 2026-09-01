// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreatePipeline,
  usePipelineConfig,
  usePipelineOps,
  useSavePipeline,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import type {
  PipelineEdge,
  PipelineNode,
  PipelinePayload,
  PipelineRefreshPolicy,
  PipelineRun,
} from "../api/types";
import { Button } from "../ui/kit/Button";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { PipelineCanvas } from "../builder/pipeline/PipelineCanvas";
import { PipelineNodeInspector } from "../builder/pipeline/PipelineNodeInspector";
import { PipelinePalette, PIPELINE_OP_DND_TYPE } from "../builder/pipeline/PipelinePalette";
import { PipelinePreviewPanel } from "../builder/pipeline/PipelinePreviewPanel";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { genNodeId, insertNodeOnEdge } from "../builder/pipeline/graphOps";
import { isPipelineValid, validatePipelineGraphLocally } from "../builder/pipeline/validation";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";

const EMPTY_PAYLOAD: PipelinePayload = { nodes: [], edges: [] };

// pk === null : brouillon local (/pipelines/new, design SP-15b §2.2) —
// rien n'est persisté avant le premier "Enregistrer" (choix de session : le
// validateur serveur exige déjà ≥1 reader/≥1 writer, donc il n'existe pas de
// payload trivial à créer immédiatement comme pour app/dashboard/map/site).
export function PipelineBuilderPage({
  pk,
  initialTitle,
}: {
  pk: string | null;
  initialTitle?: string;
}) {
  const navigate = useNavigate();
  const { username } = useAuth();
  const client = useItemClient();
  const opsQuery = usePipelineOps();
  const configQuery = usePipelineConfig(pk ?? "", { enabled: pk !== null });
  const createPipeline = useCreatePipeline();
  const savePipeline = useSavePipeline(pk ?? "");

  const [draft, setDraft] = useState<PipelinePayload>(EMPTY_PAYLOAD);
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk !== null && configQuery.data) setDraft(configQuery.data);
  }, [pk, configQuery.data]);

  if (pk !== null && configQuery.isLoading) return <p role="status">Chargement…</p>;
  if (opsQuery.isLoading || !opsQuery.data) return <p role="status">Chargement…</p>;

  const catalog = opsQuery.data;
  const validation = validatePipelineGraphLocally(draft.nodes, draft.edges, catalog);
  const valid = isPipelineValid(validation);
  const selectedNode = draft.nodes.find((n) => n.id === selectedNodeId) ?? null;

  function setNodes(nodes: PipelineNode[]) {
    setDraft((d) => ({ ...d, nodes }));
  }
  function setEdges(edges: PipelineEdge[]) {
    setDraft((d) => ({ ...d, edges }));
  }
  function setRefreshPolicy(refreshPolicy: PipelineRefreshPolicy | null) {
    setDraft((d) => ({ ...d, refreshPolicy }));
  }
  function updateSelectedNodeParams(params: Record<string, unknown>) {
    if (!selectedNode) return;
    setNodes(draft.nodes.map((n) => (n.id === selectedNode.id ? { ...n, params } : n)));
  }
  function onInsertOnEdge(edgeId: string, op: string) {
    const kind = catalog[op]?.kind ?? "transform";
    const result = insertNodeOnEdge(draft.nodes, draft.edges, edgeId, {
      id: genNodeId(),
      kind,
      op,
      x: 0,
      y: 0,
      params: {},
      title: op,
    });
    setDraft(result);
  }
  function onDropOnCanvas(op: string, position: { x: number; y: number }) {
    const kind = catalog[op]?.kind ?? "transform";
    setNodes([
      ...draft.nodes,
      { id: genNodeId(), kind, op, x: position.x, y: position.y, params: {}, title: op },
    ]);
  }

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createPipeline.mutateAsync({
          title: initialTitle ?? "",
          owner: username ?? "",
          pipeline: draft,
        });
        navigate(`/pipelines/${item.pk}/edit`, { replace: true });
        return;
      }
      await savePipeline.mutateAsync(draft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : "Échec de l'enregistrement.");
    }
  }

  return (
    <div
      className="-m-6 flex flex-1 flex-col overflow-hidden"
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        const op = e.dataTransfer.getData(PIPELINE_OP_DND_TYPE);
        if (!op) return;
        onDropOnCanvas(op, { x: e.clientX, y: e.clientY });
      }}
    >
      <TriptychLayout
        defaultTabId="canvas"
        browse={{
          id: "steps",
          label: "Étapes",
          content: <PipelinePalette />,
        }}
        work={{
          id: "canvas",
          label: "Canevas",
          content: (
            <div className="flex h-full flex-col overflow-hidden">
              <div className="border-b border-rule p-2">
                <h2 className="text-lg font-semibold text-ink">{initialTitle ?? "Pipeline"}</h2>
              </div>
              <div className="flex-1 overflow-auto p-2">
                <PipelineCanvas
                  nodes={draft.nodes}
                  edges={draft.edges}
                  selectedNodeId={selectedNodeId}
                  onSelectNode={setSelectedNodeId}
                  onNodesChange={setNodes}
                  onEdgesChange={setEdges}
                  onInsertOnEdge={onInsertOnEdge}
                  opsCatalog={catalog}
                  nodeStats={latestRun?.nodeStats}
                  runStatus={latestRun?.status}
                />
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "props",
          label: "Propriétés",
          content: (
            <div className="flex flex-col gap-1 p-2">
              {selectedNode && catalog[selectedNode.op] && (
                <>
                  <p className="mb-1 text-xs font-medium text-ink-2">Nœud sélectionné</p>
                  <PipelineNodeInspector
                    key={selectedNode.id}
                    node={selectedNode}
                    opEntry={catalog[selectedNode.op]}
                    errors={validation.nodeErrors[selectedNode.id] ?? []}
                    onChange={updateSelectedNodeParams}
                  />
                  {pk !== null && <PipelinePreviewPanel pipelineId={pk} nodeId={selectedNode.id} />}
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Exécution</p>
                  <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">Planification</p>
                  <PipelineScheduleEditor
                    value={draft.refreshPolicy ?? null}
                    onChange={setRefreshPolicy}
                  />
                </>
              )}
              {pk !== null && (
                <div className="mt-3">
                  <ConfigHistoryPanel
                    pk={pk}
                    currentVersion={null}
                    onRestored={async () => setDraft(await client.getPipelineConfig(pk))}
                  />
                </div>
              )}
              <div className="mt-3 flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={!valid || createPipeline.isPending || savePipeline.isPending}
                >
                  Enregistrer
                </Button>
                {saveError && (
                  <p role="alert" className="text-xs text-danger">
                    {saveError}
                  </p>
                )}
              </div>
            </div>
          ),
        }}
      />
    </div>
  );
}
