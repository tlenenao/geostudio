// SPDX-License-Identifier: Apache-2.0
import { forwardRef } from "react";
import { cn } from "../../lib/utils";

// forwardRef (D07, SP-C4/Task 21) : additif — les 24 usages existants qui ne
// passent pas de `ref` sont inchangés ; CommandPalette.tsx est le premier
// consommateur à en avoir besoin, pour un focus programmatique à l'ouverture
// de la palette (sans l'attribut `autoFocus`, refusé par jsx-a11y/no-autofocus).
export const Input = forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  function Input({ className, ...props }, ref) {
    return (
      <input
        ref={ref}
        className={cn(
          "h-9 w-full rounded-md border border-rule bg-surface px-3 text-sm text-ink placeholder:text-ink-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
          className,
        )}
        {...props}
      />
    );
  },
);
