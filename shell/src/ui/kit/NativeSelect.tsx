// SPDX-License-Identifier: Apache-2.0
import { forwardRef } from "react";
import { cn } from "../../lib/utils";

// <select> natif aux mêmes hauteur/bordure/jetons que Input (P34.06) : à
// préférer à `Select` (Radix) quand le contrôle doit rester un vrai <select>
// (formulaires courts, tests `selectOption`).
export const NativeSelect = forwardRef<
  HTMLSelectElement,
  React.SelectHTMLAttributes<HTMLSelectElement>
>(function NativeSelect({ className, ...props }, ref) {
  return (
    <select
      ref={ref}
      className={cn(
        "h-9 w-full rounded-md border border-control bg-surface px-3 text-sm text-ink focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-50",
        className,
      )}
      {...props}
    />
  );
});
