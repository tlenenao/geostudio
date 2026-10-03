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
  description,
  alert = false,
  returnFocusRef,
  size = "md",
  children,
}: {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  title: string;
  /** Texte relié au dialogue par aria-describedby (WCAG, P33.11). */
  description?: string;
  /** role="alertdialog" : dialogue qui interrompt pour une confirmation. */
  alert?: boolean;
  /** Cible du focus à la fermeture quand le déclencheur n'est plus dans le DOM
   * au moment de l'ouverture (ex. dialogue ouvert depuis un item de menu). */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
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
  const onCloseAutoFocus = useFocusRestoreOnClose(open, returnFocusRef);

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-ink/40" />
        <DialogPrimitive.Content
          onCloseAutoFocus={onCloseAutoFocus}
          {...(alert ? { role: "alertdialog" } : {})}
          className={`fixed left-1/2 top-1/2 z-50 w-full ${SIZE_CLASSES[size]} -translate-x-1/2 -translate-y-1/2 rounded-lg border border-rule bg-raised p-6 shadow-lg`}
        >
          <DialogPrimitive.Title className="mb-4 text-lg font-semibold text-ink">
            {title}
          </DialogPrimitive.Title>
          {description && (
            <DialogPrimitive.Description className="mb-4 text-sm text-ink-2">
              {description}
            </DialogPrimitive.Description>
          )}
          {children}
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  );
}
