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
  collections,
}: {
  sql: string;
  setSql: (sql: string) => void;
  // Liste des collections visibles par l'utilisateur (I1, revue finale de
  // branche GAP-17) : `generate_sql_query` exige un `collectionId` et aucun
  // des outils MCP de l'allowlist du copilote n'énumère les collections —
  // sans cette liste dans le contexte, l'outil est inutilisable sur cette
  // surface avec un vrai fournisseur LLM. Pendant exact du
  // `baseCollectionId` déjà transmis par VisualQueryCopilotPanel.
  collections: { id: string; title: string }[];
}) {
  function handleClientOps(ops: CopilotClientOp[]): boolean[] {
    return (ops as RawClientOp[]).map((op) => applySqlLabClientOp(op, setSql));
  }

  return (
    <CopilotChat
      surface="sql_lab"
      contextPayload={{ sql, collections }}
      clientTools={buildSqlLabClientToolSchemas()}
      opLabels={{ applySqlDraft: t("copilot.opSqlDraftApplied") }}
      onClientOps={handleClientOps}
    />
  );
}
