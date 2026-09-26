// SPDX-License-Identifier: Apache-2.0
import { t } from "../../i18n";

export function LoadingState({ label }: { label?: string }) {
  return (
    <p role="status" className="flex items-center gap-2 text-sm text-ink-3">
      <span
        className="h-4 w-4 animate-spin rounded-full border-2 border-rule border-t-accent"
        aria-hidden="true"
      />
      {label ?? t("common.loading")}
    </p>
  );
}
