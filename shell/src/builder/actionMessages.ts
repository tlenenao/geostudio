// SPDX-License-Identifier: Apache-2.0
// Retire tout ActionMessage dont from/to référence l'un des ids retirés —
// évite qu'un câblage ActionsPanel orphelin reste indéfiniment dans
// config.messages, invisible (ActionsPanel.resolvesOnThisPage le filtre
// déjà de l'affichage) mais jamais purgé, donc impossible à retirer depuis
// l'UI (GAP-66c). Un id nu identifie un widget retiré ; un id "var:<id>"
// identifie une variable retirée — même fonction pour les deux, appelée
// par AppRenderer.handleRemove (widget) et AppBuilderPage.setVariables
// (variable), pour ne jamais écrire ce filtrage à deux endroits légèrement
// différents (CLAUDE.md, piège n°4).
import type { ActionMessage } from "../api/types";

export function pruneMessagesForIds(
  messages: ActionMessage[],
  removedIds: string[],
): ActionMessage[] {
  if (removedIds.length === 0) return messages;
  const removed = new Set(removedIds);
  return messages.filter((m) => !removed.has(m.from) && !removed.has(m.to));
}
