// SPDX-License-Identifier: Apache-2.0
import { useState } from "react";
import { Database, Save, Wand2 } from "lucide-react";
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";
import { Input } from "../../ui/kit/Input";
import { t } from "../../i18n";
import { useRecentPipelineOps } from "./useRecentPipelineOps";

export const PIPELINE_OP_DND_TYPE = "application/x-geostudio-pipeline-op";
export const PIPELINE_PALETTE_SEARCH_ID = "pipeline-palette-search";

const SECTION_LABEL: Record<PipelineNodeKind, string> = {
  reader: t("pipelinePalette.sectionSources"),
  transform: t("pipelinePalette.sectionTransforms"),
  writer: t("pipelinePalette.sectionWriters"),
};

const KIND_ICON: Record<PipelineNodeKind, React.ComponentType<{ className?: string }>> = {
  reader: Database,
  transform: Wand2,
  writer: Save,
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
  const [query, setQuery] = useState("");
  const { recent, recordUse } = useRecentPipelineOps();
  const normalizedQuery = query.trim().toLowerCase();
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) {
    if (normalizedQuery && !op.toLowerCase().includes(normalizedQuery)) continue;
    byKind[entry.kind].push(op);
  }

  return (
    <div className="flex flex-col gap-3 p-2 text-xs">
      <Input
        id={PIPELINE_PALETTE_SEARCH_ID}
        role="searchbox"
        aria-label={t("pipelinePalette.searchAria")}
        placeholder={t("pipelinePalette.searchPlaceholder")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {recent.length > 0 && (
        <div>
          <h3 className="mb-1 font-semibold text-ink-2">{t("pipelinePalette.sectionRecent")}</h3>
          <ul className="flex flex-col gap-1">
            {recent
              .filter((op) => catalog[op])
              .map((op) => {
                const Icon = KIND_ICON[catalog[op].kind];
                const description = catalog[op].paramsSchema.description;
                return (
                  <li key={op}>
                    <button
                      type="button"
                      draggable
                      onDragStart={(e) => {
                        e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                        e.dataTransfer.effectAllowed = "move";
                        // Cf. commentaire jumeau plus bas (section par kind) : recordUse()
                        // doit être différé hors du gestionnaire `dragstart` synchrone,
                        // sinon Chromium bloque indéfiniment le glisser-déposer natif.
                        setTimeout(() => recordUse(op), 0);
                      }}
                      onClick={() => {
                        recordUse(op);
                        onAdd?.(op);
                      }}
                      className="flex w-full cursor-grab items-start gap-2 rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                    >
                      <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
                      <span className="flex flex-col">
                        <span>{op}</span>
                        {description && (
                          <span className="text-[10px] text-ink-2">{description}</span>
                        )}
                      </span>
                    </button>
                  </li>
                );
              })}
          </ul>
        </div>
      )}
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => {
              const Icon = KIND_ICON[kind];
              const description = catalog[op]?.paramsSchema.description;
              return (
                <li key={op}>
                  <button
                    type="button"
                    draggable
                    onDragStart={(e) => {
                      e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
                      e.dataTransfer.effectAllowed = "move";
                      // Chromium interrompt un glisser-déposer HTML5 natif quand le DOM
                      // est modifié de façon synchrone dans le gestionnaire `dragstart` :
                      // recordUse() déclenche un re-rendu React (montage/réordonnancement
                      // de la section « Récemment utilisés ») avant que le navigateur
                      // n'ait fini d'armer le glisser, ce qui bloque indéfiniment le
                      // mouseup/drop final. Différer d'un tick laisse le navigateur
                      // terminer l'initialisation du glisser avant que React ne re-rende.
                      setTimeout(() => recordUse(op), 0);
                    }}
                    onClick={() => {
                      recordUse(op);
                      onAdd?.(op);
                    }}
                    className="flex w-full cursor-grab items-start gap-2 rounded border border-rule bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
                  >
                    <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
                    <span className="flex flex-col">
                      <span>{op}</span>
                      {description && <span className="text-[10px] text-ink-2">{description}</span>}
                    </span>
                  </button>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </div>
  );
}
