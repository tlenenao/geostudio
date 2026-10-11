// SPDX-License-Identifier: Apache-2.0
// Panneau copilote du builder d'App (SP-20) — enveloppe fine de
// CopilotChat (GAP-17), spécialisée pour un AppConfig unique patché via
// applyClientOp/setDraft (undo SP-19 : un seul appel par tour).
//
// Écart au texte du brief Task 6 (GAP-17) : `activePageId` est lu via un
// ref, pas directement dans la fermeture de `handleClientOps`. Raison —
// un tour peut durer plusieurs secondes ; si l'utilisateur change de page
// pendant ce temps, `CopilotChat.send()` (déjà en vol) a capturé la
// fermeture `onClientOps` de CE rendu-là et ne verra jamais une nouvelle
// fermeture recréée par un rendu ultérieur de CopilotPanel — exactement
// le même problème que celui qui avait motivé `activePageIdRef` dans
// l'ancien CopilotPanel.tsx monolithique. Vérifié par le test de
// caractérisation existant ("applies clientOps against the page active
// when the reply lands, not the one active at send time") : la version
// littérale du brief (fermeture directe sur `activePageId`) le fait
// échouer.
import { useEffect, useRef, useState } from "react";
import type { AppConfig, CopilotClientOp } from "../../api/types";
import { appendCopilotHistory, readCopilotHistory } from "../../lib/copilotHistory";
import { applyClientOp, type RawClientOp } from "./applyClientOp";
import { buildClientToolSchemas } from "./clientTools";
import { CopilotChat } from "./CopilotChat";
import { t } from "../../i18n";
import "../../i18n/domains/automation";

const OP_LABELS: Record<string, string> = {
  addWidget: t("copilot.opWidgetAdded"),
  updateWidgetProps: t("copilot.opWidgetUpdated"),
  removeWidget: t("copilot.opWidgetRemoved"),
  addDataSource: t("copilot.opDataSourceAdded"),
  setFilter: t("copilot.opFilterUpdated"),
};

// Plafond du cœur (MAX_CONFIG_CHARS = 64 000, core/app/copilot/routes.py) avec
// une marge : au-delà, seule la page active part en entier, les autres sont
// réduites à {id, name} (j11-013).
const COMPACT_THRESHOLD_CHARS = 60_000;

export function compactForCopilot(config: AppConfig, activePageId: string): AppConfig {
  if (JSON.stringify(config).length <= COMPACT_THRESHOLD_CHARS || !config.pages) return config;
  return {
    ...config,
    pages: config.pages.map((p) =>
      p.id === activePageId ? p : { id: p.id, name: p.name, layout: { ...p.layout, items: [] } },
    ),
  };
}

export function CopilotPanel({
  itemId,
  config,
  activePageId,
  setDraft,
  readOnly = false,
}: {
  itemId: string;
  config: AppConfig;
  activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void;
  readOnly?: boolean;
}) {
  // P07.08 : l'historique persistant (par compte et par item) est relisible.
  const [pastExchanges, setPastExchanges] = useState(() => readCopilotHistory(itemId));
  const activePageIdRef = useRef(activePageId);
  useEffect(() => {
    activePageIdRef.current = activePageId;
  }, [activePageId]);

  function handleClientOps(ops: CopilotClientOp[]) {
    setDraft((d) => {
      if (!d) return d;
      return (ops as RawClientOp[]).reduce(
        (acc, op) => applyClientOp(op, acc, activePageIdRef.current),
        d,
      );
    });
  }

  return (
    <>
      <CopilotChat
        itemId={itemId}
        surface="app_builder"
        contextPayload={compactForCopilot(config, activePageId)}
        disabled={readOnly}
        clientTools={buildClientToolSchemas()}
        opLabels={OP_LABELS}
        onClientOps={handleClientOps}
        onExchange={(entry) => setPastExchanges(appendCopilotHistory(entry, itemId))}
      />
      {pastExchanges.length > 0 && (
        <details className="mt-2 text-xs text-ink-2">
          <summary>{t("copilot.pastExchanges", { count: pastExchanges.length })}</summary>
          <ul className="mt-1 flex flex-col gap-1">
            {pastExchanges.map((e) => (
              <li key={e.id}>
                {e.message}
                {e.status === "error" ? ` — ${t("copilot.requestFailed")}` : ""}
              </li>
            ))}
          </ul>
        </details>
      )}
    </>
  );
}
