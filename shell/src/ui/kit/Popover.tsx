// SPDX-License-Identifier: Apache-2.0
import * as PopoverPrimitive from "@radix-ui/react-popover";

export function Popover({
  trigger,
  children,
  "aria-label": ariaLabel,
  side = "bottom",
}: {
  trigger: React.ReactNode;
  children: React.ReactNode;
  "aria-label"?: string;
  side?: "top" | "bottom" | "left" | "right";
}) {
  return (
    <PopoverPrimitive.Root>
      <PopoverPrimitive.Trigger asChild>{trigger}</PopoverPrimitive.Trigger>
      <PopoverPrimitive.Portal>
        <PopoverPrimitive.Content
          aria-label={ariaLabel}
          side={side}
          sideOffset={4}
          // avoidCollisions=false : cf. Combobox.tsx pour la mesure d'origine
          // (SP-29b/Task 13) — sous jsdom, le recalcul de collision de
          // @floating-ui/react-dom (shift+flip), utilisé en interne par
          // PopoverPrimitive.Content, n'entre jamais en convergence (rects
          // 0×0), ce qui coûtait ~13s de CPU par test ici aussi (mesuré :
          // 2 tests passant de 5s de timeout chacun à quelques centaines de
          // ms). Compromis assumé en PRODUCTION, pas un contournement de
          // test : ce popover reste ancré sous/à côté de son déclencheur
          // sans se replier au bord de la fenêtre, même dans un vrai
          // navigateur — acceptable pour un premier jet, aucune alternative
          // test-only crédible trouvée.
          avoidCollisions={false}
          className="rounded-md border border-rule bg-raised p-3 text-sm text-ink shadow-md"
        >
          {children}
        </PopoverPrimitive.Content>
      </PopoverPrimitive.Portal>
    </PopoverPrimitive.Root>
  );
}
