// SPDX-License-Identifier: Apache-2.0
// Copilote sur SQL Lab (GAP-17) — enveloppe fine de CopilotChat, insère un
// brouillon SQL sans jamais l'exécuter (le bouton Exécuter de SqlLabPage
// reste l'unique déclencheur).
import type { CopilotClientOp } from "../../api/types";
import { t } from "../../i18n";
import { applySqlLabClientOp } from "./applySqlLabClientOp";
import type { RawClientOp } from "./applyClientOp";
import { CopilotChat } from "./CopilotChat";
import { buildSqlLabClientToolSchemas } from "./sqlLabClientTools";

export function SqlLabCopilotPanel({
  sql,
  setSql,
}: {
  sql: string;
  setSql: (sql: string) => void;
}) {
  function handleClientOps(ops: CopilotClientOp[]) {
    (ops as RawClientOp[]).forEach((op) => applySqlLabClientOp(op, setSql));
  }

  return (
    <CopilotChat
      surface="sql_lab"
      contextPayload={{ sql }}
      clientTools={buildSqlLabClientToolSchemas()}
      opLabels={{ applySqlDraft: t("copilot.opSqlDraftApplied") }}
      onClientOps={handleClientOps}
    />
  );
}
