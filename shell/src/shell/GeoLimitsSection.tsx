// SPDX-License-Identifier: Apache-2.0
import { GroupSearchField, useGroupSearch } from "./GroupSearch";
import { useState } from "react";
import {
  useCollectionSharing,
  useDeleteGeoLimit,
  useGeoLimits,
  usePutGeoLimit,
} from "../api/hooks";
import { t } from "../i18n";
import { Button } from "../ui/kit/Button";
import "../i18n/domains/admin";
import { NativeSelect } from "../ui/kit/NativeSelect";

/** Limite géographique de lecture par groupe (GAP-27). Masquée sans le privilège
 *  admin.collections.manage : la route répond 403, la requête échoue, rien n'est rendu. */
export function GeoLimitsSection({ collectionId }: { collectionId: string }) {
  const limitsQuery = useGeoLimits(collectionId);
  const sharing = useCollectionSharing(collectionId);
  const gs = useGroupSearch(sharing.data?.groups);
  const put = usePutGeoLimit(collectionId);
  const del = useDeleteGeoLimit(collectionId);
  const [groupId, setGroupId] = useState("");
  const [text, setText] = useState("");
  const [parseError, setParseError] = useState(false);

  if (!limitsQuery.isSuccess) return null;
  const groups = gs.groups;
  const known = [...(gs.defaults.data ?? []), ...groups];
  const titleOf = (id: string) => known.find((g) => g.id === id)?.title ?? id;

  async function submit() {
    let geometry: Record<string, unknown>;
    try {
      geometry = JSON.parse(text) as Record<string, unknown>;
    } catch {
      setParseError(true);
      return;
    }
    setParseError(false);
    try {
      await put.mutateAsync({ targetType: "group", targetId: groupId, geometry });
      setText("");
    } catch {
      /* surfaced via put.isError */
    }
  }

  return (
    <section aria-label={t("geoLimits.title")} className="flex flex-col gap-2">
      <h3 className="text-sm font-semibold text-ink">{t("geoLimits.title")}</h3>
      <p className="text-xs text-ink-muted">{t("geoLimits.help")}</p>
      <p className="text-xs text-ink-muted">{t("geoLimits.adminExempt")}</p>
      {limitsQuery.data.length === 0 ? (
        <p className="text-sm text-ink-muted">{t("geoLimits.none")}</p>
      ) : (
        <ul className="flex flex-col gap-1">
          {limitsQuery.data.map((l) => (
            <li
              key={`${l.targetType}:${l.targetId}`}
              className="flex items-center justify-between gap-2 text-sm text-ink"
            >
              <span>{titleOf(l.targetId)}</span>
              <Button
                type="button"
                variant="outline"
                size="sm"
                disabled={del.isPending}
                onClick={() => del.mutate({ targetType: l.targetType, targetId: l.targetId })}
              >
                {t("geoLimits.remove", { group: titleOf(l.targetId) })}
              </Button>
            </li>
          ))}
        </ul>
      )}
      <GroupSearchField state={gs} />
      <label className="flex flex-col gap-1 text-sm text-ink">
        {t("geoLimits.groupLabel")}
        <NativeSelect
          className="h-9 rounded-md border border-control bg-surface px-2 text-sm text-ink w-auto"
          value={groupId}
          onChange={(e) => setGroupId(e.target.value)}
        >
          <option value="" />
          {groups.map((g) => (
            <option key={g.id} value={g.id}>
              {g.title}
            </option>
          ))}
        </NativeSelect>
      </label>
      <label className="flex flex-col gap-1 text-sm text-ink">
        {t("geoLimits.geometryLabel")}
        <textarea
          className="min-h-24 rounded-md border border-control bg-surface p-2 font-mono text-xs text-ink"
          value={text}
          onChange={(e) => setText(e.target.value)}
        />
      </label>
      {(parseError || put.isError || del.isError) && (
        <p role="alert" className="text-sm text-danger">
          {parseError
            ? t("geoLimits.invalidJson")
            : put.isError
              ? t("geoLimits.saveFailed")
              : t("geoLimits.deleteFailed")}
        </p>
      )}
      <div className="flex justify-end">
        <Button
          type="button"
          size="sm"
          disabled={!groupId || !text.trim() || put.isPending}
          onClick={() => void submit()}
        >
          {t("geoLimits.save")}
        </Button>
      </div>
    </section>
  );
}
