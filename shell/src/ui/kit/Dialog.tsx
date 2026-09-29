// SPDX-License-Identifier: Apache-2.0
import * as DialogPrimitive from "@radix-ui/react-dialog";
import { useFocusRestoreOnClose } from "./useFocusRestoreOnClose";

const SIZE_CLASSES: Record<"md" | "lg", string> = {
  md: "max-w-md",
  lg: "max-w-2xl",
};

export function Dialog({
  open,
  onOpenChange,
  title,
  size = "md",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  size?: "md" | "lg";
  children: React.ReactNode;
}) {
  // D48, revue finale Vague C (point 3) : même défaut que Drawer.tsx avant
  // son correctif Tâche 3 — pas de DialogPrimitive.Trigger ici (le
  // déclencheur externe, souvent un Button gérant lui-même son état `open`,
  // n'a aucun lien mécanique avec ce composant), donc `onCloseAutoFocus` par
  // défaut ne restaurait rien : le focus partait sur `<body>` à la
  // fermeture. Profite à ConfirmDialog (4 sites de suppression) et
  // CommandPalette (⌘K puis Échap), qui rendent tous deux via ce composant.
  const onCloseAutoFocus = useFocusRestoreOnClose(open);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          onCloseAutoFocus={onCloseAutoFocus}
          className={`fixed left-1/2 top-1/2 z-50 w-full ${SIZE_CLASSES[size]} -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-raised p-6 shadow-lg`}
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
