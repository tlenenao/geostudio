// SPDX-License-Identifier: Apache-2.0
import type { CollectionSchema } from "../../api/types";
import { JoinConfig } from "./inferSchema";
import { t } from "../../i18n";

export function QueryJoinPicker({
  baseSchema,
  joinedSchema,
  collections,
  value,
  onChange,
}: {
  baseSchema: CollectionSchema;
  joinedSchema: CollectionSchema | null;
  collections: { id: string; title: string }[];
  value: JoinConfig;
  onChange: (next: JoinConfig) => void;
}) {
  const baseNames = new Set(baseSchema.fields.map((f) => f.name));
  const commonColumns = joinedSchema
    ? joinedSchema.fields.filter((f) => baseNames.has(f.name))
    : [];

  return (
    <div className="flex flex-col gap-2">
      <label className="flex flex-col gap-1 text-xs">
        {t("queryJoinPicker.collectionLabel")}
        <select
          aria-label={t("queryJoinPicker.collectionAria")}
          className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
          value={value.collectionId}
          onChange={(e) => onChange({ ...value, collectionId: e.target.value, on: "" })}
        >
          <option value="">{t("queryJoinPicker.choose")}</option>
          {collections.map((c) => (
            <option key={c.id} value={c.id}>
              {c.title}
            </option>
          ))}
        </select>
      </label>
      {joinedSchema && commonColumns.length === 0 && (
        <p className="text-xs text-danger">{t("queryJoinPicker.noCommonColumn")}</p>
      )}
      {commonColumns.length > 0 && (
        <label className="flex flex-col gap-1 text-xs">
          {t("queryJoinPicker.joinColumnLabel")}
          <select
            aria-label={t("queryJoinPicker.joinColumnAria")}
            className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
            value={value.on}
            onChange={(e) => onChange({ ...value, on: e.target.value })}
          >
            <option value="">{t("queryJoinPicker.choose")}</option>
            {commonColumns.map((f) => (
              <option key={f.name} value={f.name}>
                {f.name}
              </option>
            ))}
          </select>
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs">
        {t("queryJoinPicker.joinTypeLabel")}
        <select
          aria-label={t("queryJoinPicker.joinTypeAria")}
          className="h-8 rounded border border-rule bg-surface px-2 text-xs text-ink"
          value={value.how}
          onChange={(e) => onChange({ ...value, how: e.target.value as "inner" | "left" })}
        >
          <option value="inner">{t("queryJoinPicker.joinInnerOption")}</option>
          <option value="left">{t("queryJoinPicker.joinLeftOption")}</option>
        </select>
      </label>
    </div>
  );
}
