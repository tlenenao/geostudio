// SPDX-License-Identifier: Apache-2.0
// Copilote sur la requête visuelle (GAP-17) — enveloppe fine de
// CopilotChat, applique filtres/jointure/résumé générés à l'état local du
// wizard sans jamais créer ni exécuter le pipeline (le bouton Créer/Mettre
// à jour de VisualQueryWizardPage reste l'unique déclencheur).
import type { CollectionSchema, CopilotClientOp } from "../../api/types";
import { t } from "../../i18n";
import type { FilterRow } from "../visualQuery/compileFilter";
import type { JoinConfig, SummaryConfig } from "../visualQuery/inferSchema";
import { applyVisualQueryClientOp } from "./applyVisualQueryClientOp";
import type { RawClientOp } from "./applyClientOp";
import { CopilotChat } from "./CopilotChat";
import { buildVisualQueryClientToolSchemas } from "./visualQueryClientTools";

export function VisualQueryCopilotPanel({
  baseCollectionId,
  baseSchema,
  joinedSchema,
  collectionIds,
  filters,
  join,
  summary,
  setFilters,
  setJoin,
  setSummary,
}: {
  baseCollectionId: string;
  // Contexte de validation (I2/I3, revue finale de branche GAP-17) : le
  // wizard a déjà chargé ces trois choses ; les passer ici permet de rejeter
  // une colonne ou une collection hallucinée avant qu'elle n'atteigne le
  // formulaire — la validation faite par le tool MCP côté serveur n'atteint
  // jamais ce point, puisque c'est le LLM (pas le JSON validé) qui compose
  // l'appel applyVisualQueryDraft.
  baseSchema: CollectionSchema;
  joinedSchema: CollectionSchema | null;
  collectionIds: string[];
  filters: FilterRow[];
  join: JoinConfig | null;
  summary: SummaryConfig | null;
  setFilters: (rows: FilterRow[]) => void;
  setJoin: (join: JoinConfig | null) => void;
  setSummary: (summary: SummaryConfig | null) => void;
}) {
  function handleClientOps(ops: CopilotClientOp[]): boolean[] {
    return (ops as RawClientOp[]).map((op) =>
      applyVisualQueryClientOp(
        op,
        { setFilters, setJoin, setSummary },
        { baseSchema, joinedSchema, collectionIds },
      ),
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
