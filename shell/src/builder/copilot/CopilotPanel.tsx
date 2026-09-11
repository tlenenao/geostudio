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
import { useEffect, useRef } from "react";
import type { AppConfig, CopilotClientOp } from "../../api/types";
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
    <CopilotChat
      itemId={itemId}
      surface="app_builder"
      contextPayload={config}
      clientTools={buildClientToolSchemas()}
      opLabels={OP_LABELS}
      onClientOps={handleClientOps}
    />
  );
}
