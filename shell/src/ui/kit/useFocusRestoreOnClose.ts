// SPDX-License-Identifier: Apache-2.0
import { useEffect, useRef } from "react";

// D48 (Drawer.tsx, Tâche 3) : Radix restaure le focus de fermeture d'un
// DialogPrimitive.Root via `context.triggerRef`, peuplé uniquement par un
// `DialogPrimitive.Trigger` (lu dans
// node_modules/@radix-ui/react-dialog/dist/index.mjs). Ni Drawer.tsx ni
// Dialog.tsx n'utilisent ce Trigger — leur déclencheur externe est câblé
// séparément (aria-controls/usePanelTrigger, ou un simple `onClick` posant
// `open=true`), sans lien mécanique avec le composant. Sans ce hook,
// `onCloseAutoFocus` par défaut ne fait rien et le focus part sur
// `<body>` à la fermeture. Capture l'élément actif à l'ouverture, le
// restaure explicitement à la fermeture — revue finale Vague C (point 3) :
// factorisé ici, partagé entre Drawer.tsx et Dialog.tsx (ce dernier avait
// le même défaut, jamais corrigé).
export function useFocusRestoreOnClose(open: boolean): (event: Event) => void {
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open && document.activeElement instanceof HTMLElement) {
      previouslyFocusedRef.current = document.activeElement;
    }
  }, [open]);

  return function onCloseAutoFocus(event: Event) {
    event.preventDefault();
    previouslyFocusedRef.current?.focus();
  };
}
