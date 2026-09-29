// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { cn } from "../../lib/utils";
import { useFocusRestoreOnClose } from "./useFocusRestoreOnClose";

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
  // D48 : cf. useFocusRestoreOnClose.ts pour le pourquoi (pas de
  // DialogPrimitive.Trigger ici, donc rien ne restaure le focus sans lui).
  const onCloseAutoFocus = useFocusRestoreOnClose(open);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          id={id}
          onCloseAutoFocus={onCloseAutoFocus}
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
