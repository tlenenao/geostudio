// SPDX-License-Identifier: Apache-2.0
import { X } from "lucide-react";

export function Chip({ children, onRemove }: { children: React.ReactNode; onRemove?: () => void }) {
  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-rule bg-surface px-2 py-0.5 text-xs text-ink">
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label={`Retirer ${children}`}
          onClick={onRemove}
          className="text-ink-3 hover:text-danger"
        >
          <X size={12} />
        </button>
      )}
    </span>
  );
}
