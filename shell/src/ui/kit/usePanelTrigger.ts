// SPDX-License-Identifier: Apache-2.0
import { useId } from "react";

/**
 * Câble aria-expanded/aria-controls sur un déclencheur et id/role="region"
 * sur le panneau qu'il bascule — fait de la convention CLAUDE.md du
 * 2026-09-01 une propriété du composant plutôt qu'une prose à respecter de
 * mémoire (SP-43 §3.6). Patron de référence : ui/kit/Combobox.tsx, seul
 * site du dépôt à câbler ces attributs aujourd'hui, via Radix.
 */
export function usePanelTrigger(open: boolean) {
  const panelId = useId();
  return {
    panelId,
    triggerProps: {
      "aria-expanded": open,
      "aria-controls": panelId,
    } as const,
    panelProps: {
      id: panelId,
      role: "region" as const,
    },
  };
}
