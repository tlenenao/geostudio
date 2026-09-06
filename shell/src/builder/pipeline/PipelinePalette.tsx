// SPDX-License-Identifier: Apache-2.0
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";
import { t } from "../../i18n";

export const PIPELINE_OP_DND_TYPE = "application/x-geostudio-pipeline-op";

const SECTION_LABEL: Record<PipelineNodeKind, string> = {
  reader: t("pipelinePalette.sectionSources"),
  transform: t("pipelinePalette.sectionTransforms"),
  writer: t("pipelinePalette.sectionWriters"),
};

// REV-060 (backlog 2026-09-04) : le drag-and-drop était l'unique moyen
// d'ajouter une étape — pas de repli clavier/clic, contrairement à
// WidgetPalette.tsx (App Builder) qui expose déjà un onClick pour le même
// problème. `onAdd` ajoute le nœud à une position par défaut du canevas ;
// le drag existant reste le chemin de placement précis, `onAdd` n'est
// qu'un repli optionnel — le seul consommateur réel (PipelineBuilderPage)
// le fournit toujours.
export function PipelinePalette({ onAdd }: { onAdd?: (op: string) => void }) {
  const opsQuery = usePipelineOps();
  const catalog = opsQuery.data ?? {};
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) byKind[entry.kind].push(op);

  return (
    <div className="flex flex-col gap-3 p-2 text-xs">
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => (
              <li key={op}>
                <button
                  type="button"
                  draggable
                  onDragStart={(e) => {
                    e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                    e.dataTransfer.effectAllowed = "move";
                  }}
                  onClick={() => onAdd?.(op)}
                  className="w-full cursor-grab rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                >
                  {op}
                </button>
              </li>
            ))}
          </ul>
        </div>
      ))}
    </div>
  );
}
