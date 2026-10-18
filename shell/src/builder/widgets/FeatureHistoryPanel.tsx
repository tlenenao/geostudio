// SPDX-License-Identifier: Apache-2.0
// ARC-15 : onglet « Historique » d'une entité (versions, auteur, champs modifiés, restauration).
import { formatDateTime } from "../../lib/format";
import { useId, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ItemClient, FeatureVersion } from "../../api/types";
import { t } from "../../i18n";
import { LoadingState } from "../../ui/kit/LoadingState";
import "../../i18n/domains/widgets";

function changedKeys(v: FeatureVersion): string[] {
  const before = v.before?.properties ?? {};
  const after = v.after?.properties ?? {};
  const keys = new Set([...Object.keys(before), ...Object.keys(after)]);
  return [...keys].filter((k) => JSON.stringify(before[k]) !== JSON.stringify(after[k])).sort();
}

export function FeatureHistoryPanel({
  client,
  collectionId,
  fid,
  canWrite,
  onRestored,
}: {
  client: ItemClient;
  collectionId: string;
  fid: string;
  canWrite: boolean;
  onRestored?: () => void;
}) {
  const [open, setOpen] = useState(false);
  const panelId = useId();
  const queryClient = useQueryClient();
  const key = ["feature-history", collectionId, fid];
  const list = client.listFeatureHistory;
  const restore = client.restoreFeatureVersion;
  const query = useQuery({
    queryKey: key,
    queryFn: () => list!.call(client, collectionId, fid),
    enabled: open && list !== undefined,
  });
  const restoreMutation = useMutation({
    mutationFn: (versionId: number) => restore!.call(client, collectionId, fid, versionId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: key });
      onRestored?.();
    },
  });
  if (!list) return null;
  const opLabels: Record<FeatureVersion["op"], string> = {
    create: t("featureHistory.opCreate"),
    update: t("featureHistory.opUpdate"),
    delete: t("featureHistory.opDelete"),
    restore: t("featureHistory.opRestore"),
  };
  return (
    <div className="flex flex-col gap-1 text-xs">
      <button
        type="button"
        className="self-start underline"
        aria-expanded={open}
        aria-controls={panelId}
        onClick={() => setOpen((o) => !o)}
      >
        {t("featureHistory.toggle")}
      </button>
      {open && (
        <div id={panelId} role="region" aria-label={t("featureHistory.toggle")}>
          {query.isLoading && <LoadingState />}
          {query.isError && <p className="text-danger">{t("featureHistory.error")}</p>}
          {query.data && query.data.length === 0 && (
            <p className="text-ink-3">{t("featureHistory.empty")}</p>
          )}
          {query.data && query.data.length > 0 && (
            <ol className="flex flex-col gap-1">
              {query.data.map((v) => {
                const keys = changedKeys(v);
                return (
                  <li key={v.id} className="flex flex-col rounded border border-rule p-1">
                    <span className="font-medium">
                      {opLabels[v.op]} ·{formatDateTime(v.at)} ·{" "}
                      {v.actor?.username ?? t("featureHistory.unknownActor")}
                    </span>
                    {keys.length > 0 && (
                      <span className="text-ink-3">
                        {t("featureHistory.changed", { fields: keys.join(", ") })}
                      </span>
                    )}
                    {canWrite && restore && v.after !== null && (
                      <button
                        type="button"
                        className="self-start underline"
                        disabled={restoreMutation.isPending}
                        onClick={() => restoreMutation.mutate(v.id)}
                      >
                        {t("featureHistory.restore")}
                      </button>
                    )}
                  </li>
                );
              })}
            </ol>
          )}
        </div>
      )}
    </div>
  );
}
