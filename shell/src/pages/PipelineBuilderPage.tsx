// SPDX-License-Identifier: Apache-2.0
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import {
  useCreatePipeline,
  useInstanceInfo,
  useItem,
  usePipelineConfig,
  usePipelineOps,
  useSavePipeline,
} from "../api/hooks";
import { useAuth } from "../auth/useAuth";
import { useItemClient } from "../api/ItemClientProvider";
import type {
  PipelineCanvasNote,
  PipelineEdge,
  PipelineNode,
  PipelinePayload,
  PipelineRefreshPolicy,
  PipelineRun,
} from "../api/types";
import { hasPermission } from "../auth/permissions";
import { Banner } from "../ui/kit/Banner";
import { Button } from "../ui/kit/Button";
import { ConfigHistoryPanel } from "../builder/ConfigHistoryPanel";
import { useUndoableDraft } from "../builder/useUndoableDraft";
import { PipelineCanvas } from "../builder/pipeline/PipelineCanvas";
import { PipelineNodeInspector } from "../builder/pipeline/PipelineNodeInspector";
import {
  PipelinePalette,
  PIPELINE_OP_DND_TYPE,
  PIPELINE_PALETTE_SEARCH_ID,
} from "../builder/pipeline/PipelinePalette";
import { PipelinePreviewPanel } from "../builder/pipeline/PipelinePreviewPanel";
import { PipelineRunPanel } from "../builder/pipeline/PipelineRunPanel";
import { PipelineScheduleEditor } from "../builder/pipeline/PipelineScheduleEditor";
import { PipelineWebhookTrigger } from "../builder/pipeline/PipelineWebhookTrigger";
import { genNodeId, genNoteId, insertNodeOnEdge } from "../builder/pipeline/graphOps";
import { isPipelineValid, validatePipelineGraphLocally } from "../builder/pipeline/validation";
import { TriptychLayout } from "../shell/chrome/TriptychLayout";
import { t } from "../i18n";

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
  const instanceQuery = useInstanceInfo();
  const etlEnabled = instanceQuery.data?.etlEnabled === true;
  const configQuery = usePipelineConfig(pk ?? "", { enabled: pk !== null });
  const itemQuery = useItem(pk ?? "", { enabled: pk !== null });
  const createPipeline = useCreatePipeline();
  const savePipeline = useSavePipeline(pk ?? "");
  // SP-42/F-shell-pages-04 : cf. commentaire jumeau sur DatasetEditPage.tsx —
  // même doctrine, même résidu documenté. `pk === null` = brouillon jamais
  // encore créé, rien à verrouiller (la garde de création est un sujet
  // distinct, F-shell-pages-01/F-securite-autorisation-01).
  //
  // SP-42, revue finale (point 2, Critical) : quand `pk !== null`,
  // `itemQuery.data` est `undefined` pendant tout le chargement ET en cas
  // d'erreur — hasPermission renvoie alors `false`, verrouillant Enregistrer
  // pour la mauvaise raison. Le garde de rendu plus bas inclut désormais
  // itemQuery.isLoading/isError (même patron que DatasetEditPage.tsx:52-58).
  const readOnly = pk !== null && !hasPermission(itemQuery.data, "write");

  const { draft, setDraft, seedDraft, resetDraft, undo, redo, canUndo, canRedo } =
    useUndoableDraft<PipelinePayload>();
  const [selectedNodeId, setSelectedNodeId] = useState<string | null>(null);
  const [latestRun, setLatestRun] = useState<PipelineRun | null>(null);
  const [saveError, setSaveError] = useState<string | null>(null);

  useEffect(() => {
    if (pk === null) {
      seedDraft(EMPTY_PAYLOAD);
      return;
    }
    if (configQuery.data) seedDraft(configQuery.data);
  }, [pk, configQuery.data, seedDraft]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      if (!(e.metaKey || e.ctrlKey) || e.key.toLowerCase() !== "z") return;
      e.preventDefault();
      if (e.shiftKey) redo();
      else undo();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [undo, redo]);

  useEffect(() => {
    function onKeyDown(e: KeyboardEvent) {
      if (e.key !== "/") return;
      const target = document.activeElement;
      const isTextField =
        target instanceof HTMLInputElement ||
        target instanceof HTMLTextAreaElement ||
        (target instanceof HTMLElement && target.isContentEditable);
      if (isTextField) return;
      e.preventDefault();
      document.getElementById(PIPELINE_PALETTE_SEARCH_ID)?.focus();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  if (pk !== null && (configQuery.isLoading || itemQuery.isLoading))
    return <p role="status">{t("common.loading")}</p>;
  // SP-42 F-shell-pages-05 : sans cette garde, un pipeline existant dont le
  // chargement échoue (403 suite à une révocation de partage, item supprimé
  // mais lien conservé, panne réseau transitoire) s'affichait comme un
  // brouillon vide avec Enregistrer actif — un ré-enregistrement écrasait
  // silencieusement la configuration réelle. Même patron que
  // MapEditorPage.tsx pour son propre query.isError.
  //
  // SP-42, revue finale (point 2, Critical) : itemQuery.isError/!itemQuery.data
  // ajoutés pour la même raison que configQuery.isError — sans eux,
  // `readOnly` se calculait sur `itemQuery.data === undefined` (=> verrouillé
  // à tort) sans jamais bloquer le rendu complet.
  if (pk !== null && (configQuery.isError || itemQuery.isError || !itemQuery.data))
    return (
      <p role="alert" className="text-sm text-danger">
        {t("pipelineBuilder.notFound")}
      </p>
    );
  // D09, revue finale (Important) : instanceQuery (/v1/instance) et opsQuery
  // (/v1/pipelines/ops) sont deux requêtes indépendantes sans garantie
  // d'ordre. Le garde ci-dessous ne doit AFFIRMER quoi que ce soit sur
  // etlEnabled qu'une fois instanceQuery résolu — mais il ne suffit pas non
  // plus de laisser passer le rendu tant qu'il charge : si opsQuery résout
  // avant instanceQuery, rien ne bloquait alors le builder interactif de
  // s'afficher sur une instance où ETL est en réalité désactivé, avant de
  // basculer vers le message de désactivation une fois instanceQuery résolu
  // à son tour. Attendre explicitement instanceQuery avant même de regarder
  // opsQuery ferme cette fenêtre.
  if (instanceQuery.isLoading) return <p role="status">{t("common.loading")}</p>;
  // D09 : CORE_ETL_ENABLED=false → les routes pipeline ne sont pas montées
  // côté cœur (core/app/pipelines/routes.py), opsQuery termine en erreur
  // (404) et !opsQuery.data reste vrai pour toujours sans cette garde —
  // spinner infini.
  if (!etlEnabled) {
    return (
      <p role="status" className="text-sm text-ink-2">
        {t("pipelineBuilder.etlDisabled")}
      </p>
    );
  }
  if (opsQuery.isLoading || !opsQuery.data) return <p role="status">{t("common.loading")}</p>;
  if (draft === null) return <p role="status">{t("common.loading")}</p>;

  const catalog = opsQuery.data;
  // Narrowing from the `draft === null` guard above does not survive into the
  // nested `function` declarations below (onInsertOnEdge/onDropOnCanvas/
  // onAddViaPalette/onSave) — TypeScript resets control-flow narrowing at a
  // function boundary. Capturing it in a freshly-declared, non-nullable
  // const sidesteps that instead of asserting `draft!` at each read site.
  const currentDraft: PipelinePayload = draft;
  const validation = validatePipelineGraphLocally(draft.nodes, draft.edges, catalog);
  const valid = isPipelineValid(validation);
  const selectedNode = draft.nodes.find((n) => n.id === selectedNodeId) ?? null;

  function setNodes(nodes: PipelineNode[]) {
    setDraft((d) => (d ? { ...d, nodes } : d));
  }
  function setEdges(edges: PipelineEdge[]) {
    setDraft((d) => (d ? { ...d, edges } : d));
  }
  function setRefreshPolicy(refreshPolicy: PipelineRefreshPolicy | null) {
    setDraft((d) => (d ? { ...d, refreshPolicy } : d));
  }
  function setNotes(notes: PipelineCanvasNote[]) {
    setDraft((d) => (d ? { ...d, notes } : d));
  }
  function onAddNote() {
    setNotes([
      ...(currentDraft.notes ?? []),
      {
        id: genNoteId(),
        label: t("pipelineBuilder.newNoteLabel"),
        x: 40,
        y: 40,
        width: 200,
        height: 120,
      },
    ]);
  }
  function updateSelectedNodeParams(params: Record<string, unknown>) {
    if (!selectedNode) return;
    setDraft((d) =>
      d
        ? { ...d, nodes: d.nodes.map((n) => (n.id === selectedNode.id ? { ...n, params } : n)) }
        : d,
    );
  }
  function onInsertOnEdge(edgeId: string, op: string) {
    const kind = catalog[op]?.kind ?? "transform";
    const result = insertNodeOnEdge(currentDraft.nodes, currentDraft.edges, edgeId, {
      id: genNodeId(),
      kind,
      op,
      x: 0,
      y: 0,
      params: {},
      title: op,
    });
    setDraft((d) => (d ? { ...d, ...result } : d));
  }
  function onDropOnCanvas(op: string, position: { x: number; y: number }) {
    const kind = catalog[op]?.kind ?? "transform";
    setNodes([
      ...currentDraft.nodes,
      { id: genNodeId(), kind, op, x: position.x, y: position.y, params: {}, title: op },
    ]);
  }
  // REV-060 : repli clic sur PipelinePalette — mêmes coordonnées relatives
  // au canevas (pas de mesure de sa position réelle ici, comme le drop
  // existant qui utilise directement clientX/clientY), en décalant chaque
  // ajout successif pour ne pas empiler les nœuds exactement l'un sur
  // l'autre.
  function onAddViaPalette(op: string) {
    onDropOnCanvas(op, { x: 40, y: 40 + currentDraft.nodes.length * 90 });
  }

  async function onSave() {
    setSaveError(null);
    try {
      if (pk === null) {
        const item = await createPipeline.mutateAsync({
          title: initialTitle ?? "",
          owner: username ?? "",
          pipeline: currentDraft,
        });
        navigate(`/pipelines/${item.pk}/edit`, { replace: true });
        return;
      }
      await savePipeline.mutateAsync(currentDraft);
    } catch (e) {
      setSaveError(e instanceof Error ? e.message : t("actions.saveFailed"));
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
          label: t("pipelineBuilder.stepsLabel"),
          content: <PipelinePalette onAdd={onAddViaPalette} />,
        }}
        work={{
          id: "canvas",
          label: t("appBuilder.canvasLabel"),
          content: (
            <div className="flex h-full flex-col overflow-hidden">
              <div className="flex items-center justify-between border-b border-rule p-2">
                <h2 className="text-lg font-semibold text-ink">
                  {initialTitle ?? t("pipelineBuilder.defaultTitle")}
                </h2>
                <div className="flex items-center gap-1">
                  <Button size="sm" variant="outline" disabled={!canUndo} onClick={undo}>
                    {t("pipelineBuilder.undo")}
                  </Button>
                  <Button size="sm" variant="outline" disabled={!canRedo} onClick={redo}>
                    {t("pipelineBuilder.redo")}
                  </Button>
                  <Button size="sm" variant="outline" onClick={onAddNote}>
                    {t("pipelineBuilder.addNoteButton")}
                  </Button>
                </div>
              </div>
              {validation.graphErrors.length > 0 && (
                <div className="p-2">
                  <Banner variant="danger">
                    <ul className="list-disc pl-4">
                      {validation.graphErrors.map((err) => (
                        <li key={err}>{err}</li>
                      ))}
                    </ul>
                  </Banner>
                </div>
              )}
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
                  nodeErrors={validation.nodeErrors}
                  notes={draft.notes ?? []}
                  onNotesChange={setNotes}
                />
              </div>
            </div>
          ),
        }}
        inspect={{
          id: "props",
          label: t("appBuilder.propertiesLabel"),
          content: (
            <div className="flex flex-col gap-1 p-2">
              {selectedNode && catalog[selectedNode.op] && (
                <>
                  <p className="mb-1 text-xs font-medium text-ink-2">
                    {t("pipelineBuilder.selectedNodeLabel")}
                  </p>
                  <PipelineNodeInspector
                    key={selectedNode.id}
                    node={selectedNode}
                    opEntry={catalog[selectedNode.op]}
                    errors={validation.nodeErrors[selectedNode.id] ?? []}
                    onChange={updateSelectedNodeParams}
                  />
                  {pk !== null && !readOnly && (
                    <PipelinePreviewPanel
                      pipelineId={pk}
                      nodeId={selectedNode.id}
                      draft={draft}
                      isDraftStale={configQuery.data !== undefined && configQuery.data !== draft}
                    />
                  )}
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                    {t("pipelineBuilder.executionLabel")}
                  </p>
                  <PipelineRunPanel pipelineId={pk} onLatestRunChange={setLatestRun} />
                </>
              )}
              {pk !== null && (
                <>
                  <p className="mb-1 mt-3 text-xs font-medium text-ink-2">
                    {t("pipelineBuilder.scheduleLabel")}
                  </p>
                  <PipelineScheduleEditor
                    value={draft.refreshPolicy ?? null}
                    onChange={setRefreshPolicy}
                  />
                  <PipelineWebhookTrigger pipelineId={pk} />
                </>
              )}
              {pk !== null && (
                <div className="mt-3">
                  <ConfigHistoryPanel
                    pk={pk}
                    currentVersion={null}
                    onRestored={async () => resetDraft(await client.getPipelineConfig(pk))}
                  />
                </div>
              )}
              <div className="mt-3 flex flex-col gap-2 border-t border-rule pt-3">
                <Button
                  size="sm"
                  className="w-fit"
                  onClick={() => void onSave()}
                  disabled={
                    !valid || createPipeline.isPending || savePipeline.isPending || readOnly
                  }
                >
                  {t("common.save")}
                </Button>
                {readOnly && <p className="text-xs text-ink-2">{t("locked.needWrite")}</p>}
                {!valid && !readOnly && (
                  <p className="text-xs text-ink-2">{t("pipelineBuilder.saveDisabledReason")}</p>
                )}
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
