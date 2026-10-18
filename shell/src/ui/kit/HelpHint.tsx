// SPDX-License-Identifier: Apache-2.0
import { HelpCircle } from "lucide-react";
import { IconButton } from "./IconButton";
import { Popover } from "./Popover";

/** Aide contextuelle : une icône « ? » qui ouvre une courte explication (AUD-119). */
export function HelpHint({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <Popover
      aria-label={label}
      trigger={<IconButton icon={<HelpCircle size={14} />} aria-label={label} size="sm" />}
    >
      {children}
    </Popover>
  );
}
