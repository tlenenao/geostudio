// SPDX-License-Identifier: Apache-2.0
import type { PipelineNodeStat } from "../../api/types";
import { t } from "../../i18n";
import "../../i18n/domains/automation";

// F1/F2 : détail d'écriture d'un nœud writer.collection (modes upsert/update/delete), lignes
// rejetées vers la quarantaine `<cible>__rejected` par règle, et taux de nulls de l'entrée.
// Rien n'est affiché pour les nœuds qui ne publient que `rowCount`.
export function RunNodeWriteReport({ stat }: { stat: PipelineNodeStat }) {
  if (stat.inserted === undefined && !stat.rejected && !stat.quality) return null;
  const rules = Object.entries(stat.rejectsByRule ?? {});
  const nulls = (stat.quality?.columns ?? []).filter((c) => c.nulls > 0);
  return (
    <div className="ml-4 flex flex-col gap-0.5">
      {stat.inserted !== undefined && (
        <span>
          {t("pipelineRun.writeSummary", {
            inserted: stat.inserted,
            updated: stat.updated ?? 0,
            deleted: stat.deleted ?? 0,
            unchanged: stat.unchanged ?? 0,
          })}
        </span>
      )}
      {!!stat.rejected && (
        <span role="status" className="text-danger">
          {t("pipelineRun.rejectedSummary", { count: stat.rejected })}
          {rules.length > 0 &&
            " (" +
              rules
                .map(([rule, count]) => t("pipelineRun.rejectedRule", { rule, count }))
                .join(", ") +
              ")"}
          {stat.rejectedCollectionId &&
            " — " + t("pipelineRun.quarantineHint", { id: stat.rejectedCollectionId })}
        </span>
      )}
      {stat.quality && nulls.length > 0 && (
        <details>
          <summary>{t("pipelineRun.qualityHeading", { rows: stat.quality.rowCount })}</summary>
          <ul>
            {nulls.map((c) => (
              <li key={c.name}>
                {t("pipelineRun.qualityNullRate", {
                  name: c.name,
                  rate: (c.nullRate * 100).toFixed(1).replace(".", ","),
                })}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}
