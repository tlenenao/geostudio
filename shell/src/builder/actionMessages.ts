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
import type { ActionMessage, AppConfig } from "../api/types";

export function pruneMessagesForIds(
  messages: ActionMessage[],
  removedIds: string[],
): ActionMessage[] {
  if (removedIds.length === 0) return messages;
  const removed = new Set(removedIds);
  return messages.filter((m) => !removed.has(m.from) && !removed.has(m.to));
}

// Miroir exact de `_widget_ids` du cœur (document_validation.py) : ids de tous
// les objets portant `widget` (string) et `id` (string), imbriqués compris.
function widgetIds(node: unknown, out: Set<string>): Set<string> {
  if (Array.isArray(node)) node.forEach((v) => widgetIds(v, out));
  else if (node && typeof node === "object") {
    const o = node as Record<string, unknown>;
    if (typeof o.widget === "string" && typeof o.id === "string") out.add(o.id);
    Object.values(o).forEach((v) => widgetIds(v, out));
  }
  return out;
}

// Retire les câblages orphelins (from/to qui ne résolvent plus rien) que le
// cœur refuse en 422 à l'écriture stricte. Même référentiel que le cœur :
// `from` ∈ widgets ; `to` ∈ widgets ∪ var:<id> ; onEnter : `to` seulement.
// Renvoie la même référence si rien à retirer.
export function sanitizeDanglingMessages(config: AppConfig): AppConfig {
  const layouts = [
    ...(config.layout ? [config.layout] : []),
    ...(config.pages ?? []).map((p) => p.layout),
  ];
  const widgets = widgetIds(layouts, new Set());
  const targets = new Set([...widgets, ...(config.variables ?? []).map((v) => `var:${v.id}`)]);
  const messages = config.messages.filter((m) => widgets.has(m.from) && targets.has(m.to));
  let changed = messages.length !== config.messages.length;
  const pages = config.pages?.map((p) => {
    const onEnter = p.onEnter?.filter((m) => targets.has(m.to));
    if (!p.onEnter || onEnter!.length === p.onEnter.length) return p;
    changed = true;
    return { ...p, onEnter };
  });
  return changed ? { ...config, messages, ...(pages ? { pages } : {}) } : config;
}
