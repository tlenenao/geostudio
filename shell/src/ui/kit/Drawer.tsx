// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useEffect, useRef } from "react";
import { cn } from "../../lib/utils";

export function Drawer({
  open,
  onOpenChange,
  title,
  side = "right",
  id,
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  side?: "left" | "right";
  // Câblé par usePanelTrigger (SP-43 Tâche 7) : ce Drawer n'utilise pas
  // DialogPrimitive.Trigger, donc le bouton externe qui l'ouvre n'a aucun
  // lien mécanique avec lui — id transmis à Content pour satisfaire
  // aria-controls posé côté appelant.
  id?: string;
  children: React.ReactNode;
}) {
  // D48 : Radix restaure le focus de fermeture via `context.triggerRef`,
  // peuplé uniquement par un `DialogPrimitive.Trigger` (lu dans
  // node_modules/@radix-ui/react-dialog/dist/index.mjs — pas de Trigger ici,
  // cf. commentaire ci-dessus). Sans Trigger, ce ref reste `null` et
  // `onCloseAutoFocus` par défaut ne fait rien : le focus part au
  // `<body>` au lieu de revenir au bouton externe qui a ouvert le panneau.
  // On capture donc nous-mêmes l'élément actif à l'ouverture et on le
  // restaure explicitement à la fermeture.
  const previouslyFocusedRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (open && document.activeElement instanceof HTMLElement) {
      previouslyFocusedRef.current = document.activeElement;
    }
  }, [open]);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          id={id}
          onCloseAutoFocus={(event) => {
            event.preventDefault();
            previouslyFocusedRef.current?.focus();
          }}
          className={cn(
            "fixed top-0 z-50 h-full w-full max-w-sm overflow-y-auto border-rule bg-raised p-4 shadow-lg",
            side === "right" ? "right-0 border-l" : "left-0 border-r",
          )}
        >
          <DialogPrimitive.Title className="mb-4 text-lg font-semibold text-ink">
            {title}
          </DialogPrimitive.Title>
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
