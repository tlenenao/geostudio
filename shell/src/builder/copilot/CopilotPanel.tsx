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

const OP_LABELS: Record<string, string> = {
  addWidget: t("copilot.opWidgetAdded"),
  updateWidgetProps: t("copilot.opWidgetUpdated"),
  removeWidget: t("copilot.opWidgetRemoved"),
  addDataSource: t("copilot.opDataSourceAdded"),
  setFilter: t("copilot.opFilterUpdated"),
};

export function CopilotPanel({
  itemId,
  config,
  activePageId,
  setDraft,
}: {
  itemId: string;
  config: AppConfig;
  activePageId: string;
  setDraft: (update: (prev: AppConfig | null) => AppConfig | null) => void;
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
        contextPayload={config}
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
