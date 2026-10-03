// SPDX-License-Identifier: Apache-2.0
import { cn } from "../lib/utils";

export function Input({ className, ...props }: React.InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-9 w-full rounded-md border border-control bg-surface px-3 text-sm focus-visible:outline-none focus-visible:ring-2",
        className,
      )}
      {...props}
    />
  );
}
