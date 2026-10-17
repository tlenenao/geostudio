// SPDX-License-Identifier: Apache-2.0
import { t } from "../../i18n";
import type { DataSourceState } from "../../api/types";
import "../../i18n/domains/widgets";

type SampleData = Pick<DataSourceState, "records" | "total" | "resolvedSource">;

// AUD-002 : une source `features` ne renvoie qu'une page (100 par défaut, 1000 au plus
// côté cœur). Tout calcul client sur ses lignes est un échantillon dès que
// numberMatched (`total`) le dépasse ; `statistics` est agrégée par le serveur.
export function isSampled(data: SampleData): boolean {
  return (
    data.resolvedSource?.type !== "statistics" &&
    data.total != null &&
    data.total > data.records.length
  );
}

export function SampleBadge({ data }: { data: SampleData }) {
  if (!isSampled(data)) return null;
  return (
    <p role="status" className="text-xs text-[var(--gs-color-muted)]">
      {t("widgetData.sampled", { count: data.records.length, total: data.total ?? 0 })}
    </p>
  );
}
