// SPDX-License-Identifier: Apache-2.0
// AUD-086 : lignée amont/aval d'un item (GET /v1/items/{id}/lineage), filtrée par le cœur.
import { Link } from "react-router-dom";
import { useLineage } from "../../api/domains/impact.hooks";
import type { LineageNode } from "../../api/types";
import { LoadingState } from "../../ui/kit/LoadingState";
import { plural, t } from "../../i18n";
import "../../i18n/domains/automation";

function NodeList({ label, nodes }: { label: string; nodes: LineageNode[] }) {
  return (
    <div>
      <p className="text-xs font-medium text-ink-2">{label}</p>
      {nodes.length === 0 ? (
        <p className="text-xs text-ink-2">{t("lineage.none")}</p>
      ) : (
        <ul className="text-sm">
          {nodes.map((n) => (
            <li key={`${n.type}-${n.id}`}>
              {/* Pas de page de détail de collection dans le shell : titre seul. */}
              {n.type === "item" ? (
                <Link to={`/items/${n.id}`} className="text-accent hover:underline">
                  {n.title}
                </Link>
              ) : (
                <span>{n.title}</span>
              )}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function LineagePanel({ itemId }: { itemId: string }) {
  const q = useLineage(itemId);
  if (q.isLoading) return <LoadingState label={t("lineage.loading")} />;
  if (q.isError || !q.data) return null;
  const { nodes, hiddenCount } = q.data;
  return (
    <section aria-label={t("lineage.title")} className="flex flex-col gap-2">
      <h2 className="text-sm font-semibold text-ink">{t("lineage.title")}</h2>
      <NodeList
        label={t("lineage.upstream")}
        nodes={nodes.filter((n) => n.direction === "upstream")}
      />
      <NodeList
        label={t("lineage.downstream")}
        nodes={nodes.filter((n) => n.direction === "downstream")}
      />
      {hiddenCount > 0 && (
        <p className="text-xs text-ink-2">
          {t(plural(hiddenCount, "lineage.hiddenOne", "lineage.hiddenMany"), { n: hiddenCount })}
        </p>
      )}
    </section>
  );
}
