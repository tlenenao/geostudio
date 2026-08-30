// SPDX-License-Identifier: Apache-2.0
import { cn } from "../../lib/utils";

export function Skeleton({ className }: { className?: string }) {
  return <div className={cn("animate-pulse rounded-sm bg-sunken", className)} />;
}
