// SPDX-License-Identifier: Apache-2.0
// Copilote sur la requête visuelle (GAP-17) — enveloppe fine de
// CopilotChat, applique filtres/jointure/résumé générés à l'état local du
// wizard sans jamais créer ni exécuter le pipeline (le bouton Créer/Mettre
// à jour de VisualQueryWizardPage reste l'unique déclencheur).
import type { CopilotClientOp } from "../../api/types";
import { t } from "../../i18n";
import type { FilterRow } from "../visualQuery/compileFilter";
import type { JoinConfig, SummaryConfig } from "../visualQuery/inferSchema";
import { applyVisualQueryClientOp } from "./applyVisualQueryClientOp";
import type { RawClientOp } from "./applyClientOp";
import { CopilotChat } from "./CopilotChat";
import { buildVisualQueryClientToolSchemas } from "./visualQueryClientTools";

export function VisualQueryCopilotPanel({
  baseCollectionId,
  filters,
  join,
  summary,
  setFilters,
  setJoin,
  setSummary,
}: {
  baseCollectionId: string;
  filters: FilterRow[];
  join: JoinConfig | null;
  summary: SummaryConfig | null;
  setFilters: (rows: FilterRow[]) => void;
  setJoin: (join: JoinConfig | null) => void;
  setSummary: (summary: SummaryConfig | null) => void;
}) {
  function handleClientOps(ops: CopilotClientOp[]) {
    (ops as RawClientOp[]).forEach((op) =>
      applyVisualQueryClientOp(op, { setFilters, setJoin, setSummary }),
    );
  }

  return (
    <CopilotChat
      surface="visual_query"
      contextPayload={{ baseCollectionId, filters, join, summary }}
      clientTools={buildVisualQueryClientToolSchemas()}
      opLabels={{ applyVisualQueryDraft: t("copilot.opVisualQueryDraftApplied") }}
      onClientOps={handleClientOps}
    />
  );
}
