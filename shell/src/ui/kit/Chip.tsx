// SPDX-License-Identifier: Apache-2.0
import { X } from "lucide-react";
import { t } from "../../i18n";

export function Chip({
  children,
  onRemove,
  removeLabel,
}: {
  children: React.ReactNode;
  onRemove?: () => void;
  removeLabel?: string;
}) {
  const resolvedRemoveLabel =
    removeLabel ??
    (typeof children === "string" ? t("chip.remove", { item: children }) : t("chip.removeGeneric"));

  return (
    <span className="inline-flex items-center gap-1 rounded-full border border-rule bg-surface px-2 py-0.5 text-xs text-ink">
      {children}
      {onRemove && (
        <button
          type="button"
          aria-label={resolvedRemoveLabel}
          onClick={onRemove}
          className="text-ink-3 hover:text-danger"
        >
          <X size={12} />
        </button>
      )}
    </span>
  );
}
