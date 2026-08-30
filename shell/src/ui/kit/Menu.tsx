// SPDX-License-Identifier: Apache-2.0
import * as DropdownMenuPrimitive from "@radix-ui/react-dropdown-menu";
import { cn } from "../../lib/utils";

export function Menu({
  trigger,
  items,
}: {
  trigger: React.ReactNode;
  items: { label: string; onSelect: () => void; disabled?: boolean; danger?: boolean }[];
}) {
  return (
    <DropdownMenuPrimitive.Root>
      <DropdownMenuPrimitive.Trigger asChild>{trigger}</DropdownMenuPrimitive.Trigger>
      <DropdownMenuPrimitive.Portal>
        <DropdownMenuPrimitive.Content
          sideOffset={4}
          // avoidCollisions=false : cf. Combobox.tsx pour la mesure d'origine
          // (SP-29b/Task 13), réutilisée telle quelle en Popover.tsx
          // (Task 20) — sous jsdom, le recalcul de collision de
          // @floating-ui/react-dom (shift+flip), utilisé en interne par
          // DropdownMenuPrimitive.Content (même mécanique @radix-ui/react-popper
          // que Popover), n'entre jamais en convergence (rects 0×0), ce qui
          // coûtait ~14-16s de CPU par test ici aussi (mesuré : les 2 tests
          // de ce fichier passaient en timeout à 5000ms sans ce correctif).
          // Compromis assumé en PRODUCTION, pas un contournement de test : ce
          // menu reste ancré sous/à côté de son déclencheur sans se replier
          // au bord de la fenêtre, même dans un vrai navigateur — acceptable
          // pour un premier jet, aucune alternative test-only crédible
          // trouvée.
          avoidCollisions={false}
          className="min-w-40 rounded-md border border-rule bg-raised p-1 shadow-md"
        >
          {items.map((item) => (
            <DropdownMenuPrimitive.Item
              key={item.label}
              disabled={item.disabled}
              onSelect={item.onSelect}
              className={cn(
                "cursor-pointer rounded-sm px-2 py-1.5 text-sm text-ink data-[highlighted]:bg-sunken data-[highlighted]:outline-none data-[disabled]:pointer-events-none data-[disabled]:opacity-50",
                item.danger && "text-danger",
              )}
            >
              {item.label}
            </DropdownMenuPrimitive.Item>
          ))}
        </DropdownMenuPrimitive.Content>
      </DropdownMenuPrimitive.Portal>
    </DropdownMenuPrimitive.Root>
  );
}
