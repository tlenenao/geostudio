// SPDX-License-Identifier: Apache-2.0
import { cn } from "../lib/utils";

export function Card({ className, ...props }: React.HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn("rounded-lg border border-rule bg-surface shadow-sm", className)}
      {...props}
    />
  );
}
