// SPDX-License-Identifier: Apache-2.0
import * as TooltipPrimitive from "@radix-ui/react-tooltip";

export function Tooltip({ content, children }: { content: string; children: React.ReactElement }) {
  return (
    <TooltipPrimitive.Root>
      <TooltipPrimitive.Trigger asChild>{children}</TooltipPrimitive.Trigger>
      <TooltipPrimitive.Portal>
        <TooltipPrimitive.Content
          sideOffset={4}
          // avoidCollisions=false : cf. Combobox.tsx pour la mesure d'origine
          // (SP-29b/Task 13), réutilisée telle quelle en Popover.tsx
          // (Task 20) et Menu.tsx (Task 21) — sous jsdom, le recalcul de
          // collision de @floating-ui/react-dom (shift+flip), utilisé en
          // interne par TooltipPrimitive.Content (même mécanique
          // @radix-ui/react-popper), n'entre jamais en convergence (rects
          // 0×0). Compromis assumé en PRODUCTION, pas un contournement de
          // test : ce tooltip reste positionné sans se replier au bord de
          // la fenêtre, même dans un vrai navigateur.
          avoidCollisions={false}
          className="rounded-md border border-rule bg-ink px-2 py-1 text-xs text-surface shadow-sm"
        >
          {content}
          <TooltipPrimitive.Arrow className="fill-ink" />
        </TooltipPrimitive.Content>
      </TooltipPrimitive.Portal>
    </TooltipPrimitive.Root>
  );
}
