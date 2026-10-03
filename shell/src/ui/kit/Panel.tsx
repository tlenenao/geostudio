// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Panel({
  className,
  children,
  ...rest
}: React.HTMLAttributes<HTMLDivElement> & { children: React.ReactNode }) {
  return (
    <div
      className={cn("rounded-lg border border-rule bg-raised p-4 shadow-md", className)}
      {...rest}
    >
      {children}
    </div>
  );
}
