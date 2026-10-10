// SPDX-License-Identifier: Apache-2.0
import { useId, useRef, useState } from "react";
import { Database, Save, Wand2 } from "lucide-react";
import { usePipelineOps } from "../../api/hooks";
import type { PipelineNodeKind } from "../../api/types";
import { Input } from "../../ui/kit/Input";
import { t } from "../../i18n";
import { useRecentPipelineOps } from "./useRecentPipelineOps";
import "../../i18n/domains/automation";

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
  const rootRef = useRef<HTMLDivElement>(null);
  const idPrefix = useId();
  const normalizedQuery = query.trim().toLowerCase();
  const byKind: Record<PipelineNodeKind, string[]> = { reader: [], transform: [], writer: [] };
  for (const [op, entry] of Object.entries(catalog)) {
    if (normalizedQuery && !op.toLowerCase().includes(normalizedQuery)) continue;
    byKind[entry.kind].push(op);
  }
  const recentOps = recent.filter((op) => catalog[op]);
  const noResult = !!normalizedQuery && Object.values(byKind).every((l) => l.length === 0);

  // P32.06 : liste à un seul arrêt de tabulation (tabindex itinérant), flèches
  // pour parcourir — le canevas est atteignable sans traverser ~55 boutons.
  const [activeKey, setActiveKey] = useState<string | null>(null);
  const firstKey = recentOps.length > 0 ? `recent:${recentOps[0]}` : null;
  const keys = [
    ...recentOps.map((op) => `recent:${op}`),
    ...(["reader", "transform", "writer"] as const).flatMap((k) =>
      byKind[k].map((op) => `${k}:${op}`),
    ),
  ];
  const tabKey = activeKey && keys.includes(activeKey) ? activeKey : (firstKey ?? keys[0]);

  function onKeyDown(e: React.KeyboardEvent) {
    const keysNav = ["ArrowDown", "ArrowUp", "Home", "End"];
    if (!keysNav.includes(e.key)) return;
    const items = [
      ...(rootRef.current?.querySelectorAll<HTMLElement>("[data-palette-item]") ?? []),
    ];
    const i = items.indexOf(e.target as HTMLElement);
    if (i < 0) return;
    e.preventDefault();
    const next =
      e.key === "Home"
        ? 0
        : e.key === "End"
          ? items.length - 1
          : Math.min(items.length - 1, Math.max(0, i + (e.key === "ArrowDown" ? 1 : -1)));
    items[next]?.focus();
  }

  function item(key: string, kind: PipelineNodeKind, op: string) {
    const Icon = KIND_ICON[kind];
    const description = catalog[op]?.paramsSchema.description;
    const descId = `${idPrefix}-${key}`;
    return (
      <li key={key}>
        <button
          type="button"
          data-palette-item=""
          tabIndex={key === tabKey ? 0 : -1}
          onFocus={() => setActiveKey(key)}
          draggable
          aria-label={op}
          aria-describedby={description ? descId : undefined}
          onDragStart={(e) => {
            e.dataTransfer.setData(PIPELINE_OP_DND_TYPE, op);
            e.dataTransfer.effectAllowed = "move";
          }}
          onDragEnd={() => {
            // Chromium interrompt un glisser-déposer HTML5 natif quand le DOM
            // est modifié de façon synchrone dans le gestionnaire `dragstart` :
            // recordUse() déclenche un re-rendu React (montage/réordonnancement
            // de la section « Récemment utilisés »). `dragend` ne se déclenche
            // qu'une fois la session de glisser-déposer native entièrement
            // conclue : le re-rendu qu'il provoque ne peut donc structurellement
            // jamais interférer avec un glisser en cours.
            recordUse(op);
          }}
          onClick={() => {
            recordUse(op);
            onAdd?.(op);
          }}
          className="flex w-full cursor-grab items-start gap-2 rounded border border-control bg-surface px-2 py-1 text-left text-ink hover:bg-sunken"
        >
          <Icon className="mt-0.5 h-3.5 w-3.5 shrink-0 text-ink-2" />
          <span className="flex flex-col">
            <span>{op}</span>{" "}
            {description && (
              <span id={descId} className="text-xs text-ink-2">
                {description}
              </span>
            )}
          </span>
        </button>
      </li>
    );
  }

  return (
    <div
      ref={rootRef}
      role="presentation"
      onKeyDown={onKeyDown}
      className="flex flex-col gap-3 p-2 text-xs"
    >
      <Input
        id={PIPELINE_PALETTE_SEARCH_ID}
        role="searchbox"
        aria-label={t("pipelinePalette.searchAria")}
        placeholder={t("pipelinePalette.searchPlaceholder")}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      {noResult && (
        <p role="status" className="text-ink-2">
          {t("pipelinePalette.noResults")}
        </p>
      )}
      {recentOps.length > 0 && (
        <div>
          <h3 className="mb-1 font-semibold text-ink-2">{t("pipelinePalette.sectionRecent")}</h3>
          <ul className="flex flex-col gap-1">
            {recentOps.map((op) => item(`recent:${op}`, catalog[op].kind, op))}
          </ul>
        </div>
      )}
      {(["reader", "transform", "writer"] as const).map((kind) => (
        <div key={kind}>
          <h3 className="mb-1 font-semibold text-ink-2">{SECTION_LABEL[kind]}</h3>
          <ul className="flex flex-col gap-1">
            {byKind[kind].map((op) => item(`${kind}:${op}`, kind, op))}
          </ul>
        </div>
      ))}
    </div>
  );
}
