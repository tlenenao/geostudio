// SPDX-License-Identifier: Apache-2.0
// Scan top-level uniquement (pas de récursion dans tabs/modal/drawer — leur
// contenu vit dans LayoutItem.props: dict côté serveur, invisible à un scan
// typé ; cf. plan §Global Constraints, gap documenté non bloquant).
import type { AppConfig } from "../../api/types";

export function collectWidgetTypes(config: AppConfig): Set<string> {
  const types = new Set<string>();
  for (const page of config.pages ?? []) {
    for (const item of page.layout.items) {
      types.add(item.widget);
    }
  }
  return types;
}

export const WRITE_CAPABLE_WIDGET_TYPES = new Set(["form"]);
